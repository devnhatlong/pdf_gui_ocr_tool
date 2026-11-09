"""Regression checks: python -m unittest discover -s tests -v."""
import os
import subprocess
import sys
import threading
import time
import unittest
from types import SimpleNamespace

import psutil

from core.jobs import Cancelled, JobManager
from core.ocr_worker import OcrWorker
from utils.ocr_engine import OcrResult


class BlockingService:
    """A native-style call that never cooperatively checks for cancellation."""
    def __init__(self, device_pref):
        self.device = "cpu"
        self._models = {"vl": True}
        self._viet = None
        self._paddle_ok = True
        self.import_error = self._viet_error = None

    def recognize(self, path, quality, engine, progress):
        if path == "block":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            progress(f"blocked:{os.getpid()}:{child.pid}")
            if os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.Sleep(60000)
            else:
                time.sleep(60)
        if path == "crash":
            os._exit(7)
        return OcrResult(text="recovered", engine="test")


def wait_for(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for job state")


class CancellationTests(unittest.TestCase):
    def test_running_native_call_stops_and_queue_recovers(self):
        worker = OcrWorker(service_factory=BlockingService)
        manager = JobManager()
        pids = []

        def progress(message):
            pids.extend(int(p) for p in message.split(":")[1:])

        try:
            first = manager.submit("ocr", "native", lambda job: worker.recognize(
                "block", progress=progress, check_cancel=job.check_cancelled))
            wait_for(lambda: len(pids) == 2)
            self.assertTrue(all(psutil.pid_exists(pid) for pid in pids))
            second = manager.submit("ocr", "next", lambda job: worker.recognize(
                "ok", check_cancel=job.check_cancelled))
            start = time.monotonic()
            self.assertTrue(manager.cancel(first.id))
            wait_for(lambda: first.status == "cancelled", timeout=3)
            self.assertLess(time.monotonic() - start, 3)
            wait_for(lambda: not any(psutil.pid_exists(pid) for pid in pids))
            self.assertIsNone(first.result)
            wait_for(lambda: second.status == "done")
            self.assertEqual(second.result.text, "recovered")
        finally:
            worker.close()

    def test_last_page_cannot_overwrite_cancel_with_done(self):
        manager = JobManager()
        started, release = threading.Event(), threading.Event()

        def run(job):
            started.set()
            release.wait(5)
            job.update(message="late progress")
            return {"pages": 1}

        job = manager.submit("ocr", "last page", run)
        self.assertTrue(started.wait(3))
        manager.cancel(job.id)
        self.assertEqual(job.status, "cancelling")
        self.assertTrue(manager.busy())
        release.set()
        wait_for(lambda: job.status == "cancelled")
        self.assertEqual(job.message, "Đã hủy")
        self.assertIsNone(job.result)
        self.assertFalse(manager.cancel(job.id))

    def test_queued_and_paused_jobs_cancel_without_running_next_items(self):
        manager = JobManager()
        hold = threading.Event()
        first = manager.submit("ocr", "hold", lambda job: hold.wait(5))
        wait_for(lambda: first.status == "running")
        ran = []
        queued = manager.submit("ocr", "queued", lambda job: ran.append(True))
        manager.pause(queued.id)
        manager.cancel(queued.id)
        hold.set()
        wait_for(lambda: first.status == "done")
        self.assertEqual(queued.status, "cancelled")
        self.assertFalse(ran)

        def batch(job):
            job.items = [{"status": "done"}, {"status": "running"}, {"status": "queued"}]
            job._resume.clear()
            job.check()

        paused = manager.submit("batch", "paused", batch)
        wait_for(lambda: paused.status == "paused")
        manager.cancel(paused.id)
        wait_for(lambda: paused.status == "cancelled")
        self.assertEqual([item["status"] for item in paused.items], ["done", "cancelled", "cancelled"])

    def test_crashed_worker_can_restart(self):
        worker = OcrWorker(service_factory=BlockingService)
        try:
            with self.assertRaises((RuntimeError, EOFError, OSError)):
                worker.recognize("crash")
            self.assertEqual(worker.recognize("ok").text, "recovered")
        finally:
            worker.close()

    def test_cancel_before_call_does_not_start_worker(self):
        worker = OcrWorker(service_factory=BlockingService)
        def cancel():
            raise Cancelled()
        try:
            with self.assertRaises(Cancelled):
                worker.recognize("block", check_cancel=cancel)
            self.assertIsNone(worker._process)
        finally:
            worker.close()

    def test_cancel_preserves_finished_pages_and_unprocessed_edits(self):
        from core.api import Api
        api = Api.__new__(Api)
        api._settings = {"quality": "fast", "engine": "fast"}
        pages = [SimpleNamespace(uid="first"), SimpleNamespace(uid="second")]
        doc = SimpleNamespace(id="document", name="two pages", pages=pages,
                              ocr={}, edits={"first": "old", "second": "keep this edit"})
        api._prepare_page = lambda document, page, options, job: page.uid
        events = []
        api._push = events.append
        def recognize(path, **kwargs):
            if path == "second":
                raise Cancelled()
            return OcrResult(text="finished page", engine="test")
        api._ocr = SimpleNamespace(recognize=recognize)
        manager = JobManager()
        job = manager.submit("ocr", "two pages", lambda job: api._ocr_pages(
            job, doc, [p.uid for p in pages], {}))
        wait_for(lambda: job.status in ("done", "cancelled", "error"))
        self.assertEqual(job.status, "cancelled", job.error)
        self.assertEqual(doc.ocr["first"]["text"], "finished page")
        self.assertNotIn("second", doc.ocr)
        self.assertEqual(doc.edits, {"second": "keep this edit"})
        self.assertEqual([event["uid"] for event in events], ["first"])


if __name__ == "__main__":
    unittest.main()
