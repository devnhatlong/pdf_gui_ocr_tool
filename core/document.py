# === document.py ===
# Tài liệu nhiều trang trong phiên làm việc: nạp PDF / ảnh, dựng hình trang, sắp xếp / xoay / xóa /
# chèn / thay trang (không sửa file gốc), và ghi ra PDF mới.

import hashlib
import os
import threading
import uuid

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader, PdfWriter

import config

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
SUPPORTED_EXTS = (".pdf",) + IMAGE_EXTS
_pdfium_lock = threading.Lock()     # pdfium không an toàn khi gọi song song nhiều luồng


def _short_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]


def images_to_pdf(path, out_dir):
    """Ảnh (kể cả TIFF nhiều trang) -> PDF tạm để xử lý chung như PDF."""
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, _short_hash(os.path.abspath(path)) + ".pdf")
    img = Image.open(path)
    frames = []
    try:
        for i in range(getattr(img, "n_frames", 1)):
            img.seek(i)
            frames.append(img.convert("RGB"))
    except EOFError:
        pass
    dpi = img.info.get("dpi", (200, 200))[0] or 200
    frames[0].save(out, "PDF", save_all=True, append_images=frames[1:], resolution=float(dpi))
    return out


class Page:
    def __init__(self, src, index, rotation=0):
        self.uid = uuid.uuid4().hex[:12]
        self.src = src            # đường dẫn PDF nguồn
        self.index = index        # số thứ tự trang trong PDF nguồn
        self.rotation = rotation  # góc xoay thêm (theo chiều kim đồng hồ, bội số 90)
        self.blank = None
        self.codes = None

    def to_dict(self):
        return {"uid": self.uid, "rotation": self.rotation, "blank": self.blank, "codes": self.codes or []}


class Document:
    def __init__(self, path, workspace):
        self.id = uuid.uuid4().hex[:12]
        self.path = os.path.abspath(path)
        self.name = os.path.basename(path)
        self.workspace = workspace
        self.cache_dir = os.path.join(workspace, self.id)
        os.makedirs(self.cache_dir, exist_ok=True)
        src = self.path
        if self.path.lower().endswith(IMAGE_EXTS):
            src = images_to_pdf(self.path, self.cache_dir)
        with _pdfium_lock:
            pdf = pdfium.PdfDocument(src)
            count = len(pdf)
            pdf.close()
        self.pages = [Page(src, i) for i in range(count)]
        self.ocr = {}        # uid trang -> kết quả OCR (dict)
        self.edits = {}      # uid trang -> văn bản đã sửa
        self.ocr_images = {} # uid trang -> ảnh đã tiền xử lý dùng để OCR (khung tọa độ khớp ảnh này)
        self.groups = []     # kết quả tách văn bản AI
        self.meta = {}

    # --- dựng hình ---
    def page(self, uid):
        for p in self.pages:
            if p.uid == uid:
                return p
        raise KeyError(uid)

    def render(self, page, dpi=200):
        """Ảnh trang (đã xoay theo page.rotation), có cache trên đĩa."""
        key = f"{_short_hash(page.src)}_{page.index}_{dpi}_{page.rotation}.png"
        path = os.path.join(self.cache_dir, key)
        if os.path.exists(path):
            return Image.open(path), path
        with _pdfium_lock:
            pdf = pdfium.PdfDocument(page.src)
            try:
                bitmap = pdf[page.index].render(scale=dpi / 72, rotation=page.rotation % 360)
                img = bitmap.to_pil().convert("RGB")
            finally:
                pdf.close()
        if dpi >= 150:
            img.save(path)
        return img, path

    def thumbnail(self, page, max_side=260):
        from core.imaging import to_data_url
        img, _ = self.render(page, dpi=48)
        return to_data_url(img, max_side=max_side, quality=75)

    # --- thao tác trang ---
    def rotate(self, uid, degrees):
        p = self.page(uid)
        p.rotation = (p.rotation + degrees) % 360
        self.ocr.pop(uid, None)
        self.ocr_images.pop(uid, None)

    def delete(self, uids):
        self.pages = [p for p in self.pages if p.uid not in set(uids)]

    def move(self, uid, new_index):
        p = self.page(uid)
        self.pages.remove(p)
        self.pages.insert(max(0, min(new_index, len(self.pages))), p)

    def reorder(self, uids):
        by_uid = {p.uid: p for p in self.pages}
        self.pages = [by_uid[u] for u in uids if u in by_uid] + [p for p in self.pages if p.uid not in set(uids)]

    def reverse(self):
        self.pages.reverse()

    def insert_from(self, other, position, uids=None):
        """Chèn trang của tài liệu khác vào vị trí position (giữ góc xoay)."""
        pages = [Page(p.src, p.index, p.rotation) for p in other.pages if uids is None or p.uid in uids]
        self.pages[position:position] = pages
        return pages

    def replace_page(self, uid, other_page):
        i = self.pages.index(self.page(uid))
        new = Page(other_page.src, other_page.index, other_page.rotation)
        self.pages[i] = new
        self.ocr.pop(uid, None)
        return new

    # --- ghi file ---
    def save_pages(self, pages, out_path):
        """Ghi các trang (theo thứ tự, đã xoay) ra file PDF mới."""
        writer = PdfWriter()
        readers = {}
        for p in pages:
            reader = readers.get(p.src) or readers.setdefault(p.src, PdfReader(p.src))
            writer.add_page(reader.pages[p.index])
            if p.rotation:
                writer.pages[-1].rotate(p.rotation)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "wb") as f:
            writer.write(f)
        return out_path

    def page_text(self, uid):
        if uid in self.edits:
            return self.edits[uid]
        return (self.ocr.get(uid) or {}).get("text", "")

    def summary(self):
        return {"id": self.id, "name": self.name, "path": self.path, "page_count": len(self.pages),
                "pages": [p.to_dict() | {"ocr": p.uid in self.ocr, "edited": p.uid in self.edits}
                          for p in self.pages]}


def unique_path(path, overwrite=False):
    """Tránh ghi đè: thêm (1), (2)... nếu file đã tồn tại."""
    if overwrite or not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def new_workspace():
    path = os.path.join(config.WORKSPACE_DIR, "session")
    os.makedirs(path, exist_ok=True)
    return path
