"""Batch split checks: python -m unittest tests.test_batch_split -v."""
import os
import tempfile
import threading
import time
import unittest

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from core.api import Api
from core.jobs import JobManager
from utils.ocr_engine import OcrResult

HEADER = ("ỦY BAN NHÂN DÂN HUYỆN X\nCỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\n"
          "Số: {n}/QĐ-UBND\nHuyện X, ngày 05 tháng 11 năm 2026\nQUYẾT ĐỊNH")


class FakeSettings:
    def __init__(self, output_dir):
        self.values = {"output_dir": output_dir, "dpi": 72, "split_threshold": 70, "remove_blank_pages": True,
                       "naming_rule": "{so}-{loai}-{coquan}_{ngay}_{trichyeu}", "slash_replacement": "-"}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def all(self):
        return dict(self.values)


class FakeHistory:
    def __init__(self):
        self.rows = []

    def add(self, kind, *args, **kwargs):
        self.rows.append((kind, kwargs))


class FakeOcr:
    """Every call gets the next page text, so a document's first page looks like an official letter."""
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def detect_orientation(self, img, check_cancel=None):
        return 0

    def recognize(self, path, quality, engine, progress, check_cancel):
        with self.lock:
            self.calls += 1
            n = self.calls
        text = HEADER.format(n=n)
        lines = [{"text": t, "box": [10, 10 + i * 20, 300, 25 + i * 20], "score": 0.9}
                 for i, t in enumerate(text.splitlines())]
        return OcrResult(text=text, engine="test", lines=lines, size=(612, 792))


def make_pdf(path, pages):
    """pages: chuỗi, "x" = trang có chữ, "." = trang trắng."""
    c = canvas.Canvas(path)
    for kind in pages:
        if kind == "x":
            c.setFont("Helvetica", 28)
            for y in range(100, 750, 40):
                c.drawString(60, y, "Sample document content line")
        c.showPage()
    c.save()


def wait_job(jobs, job_id):
    end = time.monotonic() + 30
    while time.monotonic() < end:
        job = jobs.get(job_id)
        if job.status not in ("queued", "running"):
            return job
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for batch")


class BatchSplitTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.api = Api.__new__(Api)   # bỏ qua __init__: không đụng data thật, không nạp model
        self.api._settings = FakeSettings(os.path.join(self.dir.name, "out"))
        self.api._history = FakeHistory()
        self.api._ocr = FakeOcr()
        self.api._jobs = JobManager()
        self.api._docs = {}
        self.api._workspace = os.path.join(self.dir.name, "ws")
        os.makedirs(self.api._workspace)
        self.api._events = []
        self.api._events_lock = threading.Lock()
        self.source = os.path.join(self.dir.name, "tap.pdf")
        make_pdf(self.source, "xx.x")

    def run_batch(self, task, **opts):
        started = self.api.batch_start([self.source], task, opts)
        self.assertNotIn("error", started)
        job = wait_job(self.api._jobs, started["job_id"])
        self.assertEqual(job.status, "done", job.message)
        self.assertEqual(job.items[0]["status"], "done", job.items[0]["message"])
        return job, job.items[0]["outputs"]

    def test_no_split_keeps_one_output_and_ocrs_every_page(self):
        _, outputs = self.run_batch("ocr_txt", split="none")
        self.assertEqual(len(outputs), 1)
        self.assertEqual(self.api._ocr.calls, 4)

    def test_blank_split_with_each_ocr_format(self):
        for task, ext in (("ocr_docx", ".docx"), ("ocr_txt", ".txt"), ("ocr_xlsx", ".xlsx"),
                          ("ocr_searchable_pdf", ".pdf")):
            with self.subTest(task=task):
                self.api._ocr.calls = 0
                _, outputs = self.run_batch(task, split="blank")
                self.assertEqual(len(outputs), 2)
                self.assertTrue(all(p.endswith(ext) and os.path.exists(p) for p in outputs), outputs)
                self.assertEqual(self.api._ocr.calls, 3)   # trang trắng không OCR

    def test_ai_split_with_word_output(self):
        _, outputs = self.run_batch("ocr_docx", split="ai")
        self.assertEqual(len(outputs), 3)   # mỗi trang có chữ đều giống trang đầu văn bản
        self.assertTrue(all(p.endswith(".docx") for p in outputs))

    def test_pdf_blank_split_needs_no_ocr(self):
        _, outputs = self.run_batch("pdf", split="blank")
        self.assertEqual(self.api._ocr.calls, 0)
        self.assertEqual(sorted(len(PdfReader(p).pages) for p in outputs), [1, 2])

    def test_pdf_blank_split_ocrs_when_classifying(self):
        self.run_batch("pdf", split="blank", classify="type")
        self.assertEqual(self.api._ocr.calls, 3)

    def test_rename_with_split_keeps_source_file(self):
        _, outputs = self.run_batch("rename", split="blank")
        self.assertTrue(os.path.exists(self.source))
        self.assertEqual(len(outputs), 2)
        self.assertTrue(all(p.endswith(".pdf") and "Phan_" not in p for p in outputs), outputs)
        self.assertTrue(all(os.path.basename(p).startswith(("1-QĐ-UBND", "3-QĐ-UBND")) for p in outputs), outputs)

    def test_split_names_use_configured_slash_replacement(self):
        self.api._settings.values["slash_replacement"] = "."
        _, outputs = self.run_batch("rename", split="blank")   # dấu / của ngày 05/11/2026 -> 05.11.2026
        self.assertTrue(all("05.11.2026" in os.path.basename(p) for p in outputs), outputs)

    def test_export_failure_marks_file_as_error(self):
        self.api.export_groups = lambda *a, **k: {"error": "Đĩa đầy"}
        started = self.api.batch_start([self.source], "pdf", {"split": "blank"})
        job = wait_job(self.api._jobs, started["job_id"])
        self.assertEqual(job.items[0]["status"], "error")
        self.assertEqual(job.items[0]["message"], "Đĩa đầy")

    def test_retry_keeps_split_options(self):
        self.api.export_groups = lambda *a, **k: {"error": "Đĩa đầy"}
        started = self.api.batch_start([self.source], "ocr_txt", {"split": "blank", "quality": "fast"})
        wait_job(self.api._jobs, started["job_id"])
        del self.api.export_groups
        retry = self.api.batch_retry(started["job_id"])
        job = wait_job(self.api._jobs, retry["job_id"])
        self.assertEqual(job.meta["opts"], {"split": "blank", "quality": "fast"})
        self.assertEqual(len(job.items[0]["outputs"]), 2)


if __name__ == "__main__":
    unittest.main()
