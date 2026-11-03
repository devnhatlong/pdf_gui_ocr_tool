# === ocr_engine.py ===
# Bộ máy OCR chạy offline, gồm các chế độ:
#   - "fast"      : PP-OCRv6 Medium phát hiện dòng chữ + VietOCR nhận dạng tiếng Việt (mặc định).
#                   Bộ ký tự nhận dạng của PP-OCRv6 thiếu các chữ như ạ, ả, ế, ộ, ữ... nên tiếng Việt
#                   có dấu do VietOCR đọc; PP-OCRv6 rec chỉ dùng khi chưa có model VietOCR.
#   - "structure" : PP-StructureV3 — tách bảng, khối chữ, thứ tự đọc (chỉ bật module cần thiết),
#                   chữ trong kết quả được VietOCR đọc lại để giữ đúng dấu tiếng Việt.
#   - "vl"        : PaddleOCR-VL 1.6 — bảng phức tạp, nhiều cột, công thức. Rất nặng (CPU ~ vài phút/trang),
#                   xử lý lần lượt từng tài liệu và giải phóng bộ nhớ sau khi dùng.
# Nếu chưa cài Paddle / chưa có model thì tự dùng Tesseract để phần mềm vẫn chạy được.
#
# Model nằm ở thư mục models/ (xem config.py, tải 1 lần bằng download_models.py).

import gc
import os
import re
import threading
import time
from dataclasses import dataclass, field

from PIL import Image

import config

# Phải đặt biến môi trường trước khi import paddleocr. download_models.py đặt OCR_MODEL_DOWNLOAD=1 để được tải model.
config.apply_model_env(offline=os.environ.get("OCR_MODEL_DOWNLOAD") != "1")

MODES = {
    "fast": "Nhanh — PP-OCRv6 + VietOCR",
    "structure": "Bố cục — PP-StructureV3",
    "vl": "Nâng cao — PaddleOCR-VL 1.6",
}
MODE_HINTS = {
    "fast": "Văn bản hành chính, chữ in. Nhanh nhất.",
    "structure": "Tài liệu có bảng biểu, nhiều khối chữ.",
    "vl": "Bảng phức tạp, nhiều cột, công thức. Rất chậm nếu không có GPU.",
}
DEFAULT_MODE = "fast"

# Không bỏ dòng tiêu đề đầu trang (cơ quan ban hành, số ký hiệu) khỏi Markdown — cần cho việc đặt tên file
MARKDOWN_IGNORE_LABELS = ["number", "footer", "footer_image", "header_image"]
VIETOCR_MIN_PROB = 0.35   # dòng VietOCR đọc dưới mức này coi là nhiễu (vết bẩn, con dấu...)


@dataclass
class OcrResult:
    text: str                      # văn bản thuần, mỗi hàng 1 dòng (dùng để trích xuất thông tin)
    engine: str                    # tên engine đã dùng
    markdown: str = ""             # kết quả có cấu trúc (bảng, tiêu đề) của chế độ structure / vl
    seconds: float = 0.0
    notes: list = field(default_factory=list)


# ==================================================
# Khởi tạo model (dùng chung cho phần mềm và download_models.py)
# ==================================================
def detect_device():
    """gpu:0 nếu Paddle có CUDA và máy có card NVIDIA, ngược lại cpu."""
    try:
        import paddle
        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu:0"
    except Exception:
        pass
    return "cpu"


def build_detector(device):
    from paddleocr import TextDetection
    return TextDetection(model_name=config.PPOCR_DET_MODEL, device=device)


def build_ppocr(device):
    from paddleocr import PaddleOCR
    return PaddleOCR(
        text_detection_model_name=config.PPOCR_DET_MODEL,
        text_recognition_model_name=config.PPOCR_REC_MODEL,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device=device,
    )


def build_structure(device):
    from paddleocr import PPStructureV3
    # Chỉ bật phần cần thiết: bố cục + bảng. Tắt công thức, con dấu, biểu đồ để tiết kiệm bộ nhớ.
    return PPStructureV3(
        text_detection_model_name=config.PPOCR_DET_MODEL,
        text_recognition_model_name=config.PPOCR_REC_MODEL,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        use_table_recognition=True,
        use_formula_recognition=False,
        use_seal_recognition=False,
        use_chart_recognition=False,
        use_region_detection=True,
        markdown_ignore_labels=MARKDOWN_IGNORE_LABELS,
        device=device,
    )


def build_vl(device):
    from paddleocr import PaddleOCRVL
    return PaddleOCRVL(
        pipeline_version=config.VL_PIPELINE_VERSION,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        markdown_ignore_labels=MARKDOWN_IGNORE_LABELS,
        device=device,
    )


def vietocr_config():
    """Đọc config VietOCR từ file cục bộ (không tải từ mạng)."""
    from vietocr.tool.config import Cfg
    cfg = Cfg.load_config_from_file(config.VIETOCR_CONFIG)
    cfg["weights"] = config.VIETOCR_WEIGHTS
    cfg["device"] = "cpu"
    cfg["cnn"]["pretrained"] = False      # không tải trọng số VGG gốc của torchvision
    cfg["predictor"]["beamsearch"] = False
    return cfg


class VietRecognizer:
    """VietOCR nhận dạng từng dòng chữ tiếng Việt (ảnh cắt theo khung PP-OCRv6 phát hiện)."""

    BATCH = 32

    def __init__(self):
        import torch
        from vietocr.tool.predictor import Predictor
        # Dùng quá nhiều luồng trên CPU nhiều nhân lại chậm hơn (đo thực tế: 20 luồng 15s, 12 luồng 2.7s)
        self._threads = max(2, min(12, (os.cpu_count() or 4) * 3 // 5))
        self._torch = torch
        self.predictor = Predictor(vietocr_config())
        self.predictor.model.eval()

    def recognize(self, crops):
        texts, probs = [], []
        # Paddle đổi cấu hình luồng OpenMP dùng chung -> đặt lại mỗi lần, nếu không VietOCR chậm gần 3 lần
        self._torch.set_num_threads(self._threads)
        with self._torch.inference_mode():
            for i in range(0, len(crops), self.BATCH):
                t, p = self.predictor.predict_batch(crops[i:i + self.BATCH], return_prob=True)
                texts += [s.strip() for s in t]
                probs += [float(x) for x in p]
        return texts, probs


# ==================================================
# Xử lý kết quả
# ==================================================
def _as_list(value):
    if value is None:
        return []
    return value.tolist() if hasattr(value, "tolist") else list(value)


def poly_to_box(poly):
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def crop_lines(image, boxes):
    crops = []
    for x1, y1, x2, y2 in boxes:
        pad = max(2, int((y2 - y1) / 8))
        crops.append(image.crop((max(0, int(x1) - pad), max(0, int(y1) - pad),
                                 min(image.width, int(x2) + pad), min(image.height, int(y2) + pad))))
    return crops


def group_lines(texts, boxes):
    """Gộp các ô chữ nằm trên cùng một hàng (VD: "Số: 12/BC" ... "Lâm Đồng, ngày ..."),
    sắp theo thứ tự đọc từ trên xuống, trái sang phải."""
    items = []
    for text, box in zip(texts, boxes):
        if text and str(text).strip():
            items.append((str(text).strip(), [float(v) for v in box[:4]]))
    items.sort(key=lambda it: (it[1][1] + it[1][3]) / 2)

    rows = []
    for text, (x1, y1, x2, y2) in items:
        for row in rows:
            overlap = min(y2, row["y2"]) - max(y1, row["y1"])
            if overlap > 0.5 * min(y2 - y1, row["y2"] - row["y1"]):
                row["items"].append((x1, text))
                row["y1"], row["y2"] = min(row["y1"], y1), max(row["y2"], y2)
                break
        else:
            rows.append({"y1": y1, "y2": y2, "items": [(x1, text)]})
    rows.sort(key=lambda r: r["y1"])
    return ["   ".join(t for _, t in sorted(r["items"])) for r in rows]


def replace_in_order(md, pairs):
    """Thay lần lượt từng dòng chữ cũ bằng chữ mới trong Markdown, theo đúng thứ tự xuất hiện."""
    pos = 0
    for old, new in pairs:
        if not old or not new or old == new:
            continue
        idx = md.find(old, pos)
        if idx < 0:
            idx = md.find(old)
            if idx < 0:
                continue
        md = md[:idx] + new + md[idx + len(old):]
        pos = idx + len(new)
    return md


def markdown_to_plain(md):
    """Bỏ ký hiệu Markdown/HTML để dùng cho phần trích xuất thông tin văn bản."""
    text = re.sub(r"</(td|th)>", "   ", md)
    text = re.sub(r"</tr>|<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"(\*\*|__|`|\$)", "", text)
    text = re.sub(r"^\s*\|?[\s:\-|]+\|?\s*$", "", text, flags=re.M)   # dòng kẻ bảng |---|
    text = text.replace("|", "   ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _markdown_of(res):
    md = getattr(res, "markdown", None)
    if isinstance(md, dict):
        value = md.get("markdown_texts")
        if isinstance(value, str):
            return value
    return md if isinstance(md, str) else ""


# ==================================================
# Dịch vụ OCR (giữ model trong bộ nhớ, nạp khi cần)
# ==================================================
class OcrService:
    def __init__(self):
        self._lock = threading.Lock()
        self._models = {}
        self._viet = None
        self._viet_error = None
        self.device = None

    # --- trạng thái ---
    import_error = None   # lỗi import PaddleOCR (nếu có) — chỉ thử import 1 lần
    _paddle_ok = None

    @classmethod
    def paddle_available(cls):
        if cls._paddle_ok is None:
            try:
                import paddleocr  # noqa: F401
                cls._paddle_ok = True
            except Exception:
                import traceback
                cls._paddle_ok = False
                cls.import_error = traceback.format_exc()
        return cls._paddle_ok

    @staticmethod
    def models_ready(mode):
        root = os.path.join(config.PADDLEX_HOME, "official_models")
        need = {
            "fast": [config.PPOCR_DET_MODEL],
            "structure": [config.PPOCR_DET_MODEL, config.PPOCR_REC_MODEL, "PP-DocLayout_plus-L"],
            "vl": ["PaddleOCR-VL-1.6", "PP-DocLayoutV3"],
        }[mode]
        return all(os.path.isdir(os.path.join(root, n)) for n in need)

    @staticmethod
    def vietocr_ready():
        return os.path.exists(config.VIETOCR_CONFIG) and os.path.exists(config.VIETOCR_WEIGHTS)

    def get_device(self):
        if self.device is None:
            self.device = detect_device()
        return self.device

    def device_label(self):
        return "GPU" if self.get_device().startswith("gpu") else "CPU"

    # --- nạp / giải phóng ---
    def _model(self, name, progress):
        if name in self._models:
            return self._models[name]
        # PaddleOCR-VL rất nặng: chỉ giữ 1 pipeline lớn trong bộ nhớ tại một thời điểm
        if name == "vl":
            self.release(keep=("det",))
        elif "vl" in self._models:
            self.release(keep=("det", "rec", "structure"))
        labels = {"det": "PP-OCRv6", "rec": "PP-OCRv6", "structure": "PP-StructureV3", "vl": "PaddleOCR-VL 1.6"}
        progress(f"Đang nạp mô hình {labels[name]} ({self.device_label()}) — lần đầu có thể mất một lúc")
        builder = {"det": build_detector, "rec": build_ppocr, "structure": build_structure, "vl": build_vl}[name]
        self._models[name] = builder(self.get_device())
        return self._models[name]

    def release(self, keep=("det",)):
        """Giải phóng các model không cần nữa (giảm RAM / VRAM)."""
        for name in list(self._models):
            if name not in keep:
                del self._models[name]
        gc.collect()
        try:
            import paddle
            if paddle.device.is_compiled_with_cuda():
                paddle.device.cuda.empty_cache()
        except Exception:
            pass

    def _vietocr(self, progress):
        if self._viet is None and self._viet_error is None and self.vietocr_ready():
            progress("Đang nạp mô hình VietOCR")
            try:
                self._viet = VietRecognizer()
            except Exception:
                import traceback
                self._viet_error = traceback.format_exc()
        return self._viet

    def warmup(self, progress=lambda msg: None):
        """Nạp sẵn model của chế độ mặc định khi mở phần mềm. Trả về tên engine sẽ dùng."""
        with self._lock:
            if not self.paddle_available() or not self.models_ready("fast"):
                return "Tesseract"
            try:
                viet = self._vietocr(progress)
                self._model("det" if viet else "rec", progress)
                return "PP-OCRv6 + VietOCR" if viet else "PP-OCRv6"
            except Exception:
                return "Tesseract"

    # --- nhận dạng ---
    def recognize(self, image_path, mode=DEFAULT_MODE, progress=lambda msg: None):
        start = time.time()
        with self._lock:
            if not self.paddle_available():
                result = self._tesseract(image_path)
                result.notes.append("Chưa cài PaddleOCR — đang dùng Tesseract")
            elif not self.models_ready(mode):
                result = self._tesseract(image_path)
                result.notes.append(f"Chưa có mô hình cho chế độ \"{MODES[mode]}\" — "
                                    "chạy download_models.py để tải về. Đang dùng Tesseract")
            else:
                try:
                    if mode == "fast":
                        result = self._run_fast(image_path, progress)
                    else:
                        result = self._run_document(image_path, mode, progress)
                except Exception as e:
                    self.release(keep=("det",) if mode != "fast" else ())
                    result = self._tesseract(image_path)
                    result.notes.append(f"{MODES[mode]} gặp lỗi ({e}) — đã chuyển sang Tesseract")
        result.seconds = time.time() - start
        return result

    def _run_fast(self, image_path, progress):
        viet = self._vietocr(progress)
        if viet is None:
            # Chưa có VietOCR: dùng nguyên PP-OCRv6 (tiếng Việt có thể mất một số dấu)
            pipeline = self._model("rec", progress)
            progress("Đang nhận dạng bằng PP-OCRv6")
            res = next(iter(pipeline.predict(image_path)))
            lines = group_lines(_as_list(res["rec_texts"]), _as_list(res["rec_boxes"]))
            return OcrResult(text="\n".join(lines), engine="PP-OCRv6",
                             notes=["Chưa có VietOCR — chữ tiếng Việt có thể bị mất dấu"])

        detector = self._model("det", progress)
        progress("PP-OCRv6 đang tìm các dòng chữ")
        res = next(iter(detector.predict(image_path)))
        boxes = [poly_to_box(p) for p in _as_list(res["dt_polys"])]
        if not boxes:
            return OcrResult(text="", engine="PP-OCRv6 + VietOCR")
        progress(f"VietOCR đang đọc {len(boxes)} dòng chữ")
        image = Image.open(image_path).convert("RGB")
        texts, probs = viet.recognize(crop_lines(image, boxes))
        kept = [(t, b) for t, p, b in zip(texts, probs, boxes) if t and p >= VIETOCR_MIN_PROB]
        lines = group_lines([t for t, _ in kept], [b for _, b in kept])
        return OcrResult(text="\n".join(lines), engine="PP-OCRv6 + VietOCR")

    def _run_document(self, image_path, mode, progress):
        pipeline = self._model(mode, progress)
        name = "PaddleOCR-VL 1.6" if mode == "vl" else "PP-StructureV3"
        if mode == "vl" and self.device_label() == "CPU":
            progress(f"{name} đang phân tích tài liệu trên CPU — có thể mất vài phút")
        else:
            progress(f"{name} đang phân tích tài liệu")
        res = next(iter(pipeline.predict(image_path)))
        md = _markdown_of(res)
        notes = []

        if mode == "structure":
            # Chữ do PP-OCRv6 đọc bị thiếu dấu tiếng Việt -> VietOCR đọc lại từng dòng rồi thay vào
            ocr = res["overall_ocr_res"]
            old_texts = [str(t) for t in _as_list(ocr["rec_texts"])]
            boxes = [[float(v) for v in b[:4]] for b in _as_list(ocr["rec_boxes"])]
            texts = old_texts
            viet = self._vietocr(progress)
            if viet is not None and boxes:
                progress(f"VietOCR đang đọc lại {len(boxes)} dòng chữ")
                image = Image.open(image_path).convert("RGB")
                new_texts, probs = viet.recognize(crop_lines(image, boxes))
                texts = [n if n and p >= VIETOCR_MIN_PROB else o
                         for o, n, p in zip(old_texts, new_texts, probs)]
                md = replace_in_order(md, list(zip(old_texts, texts)))
                name += " + VietOCR"
            else:
                notes.append("Chưa có VietOCR — chữ tiếng Việt có thể bị mất dấu")
            text = "\n".join(group_lines(texts, boxes))
        else:
            text = markdown_to_plain(md)
            self.release(keep=("det", "vl"))  # dọn bộ nhớ tạm sau mỗi tài liệu
        return OcrResult(text=text, engine=name, markdown=md, notes=notes)

    @staticmethod
    def _tesseract(image_path):
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH
        text = pytesseract.image_to_string(Image.open(image_path), lang=config.LANG)
        return OcrResult(text=text, engine="Tesseract")


def extract_text_from_image(image_path):
    """Giữ tương thích với code cũ: trả về văn bản thuần."""
    return OcrService().recognize(image_path).text
