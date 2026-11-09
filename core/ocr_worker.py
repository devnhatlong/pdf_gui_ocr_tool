"""Run native OCR in a reusable child process so cancellation can stop inference."""

import importlib.util
import multiprocessing
import threading
import traceback

import psutil

from core.jobs import Cancelled
from utils.ocr_engine import OcrService


def _worker_main(connection, device_pref, service_factory):
    service = service_factory(device_pref)

    def state():
        return {"device": service.device, "models": list(service._models),
                "viet": service._viet is not None, "paddle": service._paddle_ok,
                "import_error": service.import_error, "viet_error": service._viet_error}

    def progress(message):
        connection.send(("progress", message, state()))

    try:
        while True:
            method, args, kwargs, report_progress = connection.recv()
            if report_progress:
                kwargs["progress"] = progress
            try:
                result = getattr(service, method)(*args, **kwargs)
            except Exception as error:
                connection.send(("error", (str(error), traceback.format_exc()), state()))
            else:
                connection.send(("result", result, state()))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


class OcrWorker(OcrService):
    """Keep status reads in the UI process; serialize heavy work in the child."""

    def __init__(self, device_pref="auto", *, service_factory=OcrService):
        super().__init__(device_pref)
        self._context = multiprocessing.get_context("spawn")
        self._service_factory = service_factory
        self._process = None
        self._connection = None
        self._closed = threading.Event()

    def paddle_available(self):
        # Do not import Paddle in the UI process (native calls can hold its GIL).
        if self._paddle_ok is not None:
            return self._paddle_ok
        return importlib.util.find_spec("paddleocr") is not None

    def get_device(self):
        return self.device or "cpu"

    def _sync_state(self, state):
        self.device = state["device"]
        self._models = dict.fromkeys(state["models"])
        self._viet = True if state["viet"] else None
        self._paddle_ok = state["paddle"]
        self.import_error = state["import_error"]
        self._viet_error = state["viet_error"]

    def _start(self):
        if self._process is not None and self._process.is_alive():
            return
        self._stop()
        parent, child = self._context.Pipe()
        process = self._context.Process(target=_worker_main,
                                        args=(child, self.device_pref, self._service_factory),
                                        name="OfflineOCR inference", daemon=True)
        try:
            process.start()
        except BaseException:
            parent.close()
            process.close()
            raise
        finally:
            child.close()
        self._connection, self._process = parent, process

    def _stop(self):
        process = self._process
        if process is not None:
            if process.is_alive():
                # Tesseract may be a grandchild. Stop only this worker's descendants.
                try:
                    children = psutil.Process(process.pid).children(recursive=True)
                except psutil.Error:
                    children = []
                for child in children:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                process.terminate()
                process.join(2)
                if process.is_alive():
                    process.kill()
                    process.join(2)
                if process.is_alive():
                    raise RuntimeError("Chưa dừng được tiến trình OCR")
            process.join()
            process.close()
        if self._connection is not None:
            self._connection.close()
        self._process = self._connection = None
        self._models = {}
        self._viet = None

    def _call(self, method, *args, progress=None, check_cancel=None, **kwargs):
        def check():
            if self._closed.is_set():
                raise Cancelled()
            if check_cancel:
                check_cancel()

        # A region OCR / settings call can already own the worker.
        while not self._lock.acquire(timeout=0.05):
            check()
        try:
            check()
            self._start()
            self._connection.send((method, args, kwargs, progress is not None))
            while True:
                check()
                if not self._connection.poll(0.05):
                    if not self._process.is_alive():
                        raise RuntimeError("Tiến trình OCR đã dừng. Hãy chạy lại tác vụ.")
                    continue
                kind, payload, state = self._connection.recv()
                check()
                self._sync_state(state)
                if kind == "progress":
                    progress(payload)
                elif kind == "error":
                    raise RuntimeError(payload[0])
                else:
                    return payload
        except BaseException:
            # Never leave a cancelled native call running or reuse a partial response.
            self._stop()
            raise
        finally:
            self._lock.release()

    def warmup(self, progress=lambda message: None, check_cancel=None):
        return self._call("warmup", progress=progress, check_cancel=check_cancel)

    def recognize(self, image_path, quality="fast", engine="auto", progress=lambda message: None,
                  check_cancel=None):
        return self._call("recognize", image_path, quality=quality, engine=engine,
                          progress=progress, check_cancel=check_cancel)

    def recognize_region(self, image_path, box, progress=lambda message: None):
        return self._call("recognize_region", image_path, box, progress=progress)

    def detect_orientation(self, image, check_cancel=None):
        return self._call("detect_orientation", image, check_cancel=check_cancel)

    def load(self, key, progress=lambda message: None, check_cancel=None):
        return self._call("load", key, progress=progress, check_cancel=check_cancel)

    def unload(self, key):
        with self._lock:
            if self._process is not None:
                self._call("unload", key)

    def set_device_pref(self, pref):
        with self._lock:
            if pref != self.device_pref:
                self._stop()
                self.device_pref, self.device = pref, None

    def close(self):
        self._closed.set()
        with self._lock:
            self._stop()
