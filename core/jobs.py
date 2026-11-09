# === jobs.py ===
# Hàng đợi tác vụ nặng (OCR, tách AI, hàng loạt) chạy lần lượt trên 1 luồng nền - model dùng chung bộ nhớ
# GPU/CPU nên không chạy song song. Hỗ trợ tạm dừng / tiếp tục / hủy và báo tiến độ cho giao diện.

import itertools
import queue
import threading
import time
import traceback


class Cancelled(Exception):
    pass


class Job:
    _ids = itertools.count(1)

    def __init__(self, kind, title, fn, meta=None):
        self.id = next(self._ids)
        self.kind = kind
        self.title = title
        self.fn = fn
        self.meta = meta or {}
        self.status = "queued"     # queued | running | paused | cancelling | done | error | cancelled
        self.progress = 0.0
        self.message = "Đang chờ"
        self.result = None
        self.error = None
        self.items = []            # tiến độ từng file (xử lý hàng loạt)
        self.created = time.time()
        self.version = 0
        self._cancel = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._manager = None

    # --- gọi từ trong tác vụ ---
    def update(self, progress=None, message=None, **items):
        with self._manager._lock:
            if self._cancel.is_set():
                return
            if progress is not None:
                self.progress = max(0.0, min(1.0, progress))
            if message is not None:
                self.message = message
            self._manager._touch_locked(self)

    def check_cancelled(self):
        """Safe to poll during inference; pausing remains at page boundaries."""
        if self._cancel.is_set():
            raise Cancelled()

    def check(self):
        """Gọi định kỳ trong tác vụ: dừng nếu bị hủy, chờ nếu đang tạm dừng."""
        self.check_cancelled()
        if not self._resume.is_set():
            with self._manager._lock:
                self.check_cancelled()
                self.status = "paused"
                self._manager._touch_locked(self)
            self._resume.wait()
            with self._manager._lock:
                self.check_cancelled()
                self.status = "running"
                self._manager._touch_locked(self)
        self.check_cancelled()

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "title": self.title, "status": self.status,
                "progress": round(self.progress, 4), "message": self.message, "result": self.result,
                "error": self.error, "items": self.items, "meta": self.meta}


class JobManager:
    def __init__(self):
        self._queue = queue.Queue()
        self._jobs = {}
        self._lock = threading.Lock()
        self._version = 0
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, kind, title, fn, meta=None, front=False):
        job = Job(kind, title, fn, meta)
        job._manager = self
        with self._lock:
            self._jobs[job.id] = job
        self._touch(job)
        self._queue.put(job)
        return job

    def _touch(self, job):
        with self._lock:
            self._touch_locked(job)

    def _touch_locked(self, job):
        self._version += 1
        job.version = self._version

    def _cancelled_locked(self, job):
        job.status = "cancelled"
        job.message = "Đã hủy"
        job.result = None
        job.error = None
        for item in job.items:
            if item["status"] in ("running", "queued", "paused"):
                item.update(status="cancelled", message="Đã hủy")

    def _run(self):
        while True:
            job = self._queue.get()
            with self._lock:
                if job._cancel.is_set():
                    self._cancelled_locked(job)
                    self._touch_locked(job)
                    continue
                job.status = "running"
                job.message = "Đang xử lý"
                self._touch_locked(job)
            try:
                result = job.fn(job)
                with self._lock:
                    if job._cancel.is_set():
                        self._cancelled_locked(job)
                    else:
                        job.result = result
                        job.status = "done"
                        job.progress = 1.0
                        if job.message in ("Đang xử lý", "Đang chờ"):
                            job.message = "Hoàn thành"
            except Cancelled:
                with self._lock:
                    self._cancelled_locked(job)
            except Exception as e:
                with self._lock:
                    if job._cancel.is_set():
                        self._cancelled_locked(job)
                    else:
                        job.status = "error"
                        job.error = str(e)
                        job.message = f"Lỗi: {e}"
                        job.meta["trace"] = traceback.format_exc()
            self._touch(job)

    def get(self, job_id):
        return self._jobs.get(job_id)

    def cancel(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status not in ("queued", "running", "paused", "cancelling"):
                return False
            job._cancel.set()
            job._resume.set()
            if job.status == "queued":
                self._cancelled_locked(job)
            else:
                job.status = "cancelling"
                job.message = "Đang hủy…"
            self._touch_locked(job)
            return True

    def pause(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in ("queued", "running"):
                job._resume.clear()
                job.message = "Đang tạm dừng…"
                self._touch_locked(job)

    def resume(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in ("queued", "running", "paused"):
                job._resume.set()
                if job.status == "paused":
                    job.status = "running"
                self._touch_locked(job)

    def changes(self, since):
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.version > since]
            return self._version, [j.to_dict() for j in jobs]

    def busy(self):
        with self._lock:
            return any(j.status in ("queued", "running", "paused", "cancelling") for j in self._jobs.values())
