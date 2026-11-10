# === api.py ===
# Các hàm giao diện HTML gọi xuống Python (window.pywebview.api.*). Mọi giá trị trả về đều là JSON.
# Thuộc tính nội bộ đặt tên bắt đầu bằng "_" để pywebview không đưa ra JavaScript.

import csv
import datetime
import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback

import webview

import config
from core import exporters, history, imaging, metadata, splitter, system
from core.document import SUPPORTED_EXTS, Document, new_workspace, short_stem, unique_path
from core.jobs import Cancelled, JobManager
from core.settings import Settings
from utils import license_utils as lic
from utils.ocr_engine import ENGINES, QUALITY
from core.ocr_worker import OcrWorker

DOC_FILTER = ("Tài liệu (*.pdf;*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.webp)", "Tất cả (*.*)")


def _safe(fn):
    """Bắt lỗi và trả về {"error": ...} thay vì làm hỏng lời gọi từ giao diện."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


class Api:
    def __init__(self):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        self._settings = Settings()
        self._history = history.History()
        self._history.purge(self._settings.get("history_days"))
        self._ocr = OcrWorker(self._settings.get("device"))
        self._jobs = JobManager()
        self._docs = {}
        self._workspace = new_workspace()
        self._events = []
        self._events_lock = threading.Lock()
        self._window = None
        self._engine_label = "Đang khởi động"
        self._jobs.submit("warmup", "Nạp mô hình OCR", self._warmup_job)

    # ==================================================
    # Nội bộ
    # ==================================================
    def _close(self):
        self._ocr.close()

    def _set_window(self, window):
        self._window = window

    def _push(self, event):
        with self._events_lock:
            self._events.append(event)

    def _doc(self, doc_id):
        doc = self._docs.get(doc_id)
        if not doc:
            raise KeyError("Tài liệu không còn mở")
        return doc

    def _warmup_job(self, job):
        self._engine_label = self._ocr.warmup(lambda m: job.update(message=m), check_cancel=job.check_cancelled)
        job.message = f"Sẵn sàng · {self._engine_label}"
        return {"engine": self._engine_label}

    def _file_name(self, fields):
        return metadata.build_filename(fields, self._settings.get("naming_rule"),
                                       slash=self._settings.get("slash_replacement"),
                                       ascii_name=self._settings.get("filename_ascii"))

    def _output_dir(self, sub=""):
        base = self._settings.get("output_dir") or config.DEFAULT_OUTPUT_DIR
        if self._settings.get("folder_by_date"):
            base = os.path.join(base, datetime.date.today().strftime("%Y-%m-%d"))
        path = os.path.join(base, sub) if sub else base
        os.makedirs(path, exist_ok=True)
        return path

    def _dialog(self, kind, **kw):
        if not self._window:
            return None
        kinds = {"open": webview.FileDialog.OPEN, "folder": webview.FileDialog.FOLDER,
                 "save": webview.FileDialog.SAVE}
        return self._window.create_file_dialog(kinds[kind], **kw)

    # ==================================================
    # Khởi động, bản quyền, hệ thống
    # ==================================================
    @_safe
    def bootstrap(self):
        return {
            "app": {"name": config.APP_NAME, "version": config.APP_VERSION,
                    "author": [{"label": a, "value": b} for a, b in config.AUTHOR_LINES]},
            "license": self.license_status(),
            "settings": self._settings.all(),
            "engines": [{"key": k, "label": v} for k, v in ENGINES.items()],
            "quality": [{"key": k, "label": v} for k, v in QUALITY.items()],
            "formats": [{"key": k, "label": v[0]} for k, v in exporters.FORMATS.items()],
            "doc_types": [{"code": c, "label": n} for c, n in metadata.DOC_TYPES],
            "defaults": {"doc_type_map": metadata.DEFAULT_TYPE_MAP, "agency_map": metadata.DEFAULT_AGENCY_MAP},
        }

    @_safe
    def license_status(self):
        info = {"machine_id": lic.get_machine_id()}
        if lic.check_license():
            li = lic.get_license_info() or {}
            exp = li.get("expiry_date")
            info.update(state="licensed", expiry=exp,
                        label="Bản quyền vĩnh viễn" if not exp or exp >= "2099-01-01"
                        else f"Bản quyền đến {datetime.datetime.strptime(exp, '%Y-%m-%d').strftime('%d/%m/%Y')}")
            return info
        if lic.check_trial():
            days = lic.get_trial_info().get("remaining_days", 0)
            if days > 0:
                info.update(state="trial", days=days, label=f"Dùng thử · còn {days} ngày")
                return info
        info.update(state="expired", label="Hết hạn dùng thử")
        return info

    @_safe
    def activate_license(self, key):
        key = re.sub(r"\s+", "", key or "")
        if not key:
            return {"ok": False, "message": "Vui lòng nhập License Key"}
        ok, message = lic.verify_license_key(key)
        if not ok:
            return {"ok": False, "message": message}
        if not lic.save_license(key):
            return {"ok": False, "message": "Không lưu được license - hãy chạy phần mềm ở thư mục có quyền ghi"}
        return {"ok": True, "status": self.license_status()}

    @_safe
    def quit_app(self):
        if self._window:
            self._window.destroy()
        return True

    @_safe
    def copy_text(self, text):
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True

    @_safe
    def system_status(self):
        snap = system.snapshot()
        snap["device"] = self._ocr.device_label() if self._ocr.device else "-"
        snap["engine"] = self._engine_label
        snap["models"] = [m for m in self._ocr.model_status() if m["loaded"]]
        snap["busy"] = self._jobs.busy()
        return snap

    @_safe
    def dashboard(self):
        return {"stats": self._history.stats(), "recent": self._history.search(limit=6),
                "models": self._ocr.model_status(), "system": self.system_status()}

    @_safe
    def poll(self, since=0):
        version, jobs = self._jobs.changes(since)
        with self._events_lock:
            events, self._events = self._events, []
        return {"version": version, "jobs": jobs, "events": events}

    @_safe
    def job_cancel(self, job_id):
        return self._jobs.cancel(job_id)

    @_safe
    def job_pause(self, job_id):
        self._jobs.pause(job_id)
        return True

    @_safe
    def job_resume(self, job_id):
        self._jobs.resume(job_id)
        return True

    # ==================================================
    # File & tài liệu
    # ==================================================
    @_safe
    def pick_files(self, multiple=True):
        res = self._dialog("open", allow_multiple=multiple, file_types=DOC_FILTER)
        return list(res or [])

    @_safe
    def pick_folder(self):
        res = self._dialog("folder")
        return res[0] if res else ""

    @staticmethod
    def _expand(paths):
        out = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    out += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(SUPPORTED_EXTS)]
            elif p.lower().endswith(SUPPORTED_EXTS):
                out.append(p)
        return out

    @_safe
    def expand_paths(self, paths):
        return [{"path": p, "name": os.path.basename(p), "size": os.path.getsize(p)} for p in self._expand(paths)]

    @_safe
    def open_documents(self, paths):
        out, errors = [], []
        for p in self._expand(paths):
            try:
                key = os.path.normcase(os.path.abspath(p))
                existing = next((d for d in self._docs.values()
                                 if d.path and os.path.normcase(os.path.abspath(d.path)) == key), None)
                if existing is not None:    # đã mở file này rồi -> dùng lại, không tạo trùng
                    out.append(existing.summary())
                    continue
                doc = Document(p, self._workspace)
                self._docs[doc.id] = doc
                self._load_draft(doc)
                out.append(doc.summary())
            except Exception as e:
                errors.append(f"{os.path.basename(p)}: {e}")
        return {"docs": out, "errors": errors}

    @_safe
    def close_document(self, doc_id):
        doc = self._docs.pop(doc_id, None)
        if doc and self._settings.get("clean_temp"):
            shutil.rmtree(doc.cache_dir, ignore_errors=True)
        return True

    @_safe
    def document(self, doc_id):
        return self._doc(doc_id).summary()

    @_safe
    def thumbnails(self, doc_id, uids=None):
        doc = self._doc(doc_id)
        pages = [p for p in doc.pages if uids is None or p.uid in uids]
        return [{"uid": p.uid, "src": doc.thumbnail(p)} for p in pages]

    @_safe
    def page_image(self, doc_id, uid, max_side=1600, original=False):
        """Ảnh trang để xem: nếu đã OCR thì trả ảnh đã tiền xử lý (khung tọa độ OCR khớp ảnh này).
        original=True: luôn trả ảnh như khi xuất file."""
        doc = self._doc(doc_id)
        page = doc.page(uid)
        from PIL import Image
        if not original and uid in doc.ocr_images and os.path.exists(doc.ocr_images[uid]):
            img = Image.open(doc.ocr_images[uid])
        else:
            img, _ = doc.render(page, self._settings.get("dpi"))
        return {"src": imaging.to_data_url(img, max_side=max_side), "width": img.width, "height": img.height}

    @_safe
    def open_path(self, path):
        os.startfile(path)
        return True

    @_safe
    def reveal(self, path):
        if os.path.isdir(path):
            os.startfile(path)
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        return True

    # ==================================================
    # OCR
    # ==================================================
    def _prepare_page(self, doc, page, opts, job=None):
        """Dựng ảnh trang + tiền xử lý (xoay hướng, làm thẳng, giảm nhiễu). Trả về đường dẫn ảnh."""
        if job:
            job.check()
        dpi = int(opts.get("dpi") or self._settings.get("dpi"))
        img, _ = doc.render(page, dpi)
        if opts.get("auto_rotate", self._settings.get("auto_rotate")):
            angle = self._ocr.detect_orientation(img, check_cancel=job.check_cancelled if job else None)
            if angle:
                # Xoay luôn trang trong tài liệu để file xuất ra cũng đứng thẳng
                page.rotation = (page.rotation + 360 - angle) % 360
                img, _ = doc.render(page, dpi)
        if opts.get("deskew", self._settings.get("deskew")):
            img, _a = imaging.deskew(img)
        if opts.get("denoise", self._settings.get("denoise")):
            img = imaging.denoise(img)
        img = imaging.boost_ink(img, opts.get("ink_boost", self._settings.get("ink_boost")))
        img = imaging.apply_color_mode(img, opts.get("color_mode", self._settings.get("color_mode")))
        path = os.path.join(doc.cache_dir, f"ocr_{page.uid}.png")
        if job:
            job.check()
        img.save(path)
        doc.ocr_images[page.uid] = path
        return path

    def _ocr_pages(self, job, doc, uids, opts, base=0.0, span=1.0):
        quality = opts.get("quality") or self._settings.get("quality")
        engine = opts.get("engine") or self._settings.get("engine")
        pages = [p for p in doc.pages if p.uid in set(uids)]
        for n, page in enumerate(pages):
            job.check()
            pos = doc.pages.index(page) + 1
            job.update(base + span * n / max(1, len(pages)), f"{doc.name} · trang {pos}/{len(doc.pages)}")
            path = self._prepare_page(doc, page, opts, job)
            job.check()
            res = self._ocr.recognize(
                path, quality=quality, engine=engine,
                progress=lambda m, pos=pos: job.update(message=f"Trang {pos}: {m}"),
                check_cancel=job.check_cancelled)
            job.check()
            doc.ocr[page.uid] = res.to_dict()
            doc.edits.pop(page.uid, None)
            self._push({"type": "page_ocr", "doc_id": doc.id, "uid": page.uid})
        job.check()
        return pages

    @_safe
    def ocr_run(self, doc_id, uids=None, opts=None):
        doc = self._doc(doc_id)
        opts = opts or {}
        uids = uids or [p.uid for p in doc.pages]

        def run(job):
            start = time.time()
            try:
                pages = self._ocr_pages(job, doc, uids, opts)
            except Cancelled:
                raise
            except Exception as e:
                self._history.add("ocr", doc.name, doc.path, len(uids), "error", time.time() - start, detail=str(e))
                raise
            results = [doc.ocr[p.uid] for p in pages]
            confs = [r["confidence"] for r in results if r.get("confidence") is not None]
            engines = sorted({r["engine"] for r in results})
            text = "\n\n".join(doc.page_text(p.uid) for p in doc.pages if p.uid in doc.ocr)
            self._history.add("ocr", doc.name, doc.path, len(pages), "done", time.time() - start,
                              ", ".join(engines), sum(confs) / len(confs) if confs else None, text=text)
            notes = sorted({n for r in results for n in r.get("notes", [])})
            job.message = f"Đã nhận dạng {len(pages)} trang · {', '.join(engines)}"
            return {"doc_id": doc.id, "pages": len(pages), "notes": notes,
                    "seconds": round(time.time() - start, 1)}

        job = self._jobs.submit("ocr", f"OCR · {doc.name}", run, {"doc_id": doc.id})
        return {"job_id": job.id}

    @_safe
    def ocr_result(self, doc_id, uid):
        doc = self._doc(doc_id)
        res = doc.ocr.get(uid)
        if not res:
            return None
        return {**res, "text": doc.page_text(uid), "edited": uid in doc.edits,
                "threshold": self._settings.get("ocr_threshold") / 100}

    @_safe
    def ocr_region(self, doc_id, uid, box):
        """box: [x1,y1,x2,y2] theo tỉ lệ 0..1 của ảnh đang xem."""
        doc = self._doc(doc_id)
        page = doc.page(uid)
        path = doc.ocr_images.get(uid)
        if not path or not os.path.exists(path):
            _img, path = doc.render(page, self._settings.get("dpi"))
            if not os.path.exists(path):
                _img.save(path)
        from PIL import Image
        w, h = Image.open(path).size
        px = [box[0] * w, box[1] * h, box[2] * w, box[3] * h]
        res = self._ocr.recognize_region(path, px)
        return {"text": res.text, "engine": res.engine, "lines": res.lines}

    @_safe
    def save_edit(self, doc_id, uid, text):
        doc = self._doc(doc_id)
        original = (doc.ocr.get(uid) or {}).get("text", "")
        if text == original:
            doc.edits.pop(uid, None)
        else:
            doc.edits[uid] = text
        return True

    def _draft_path(self, doc):
        name = re.sub(r"[^\w.-]", "_", os.path.basename(doc.path))
        return os.path.join(config.DATA_DIR, "drafts", name + ".json")

    @_safe
    def save_draft(self, doc_id):
        doc = self._doc(doc_id)
        path = self._draft_path(doc)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pages = [{"index": p.index, "rotation": p.rotation, "ocr": doc.ocr.get(p.uid),
                  "edit": doc.edits.get(p.uid)} for p in doc.pages]
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"source": doc.path, "saved": time.time(), "pages": pages}, f, ensure_ascii=False)
        return {"path": path}

    def _load_draft(self, doc):
        path = self._draft_path(doc)
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("source") != doc.path:
                return
            by_index = {p.index: p for p in doc.pages}
            for item in data.get("pages", []):
                page = by_index.get(item.get("index"))
                if not page:
                    continue
                page.rotation = item.get("rotation", 0)
                if item.get("ocr"):
                    doc.ocr[page.uid] = item["ocr"]
                if item.get("edit") is not None:
                    doc.edits[page.uid] = item["edit"]
            doc.meta["draft"] = True
        except (OSError, ValueError):
            pass

    @_safe
    def doc_metadata(self, doc_id):
        """Thông tin văn bản (từ trang đầu đã OCR) + tên file gợi ý theo quy tắc đặt tên."""
        doc = self._doc(doc_id)
        first = next((p for p in doc.pages if p.uid in doc.ocr), None)
        meta = metadata.extract_metadata(doc.page_text(first.uid),
                                         self._settings.get("doc_type_map"),
                                         self._settings.get("agency_map")) if first else {}
        fields = metadata.meta_to_fields(meta) if meta else {}
        return {"meta": meta, "fields": fields,
                "filename": self._file_name(fields) if fields else ""}

    @_safe
    def build_filename(self, fields):
        return self._file_name(fields)

    @_safe
    def rename_source(self, doc_id, new_name):
        """Đổi tên file gốc trên đĩa (chức năng đặt tên file theo thông tin văn bản)."""
        doc = self._doc(doc_id)
        new_name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", new_name or "").strip()
        if not new_name:
            return {"ok": False, "message": "Tên file mới đang trống"}
        ext = os.path.splitext(doc.path)[1]
        if not new_name.lower().endswith(ext.lower()):
            new_name += ext
        new_path = os.path.join(os.path.dirname(doc.path), new_name)
        if os.path.normcase(new_path) == os.path.normcase(doc.path):
            return {"ok": True, "path": doc.path}
        if os.path.exists(new_path):
            return {"ok": False, "message": f"Đã có file \"{new_name}\" trong thư mục"}
        old_draft = self._draft_path(doc)
        os.rename(doc.path, new_path)
        for p in doc.pages:
            if os.path.normcase(p.src) == os.path.normcase(doc.path):
                p.src = new_path
        doc.path, doc.name = new_path, new_name
        if os.path.exists(old_draft):
            os.replace(old_draft, self._draft_path(doc))
        self._history.add("pdf", new_name, new_path, len(doc.pages), detail="Đổi tên file", outputs=[new_path])
        return {"ok": True, "path": new_path, "name": new_name}

    # ==================================================
    # Xuất
    # ==================================================
    def _export_pages(self, doc, uids=None):
        out = []
        for p in doc.pages:
            if uids and p.uid not in uids:
                continue
            res = doc.ocr.get(p.uid) or {}
            out.append({"uid": p.uid, "page": p, "text": doc.page_text(p.uid), "markdown": res.get("markdown", "")
                        if p.uid not in doc.edits else "", "lines": res.get("lines", []), "blocks": res.get("blocks", []),
                        "size": res.get("size"), "engine": res.get("engine")})
        return out

    @_safe
    def export_document(self, doc_id, fmt, scope="all", uid=None, path=None, name=None):
        doc = self._doc(doc_id)
        ext = exporters.FORMATS[fmt][1]
        base = short_stem(name or doc.name, 120)
        if not path:
            res = self._dialog("save", directory=self._output_dir(), save_filename=base + ext)
            if not res:
                return {"cancelled": True}
            path = res if isinstance(res, str) else res[0]
        path = unique_path(path, self._settings.get("overwrite"))
        uids = [uid] if scope == "page" and uid else None
        pages = self._export_pages(doc, uids)
        if fmt == "searchable_pdf" and not any(p["lines"] for p in pages):
            return {"error": "Chưa có kết quả OCR - hãy chạy OCR trước khi xuất PDF có lớp chữ"}
        exporters.export(fmt, pages, path, doc)
        self._history.add("ocr" if fmt != "pdf" else "pdf", os.path.basename(path), doc.path, len(pages),
                          detail=f"Xuất {exporters.FORMATS[fmt][0]}", outputs=[path])
        return {"path": path}

    # ==================================================
    # Cắt, ghép, sắp xếp trang
    # ==================================================
    @_safe
    def pages_rotate(self, doc_id, uids, degrees):
        doc = self._doc(doc_id)
        for u in uids:
            doc.rotate(u, degrees)
        return self.thumbnails(doc_id, uids)

    @_safe
    def pages_delete(self, doc_id, uids):
        doc = self._doc(doc_id)
        if len(uids) >= len(doc.pages):
            return {"error": "Phải giữ lại ít nhất một trang"}
        doc.delete(uids)
        return doc.summary()

    @_safe
    def pages_reorder(self, doc_id, uids):
        doc = self._doc(doc_id)
        doc.reorder(uids)
        return doc.summary()

    @_safe
    def pages_reverse(self, doc_id):
        doc = self._doc(doc_id)
        doc.reverse()
        return doc.summary()

    @_safe
    def pages_insert(self, doc_id, position, paths=None):
        """Chèn toàn bộ trang của file khác vào vị trí position."""
        doc = self._doc(doc_id)
        paths = paths or self.pick_files(True)
        added = 0
        for p in self._expand(paths):
            other = Document(p, self._workspace)
            added += len(doc.insert_from(other, position + added))
        return doc.summary() | {"added": added}

    @_safe
    def page_replace(self, doc_id, uid, path=None, page_no=1):
        doc = self._doc(doc_id)
        if not path:
            files = self.pick_files(False)
            if not files:
                return {"cancelled": True}
            path = files[0]
        other = Document(path, self._workspace)
        idx = max(0, min(int(page_no) - 1, len(other.pages) - 1))
        doc.replace_page(uid, other.pages[idx])
        return doc.summary()

    @_safe
    def merge_documents(self, doc_ids, name="Tai_lieu_ghep.pdf"):
        docs = [self._doc(d) for d in doc_ids]
        if not docs:
            return {"error": "Chưa chọn tài liệu để ghép"}
        merged = Document(docs[0].path, self._workspace)
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        merged.name = name
        merged.path = os.path.join(self._output_dir(), name)   # chưa có trên đĩa cho tới khi lưu
        merged.pages = []
        for d in docs:
            merged.insert_from(d, len(merged.pages))
            for src_page, new_page in zip(d.pages, merged.pages[-len(d.pages):]):
                if src_page.uid in d.ocr:
                    merged.ocr[new_page.uid] = d.ocr[src_page.uid]
                    if src_page.uid in d.ocr_images:
                        merged.ocr_images[new_page.uid] = d.ocr_images[src_page.uid]
                if src_page.uid in d.edits:
                    merged.edits[new_page.uid] = d.edits[src_page.uid]
        self._docs[merged.id] = merged
        return merged.summary()

    @_safe
    def split_plan(self, doc_id, method, value=""):
        """Chia trang theo: ranges ("1-3, 4, 5-8"), every (N trang), odd_even, extract (trang chọn),
        blank (trang trắng), code (QR/barcode)."""
        doc = self._doc(doc_id)
        pages = doc.pages
        n = len(pages)
        chunks = []
        if method == "ranges":
            for part in re.split(r"[,;]\s*", value or ""):
                m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", part)
                if not m:
                    continue
                a = int(m.group(1))
                b = int(m.group(2) or a)
                a, b = max(1, min(a, b)), min(n, max(a, b))
                if a <= b:
                    chunks.append(list(range(a - 1, b)))
        elif method == "every":
            k = max(1, int(value or 1))
            chunks = [list(range(i, min(n, i + k))) for i in range(0, n, k)]
        elif method == "odd_even":
            chunks = [list(range(0, n, 2)), list(range(1, n, 2))]
        elif method == "extract":
            wanted = set(value or [])
            chunks = [[i for i, p in enumerate(pages) if p.uid in wanted]]
        elif method in ("blank", "code"):
            self._detect_separators(doc, need_codes=(method == "code"))
            cur = []
            for i, p in enumerate(pages):
                sep = p.blank if method == "blank" else bool(p.codes)
                if sep:
                    if cur:
                        chunks.append(cur)
                    cur = []
                else:
                    cur.append(i)
            if cur:
                chunks.append(cur)
        chunks = [c for c in chunks if c]
        base = os.path.splitext(doc.name)[0]
        groups = []
        for i, c in enumerate(chunks):
            label = {"odd_even": ["Trang_le", "Trang_chan"][i] if i < 2 else f"Phan_{i + 1}"}.get(method, f"Phan_{i + 1:02d}")
            groups.append({"start_uid": pages[c[0]].uid, "uids": [pages[j].uid for j in c],
                           "name": f"{base}_{label}", "confidence": 100, "reasons": [], "type": "", "agency": ""})
        doc.groups = groups
        return {"groups": groups, "pages": doc.summary()["pages"]}

    def _detect_separators(self, doc, need_codes=False, job=None):
        for p in doc.pages:
            if job:
                job.check()
            if p.blank is None or (need_codes and p.codes is None):
                img, _ = doc.render(p, 100 if need_codes else 48)
                if p.blank is None:
                    p.blank = imaging.is_blank(img)
                if need_codes and p.codes is None:
                    p.codes = imaging.read_codes(img) if not p.blank else []

    # ==================================================
    # AI tách văn bản
    # ==================================================
    @_safe
    def split_analyze(self, doc_id, opts=None):
        doc = self._doc(doc_id)
        opts = opts or {}

        def run(job):
            start = time.time()
            job.update(0.02, "Đang tìm trang trắng và mã phân cách")
            self._detect_separators(doc, need_codes=True, job=job)
            todo = [p.uid for p in doc.pages if p.uid not in doc.ocr and not p.blank and not p.codes]
            if todo:
                self._ocr_pages(job, doc, todo, {"quality": "fast", "engine": "fast", **opts}, 0.05, 0.9)
            job.check()
            job.update(0.97, "AI đang phân tích ranh giới văn bản")
            groups = splitter.analyze(doc, self._settings.all())
            self._history.add("split", doc.name, doc.path, len(doc.pages), "done", time.time() - start,
                              "PP-OCRv6 + VietOCR", doc_count=len(groups),
                              text="\n\n".join(doc.page_text(p.uid) for p in doc.pages))
            job.message = f"Phát hiện {len(groups)} văn bản trong {len(doc.pages)} trang"
            return {"doc_id": doc.id, "groups": groups}

        job = self._jobs.submit("split", f"Tách AI · {doc.name}", run, {"doc_id": doc.id})
        return {"job_id": job.id}

    @_safe
    def split_groups(self, doc_id):
        doc = self._doc(doc_id)
        return {"groups": doc.groups, "pages": doc.summary()["pages"],
                "scores": {p.uid: getattr(p, "split_score", None) for p in doc.pages}}

    @_safe
    def split_set(self, doc_id, start_uids, names=None):
        doc = self._doc(doc_id)
        if doc.groups and doc.groups[0].get("meta") is not None or any(p.uid in doc.ocr for p in doc.pages):
            groups = splitter.set_boundaries(doc, start_uids, self._settings.all(), names or {})
        else:   # chia thủ công khi chưa OCR
            starts = set(start_uids)
            groups, cur = [], None
            for p in doc.pages:
                if p.uid in starts or cur is None:
                    cur = {"start_uid": p.uid, "uids": [], "confidence": 100, "reasons": ["Thủ công"],
                           "name": (names or {}).get(p.uid) or f"{os.path.splitext(doc.name)[0]}_Phan_{len(groups) + 1:02d}",
                           "type": "", "agency": ""}
                    groups.append(cur)
                cur["uids"].append(p.uid)
            doc.groups = groups
        return {"groups": groups}

    @_safe
    def export_groups(self, doc_id, groups, fmt="pdf", classify="none", folder=None):
        """Xuất mỗi nhóm thành file riêng. classify: none | type | agency (tạo thư mục con)."""
        doc = self._doc(doc_id)
        folder = folder or self._output_dir(short_stem(doc.name, 60))
        outputs = []
        for g in groups:
            sub = {"type": g.get("type"), "agency": g.get("agency")}.get(classify) or ""
            target_dir = os.path.join(folder, re.sub(r'[\\/:*?"<>|]', "_", sub)) if sub else folder
            name = short_stem((g.get("name") or "Van_ban") + ".x", 120)
            ext = exporters.FORMATS[fmt][1]
            path = unique_path(os.path.join(target_dir, name + ext), self._settings.get("overwrite"))
            exporters.export(fmt, self._export_pages(doc, set(g["uids"])), path, doc)
            outputs.append(path)
        register = self._export_register(doc, groups, folder)
        self._history.add("split", doc.name, doc.path, len(doc.pages), detail=f"Xuất {len(outputs)} văn bản",
                          outputs=outputs + ([register] if register else []), doc_count=len(outputs),
                          text="\n\n".join(doc.page_text(p.uid) for p in doc.pages))
        return {"folder": folder, "outputs": outputs, "register": register}

    def _export_register(self, doc, groups, folder):
        """Ghi sổ danh mục văn bản (Excel) cho các nhóm đã xuất."""
        pos = {p.uid: i + 1 for i, p in enumerate(doc.pages)}
        rows = []
        for g in groups:
            info = g.get("info") or {}
            meta = g.get("meta") or {}
            to_so = info.get("to_so")
            if not to_so:   # không có từ giao diện -> tính từ vị trí trang trong tài liệu
                nums = sorted(pos[u] for u in g.get("uids", []) if u in pos)
                if not nums:
                    to_so = ""
                elif len(nums) == 1:
                    to_so = str(nums[0])
                elif nums[-1] - nums[0] + 1 == len(nums):
                    to_so = f"{nums[0]}-{nums[-1]}"
                else:
                    to_so = ", ".join(map(str, nums))
            rows.append({
                "so": info.get("so_ky_hieu") or meta.get("so_ky_hieu", ""),
                "ngay": info.get("ngay") or meta.get("ngay_ban_hanh", ""),
                "coquan": info.get("co_quan") or meta.get("co_quan") or meta.get("co_quan_viet_tat", ""),
                "trichyeu": info.get("trich_yeu") or meta.get("trich_yeu", ""),
                "to_so": to_so,
                "do_mat": info.get("do_mat") or "Không mật",
                "ghi_chu": info.get("ghi_chu", ""),
            })
        try:
            path = unique_path(os.path.join(folder, "Danh muc van ban.xlsx"), self._settings.get("overwrite"))
            return exporters.export_register(rows, path)
        except Exception:
            return None

    @_safe
    def save_document(self, doc_id, path=None):
        doc = self._doc(doc_id)
        if not path:
            res = self._dialog("save", directory=self._output_dir(), save_filename=os.path.splitext(doc.name)[0] + ".pdf")
            if not res:
                return {"cancelled": True}
            path = res if isinstance(res, str) else res[0]
        path = unique_path(path, self._settings.get("overwrite"))
        doc.save_pages(doc.pages, path)
        self._history.add("pdf", os.path.basename(path), doc.path, len(doc.pages), detail="Lưu PDF đã chỉnh sửa",
                          outputs=[path])
        return {"path": path}

    # ==================================================
    # Xử lý hàng loạt
    # ==================================================
    @_safe
    def batch_start(self, files, task="ocr_docx", opts=None):
        """task: ocr_docx | ocr_searchable_pdf | ocr_txt | ocr_xlsx | pdf | rename
        opts["split"]: none | ai | blank - tách từng file thành nhiều văn bản rồi mới làm tác vụ trên mỗi văn bản.
        rename + tách: xuất các PDF đặt tên theo nội dung, không đổi tên file gốc."""
        opts = opts or {}
        paths = self._expand(files)
        if not paths:
            return {"error": "Chưa có file nào trong hàng đợi"}
        fmt = {"ocr_docx": "docx", "ocr_searchable_pdf": "searchable_pdf", "ocr_txt": "txt",
               "ocr_xlsx": "xlsx"}.get(task, "pdf")
        split = opts.get("split", "none")
        classify = opts.get("classify", "none")
        # Tác vụ pdf chỉ cần OCR khi phải đọc nội dung để tách hoặc phân loại
        need_ocr = task != "pdf" or split == "ai" or (split == "blank" and classify != "none")
        ocr_opts = {"quality": "fast", "engine": "fast", **opts} if task == "pdf" else opts

        def run(job):
            job.items = [{"name": os.path.basename(p), "path": p, "status": "queued", "message": ""} for p in paths]
            out_root = self._output_dir("Hang_loat_" + datetime.datetime.now().strftime("%H%M%S"))
            done = errors = 0
            for i, (path, item) in enumerate(zip(paths, job.items)):
                job.check()
                item["status"] = "running"
                job.update(i / len(paths), f"{i + 1}/{len(paths)} · {item['name']}")
                start = time.time()
                try:
                    doc = Document(path, self._workspace)
                    self._docs[doc.id] = doc

                    class Sub:   # tiến độ con của từng file
                        def update(_, progress=None, message=None):
                            job.update((i + (progress or 0)) / len(paths), message)

                        def check(_):
                            job.check()

                        def check_cancelled(_):
                            job.check_cancelled()
                    sub = Sub()
                    outputs = []
                    if split != "none":
                        self._detect_separators(doc, need_codes=split == "ai", job=job)
                    if need_ocr:   # khi tách: bỏ qua trang trắng và trang mã phân cách
                        todo = [p.uid for p in doc.pages if not p.blank and not p.codes]
                        self._ocr_pages(sub, doc, todo, ocr_opts)
                    if split != "none":
                        if split == "ai":
                            groups = splitter.analyze(doc, self._settings.all())
                        else:
                            plan = self.split_plan(doc.id, "blank")
                            if plan.get("error"):
                                raise RuntimeError(plan["error"])
                            groups = doc.groups
                            if need_ocr:   # đã có OCR: đặt tên và phân loại theo nội dung như khi tách tự động
                                groups = splitter.set_boundaries(doc, [g["start_uid"] for g in groups],
                                                                 self._settings.all())
                        job.check()
                        res = self.export_groups(doc.id, groups, fmt, classify,
                                                 os.path.join(out_root, short_stem(doc.name, 60)))
                        if res.get("error"):
                            raise RuntimeError(res["error"])
                        outputs = res["outputs"]
                        item["message"] = f"{len(outputs)} văn bản"
                    else:
                        if task == "rename":
                            fields = self.doc_metadata(doc.id).get("fields") or {}
                            name = self._file_name(fields)
                            res = self.rename_source(doc.id, name) if name else {"ok": False, "message": "Không đủ thông tin"}
                            if not res.get("ok"):
                                raise RuntimeError(res.get("message"))
                            outputs = [res["path"]]
                            item["message"] = os.path.basename(res["path"])
                        else:
                            out = unique_path(os.path.join(out_root, short_stem(doc.name)
                                                           + exporters.FORMATS[fmt][1]), self._settings.get("overwrite"))
                            exporters.export(fmt, self._export_pages(doc), out, doc)
                            outputs = [out]
                            item["message"] = os.path.basename(out)
                        results = [doc.ocr[p.uid] for p in doc.pages if p.uid in doc.ocr]
                        confs = [r["confidence"] for r in results if r.get("confidence") is not None]
                        self._history.add("batch", doc.name, path, len(doc.pages), "done", time.time() - start,
                                          ", ".join(sorted({r["engine"] for r in results})),
                                          sum(confs) / len(confs) if confs else None, outputs,
                                          text="\n\n".join(doc.page_text(p.uid) for p in doc.pages))
                    item["status"] = "done"
                    item["outputs"] = outputs
                    done += 1
                    self.close_document(doc.id)
                except Cancelled:
                    item["status"] = "cancelled"
                    raise
                except Exception as e:
                    item["status"] = "error"
                    item["message"] = str(e)
                    errors += 1
                    self._history.add("batch", os.path.basename(path), path, 0, "error", time.time() - start,
                                      detail=str(e))
                job.update()
            job.message = f"Hoàn tất {done}/{len(paths)} file" + (f" · {errors} lỗi" if errors else "")
            return {"folder": out_root, "done": done, "errors": errors}

        job = self._jobs.submit("batch", f"Hàng loạt · {len(paths)} file", run, {"task": task, "opts": opts})
        return {"job_id": job.id, "count": len(paths)}

    @_safe
    def batch_retry(self, job_id):
        job = self._jobs.get(job_id)
        if not job:
            return {"error": "Không tìm thấy tác vụ"}
        failed = [it["path"] for it in job.items if it["status"] in ("error", "cancelled", "queued")]
        return self.batch_start(failed, job.meta.get("task", "ocr_docx"), job.meta.get("opts"))

    # ==================================================
    # Lịch sử
    # ==================================================
    @_safe
    def history_search(self, query="", kind="", status="", days=0):
        return self._history.search(query, kind, status, int(days or 0))

    @_safe
    def history_update(self, task_id, fields):
        self._history.update(task_id, **fields)
        return True

    @_safe
    def history_delete(self, task_id, delete_files=False):
        item = self._history.get(task_id)
        if item and delete_files:
            for p in item["outputs"]:
                try:
                    os.remove(p)
                except OSError:
                    pass
        self._history.delete(task_id)
        return True

    @_safe
    def history_move(self, task_id):
        item = self._history.get(task_id)
        target = self.pick_folder()
        if not item or not target:
            return {"cancelled": True}
        moved = []
        for p in item["outputs"]:
            if os.path.exists(p):
                dst = unique_path(os.path.join(target, os.path.basename(p)))
                shutil.move(p, dst)
                moved.append(dst)
        self._history.update(task_id, outputs=moved)
        return {"outputs": moved}

    @_safe
    def history_export_csv(self):
        res = self._dialog("save", directory=self._output_dir(), save_filename="lich_su_xu_ly.csv")
        if not res:
            return {"cancelled": True}
        path = res if isinstance(res, str) else res[0]
        rows = self._history.search(limit=100000)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Thời gian", "Tên tài liệu", "Loại tác vụ", "Số trang", "Trạng thái", "Engine",
                        "Độ tin cậy", "Thời gian xử lý (giây)", "Nhãn", "File đầu ra"])
            for r in rows:
                w.writerow([datetime.datetime.fromtimestamp(r["created"]).strftime("%d/%m/%Y %H:%M"), r["name"],
                            r["kind_label"], r["pages"], r["status"], r["engine"] or "",
                            f"{r['confidence'] * 100:.1f}%" if r["confidence"] else "", round(r["seconds"] or 0, 1),
                            r["tags"], " | ".join(r["outputs"])])
        return {"path": path}

    # ==================================================
    # Mô hình AI
    # ==================================================
    @_safe
    def models(self):
        return {"models": self._ocr.model_status(), "device": self._ocr.device_label() if self._ocr.device else "-",
                "paddle": self._ocr.paddle_available(), "gpus": system.gpu_info(),
                "default_engine": self._settings.get("engine"), "error": self._ocr.import_error}

    @_safe
    def model_load(self, key):
        def run(job):
            ok = self._ocr.load(key, lambda m: job.update(message=m), check_cancel=job.check_cancelled)
            job.message = "Đã nạp mô hình" if ok else "Không nạp được mô hình (thiếu file?)"
            return {"ok": ok}
        job = self._jobs.submit("model", f"Nạp mô hình · {key}", run)
        return {"job_id": job.id}

    @_safe
    def model_unload(self, key):
        self._ocr.unload(key)
        return self.models()

    @_safe
    def model_import(self):
        """Nhập model offline: chọn thư mục model (PaddleX: có inference.yml; VietOCR: có .pth)."""
        folder = self.pick_folder()
        if not folder:
            return {"cancelled": True}
        name = os.path.basename(os.path.normpath(folder))
        files = os.listdir(folder)
        # Model nhập thêm lưu ở thư mục người dùng (thư mục cài đặt trong Program Files chỉ đọc)
        if any(f.endswith(".pth") for f in files) and any(f.endswith((".yml", ".yaml")) for f in files):
            target = config.VIETOCR_DIRS[0]
            os.makedirs(target, exist_ok=True)
            pth = next(f for f in files if f.endswith(".pth"))
            yml = next(f for f in files if f.endswith((".yml", ".yaml")))
            shutil.copy2(os.path.join(folder, pth), os.path.join(target, config.VIETOCR_WEIGHTS_NAME))
            shutil.copy2(os.path.join(folder, yml), os.path.join(target, config.VIETOCR_CONFIG_NAME))
            return {"ok": True, "message": "Đã nhập model VietOCR"}
        if not any(f in files for f in ("inference.yml", "config.json")):
            return {"ok": False, "message": "Thư mục không phải model PaddleX (thiếu inference.yml / config.json)"}
        if config.find_paddlex_model(name):
            return {"ok": False, "message": f"Đã có model {name}"}
        dst = os.path.join(config.PADDLEX_MODEL_DIRS[0], name)
        shutil.copytree(folder, dst)
        return {"ok": True, "message": f"Đã nhập model {name}"}

    # ==================================================
    # Cài đặt
    # ==================================================
    @_safe
    def settings_save(self, values):
        for key in ("doc_type_map", "agency_map"):
            if isinstance(values.get(key), list):   # bỏ dòng rỗng hẳn, giữ dòng đang gõ dở
                rows = [{"ten": str(r.get("ten", "")).strip(), "tat": str(r.get("tat", "")).strip()}
                        for r in values[key] if isinstance(r, dict)]
                values[key] = [r for r in rows if r["ten"] or r["tat"]]
        old_device = self._settings.get("device")
        data = self._settings.update(values)
        if data["device"] != old_device:
            self._ocr.set_device_pref(data["device"])
        return data

    @_safe
    def settings_reset(self):
        return self._settings.reset()

    @_safe
    def settings_backup(self):
        res = self._dialog("save", save_filename="offlineocr_cau_hinh.json")
        if not res:
            return {"cancelled": True}
        path = res if isinstance(res, str) else res[0]
        self._settings.save(path)
        return {"path": path}

    @_safe
    def settings_restore(self):
        res = self._dialog("open", file_types=("Cấu hình (*.json)",))
        if not res:
            return {"cancelled": True}
        return self._settings.restore(res[0])

    @_safe
    def clean_temp(self):
        freed = 0
        open_dirs = {d.cache_dir for d in self._docs.values()}
        for root in (config.WORKSPACE_DIR, os.path.join(config.DATA_DIR, "temp_images")):
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                if any(dirpath.startswith(d) for d in open_dirs):
                    continue
                for f in files:
                    fp = os.path.join(dirpath, f)
                    try:
                        freed += os.path.getsize(fp)
                        os.remove(fp)
                    except OSError:
                        pass
        return {"freed_mb": round(freed / 1048576, 1)}

    @_safe
    def pick_output_dir(self):
        folder = self.pick_folder()
        if folder:
            self._settings.update({"output_dir": folder})
        return folder
