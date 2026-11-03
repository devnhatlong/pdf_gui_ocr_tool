# === ocr_engine.py ===
# Bộ máy OCR chạy offline:
#   - PP-OCRv6 Medium phát hiện dòng chữ + VietOCR nhận dạng tiếng Việt (mặc định, nhanh).
#     Bộ ký tự nhận dạng của PP-OCRv6 thiếu các chữ như ạ, ả, ế, ộ, ữ... nên tiếng Việt có dấu do
#     VietOCR đọc; PP-OCRv6 rec chỉ dùng khi chưa có model VietOCR.
#   - PP-StructureV3 - tách bảng, khối chữ, thứ tự đọc (chỉ bật module cần thiết); chữ được VietOCR đọc lại.
#   - PaddleOCR-VL 1.6 - bảng phức tạp, nhiều cột, công thức. Rất nặng (CPU ~ vài phút/trang),
#     chỉ giữ 1 model lớn trong bộ nhớ và giải phóng khi chuyển chế độ (phù hợp GPU 8 GB).
# Nếu chưa cài Paddle / chưa có model thì tự dùng Tesseract để phần mềm vẫn chạy được.
# Model nằm ở thư mục models/ (xem config.py, tải 1 lần bằng download_models.py).

import gc
import os
import re
import threading
import time
import traceback
from dataclasses import dataclass, field

from PIL import Image

import config

# Phải đặt biến môi trường trước khi import paddleocr. download_models.py đặt OCR_MODEL_DOWNLOAD=1 để được tải model.
config.apply_model_env(offline=os.environ.get("OCR_MODEL_DOWNLOAD") != "1")

# Model người dùng chọn được trên giao diện
ENGINES = {
    "auto": "Tự động chọn model",
    "fast": "PP-OCRv6 + VietOCR",
    "structure": "PP-StructureV3",
    "vl": "PaddleOCR-VL 1.6",
}
# Chế độ chất lượng: Nhanh / Tự động / Chính xác
QUALITY = {"fast": "Nhanh", "auto": "Tự động", "accurate": "Chính xác"}

# Không bỏ dòng tiêu đề đầu trang (cơ quan ban hành, số ký hiệu) khỏi Markdown - cần cho việc đặt tên file
MARKDOWN_IGNORE_LABELS = ["number", "footer", "footer_image", "header_image"]
VIETOCR_MIN_PROB = 0.35   # dòng VietOCR đọc dưới mức này coi là nhiễu (vết bẩn, con dấu...)

# Thông tin model hiển thị ở màn hình "Quản lý mô hình"
MODEL_INFO = [
    {"key": "det", "name": "PP-OCRv6 Medium", "desc": "Phát hiện dòng chữ, đa ngôn ngữ",
     "dirs": ["PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"], "icon": "zap"},
    {"key": "viet", "name": "VietOCR", "desc": "Nhận dạng tiếng Việt có dấu, chữ in và chữ viết tay",
     "dirs": [], "icon": "languages"},
    {"key": "structure", "name": "PP-StructureV3", "desc": "Bố cục, bảng biểu, thứ tự đọc",
     "dirs": ["PP-DocLayout_plus-L", "PP-DocBlockLayout", "SLANeXt_wired", "SLANet_plus",
              "PP-LCNet_x1_0_table_cls", "RT-DETR-L_wired_table_cell_det",
              "RT-DETR-L_wireless_table_cell_det", "PP-LCNet_x1_0_textline_ori"], "icon": "layout-template"},
    {"key": "vl", "name": "PaddleOCR-VL 1.6", "desc": "Tài liệu phức tạp: bảng, nhiều cột, công thức",
     "dirs": ["PaddleOCR-VL-1.6", "PP-DocLayoutV3"], "icon": "brain-circuit"},
    {"key": "ori", "name": "PP-LCNet Doc Orientation", "desc": "Tự xoay hướng trang 0°/90°/180°/270°",
     "dirs": ["PP-LCNet_x1_0_doc_ori"], "icon": "rotate-cw"},
]


@dataclass
class OcrResult:
    text: str                      # văn bản thuần theo thứ tự đọc (dùng để trích xuất thông tin)
    engine: str                    # tên engine đã dùng
    markdown: str = ""             # kết quả có cấu trúc (bảng, tiêu đề) của PP-StructureV3 / VL
    lines: list = field(default_factory=list)    # [{text, box:[x1,y1,x2,y2], score}]
    blocks: list = field(default_factory=list)   # [{label, box, content}] - vùng bố cục
    size: tuple = (0, 0)           # kích thước ảnh đã nhận dạng (px)
    seconds: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def confidence(self):
        scores = [ln["score"] for ln in self.lines if ln.get("score") is not None]
        return sum(scores) / len(scores) if scores else None

    def to_dict(self):
        return {"text": self.text, "engine": self.engine, "markdown": self.markdown, "lines": self.lines,
                "blocks": self.blocks, "size": list(self.size), "seconds": round(self.seconds, 2),
                "notes": self.notes, "confidence": self.confidence}


# ==================================================
# Khởi tạo model (dùng chung cho phần mềm và download_models.py)
# ==================================================
def detect_device(prefer="auto"):
    """gpu:0 nếu Paddle có CUDA và máy có card NVIDIA (và người dùng không chọn CPU), ngược lại cpu."""
    if prefer == "cpu":
        return "cpu"
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


def build_orientation(device):
    from paddleocr import DocImgOrientationClassification
    return DocImgOrientationClassification(model_name="PP-LCNet_x1_0_doc_ori", device=device)


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
    return [min(xs), min(ys), max(xs), max(ys)]


def crop_lines(image, boxes):
    crops = []
    for x1, y1, x2, y2 in boxes:
        pad = max(2, int((y2 - y1) / 8))
        crops.append(image.crop((max(0, int(x1) - pad), max(0, int(y1) - pad),
                                 min(image.width, int(x2) + pad), min(image.height, int(y2) + pad))))
    return crops


def reading_order(lines):
    """Gộp các ô chữ nằm trên cùng một hàng (VD: "Số: 12/BC" ... "Lâm Đồng, ngày ..."),
    sắp theo thứ tự đọc từ trên xuống, trái sang phải. Trả về (các dòng đã sắp, văn bản)."""
    items = sorted((ln for ln in lines if ln["text"].strip()), key=lambda ln: (ln["box"][1] + ln["box"][3]) / 2)
    rows = []
    for ln in items:
        x1, y1, x2, y2 = ln["box"]
        for row in rows:
            overlap = min(y2, row["y2"]) - max(y1, row["y1"])
            if overlap > 0.5 * min(y2 - y1, row["y2"] - row["y1"]):
                row["items"].append(ln)
                row["y1"], row["y2"] = min(row["y1"], y1), max(row["y2"], y2)
                break
        else:
            rows.append({"y1": y1, "y2": y2, "items": [ln]})
    rows.sort(key=lambda r: r["y1"])
    ordered, text_rows = [], []
    for row in rows:
        row["items"].sort(key=lambda ln: ln["box"][0])
        ordered += row["items"]
        text_rows.append("   ".join(ln["text"] for ln in row["items"]))
    return ordered, "\n".join(text_rows)


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


def _blocks_of(res):
    blocks = []
    for b in res.get("parsing_res_list", None) or []:
        label = getattr(b, "label", None)
        bbox = getattr(b, "bbox", None)
        if label is None or bbox is None:
            continue
        blocks.append({"label": str(label), "box": [float(v) for v in bbox[:4]],
                       "content": str(getattr(b, "content", "") or "")})
    return blocks


def _cluster(values, tol):
    edges = []
    for v in sorted(values):
        if not edges or v - edges[-1][-1] > tol:
            edges.append([v])
        else:
            edges[-1].append(v)
    return [sum(e) / len(e) for e in edges]


def rebuild_table(cell_boxes, lines):
    """Dựng lại bảng HTML từ tọa độ ô (PP-StructureV3) + chữ OCR nằm trong từng ô.
    Mô hình bảng đôi khi trả thứ tự ô bị đảo; tọa độ ô thì đáng tin hơn."""
    cells = [[float(v) for v in b[:4]] for b in cell_boxes]
    if not cells:
        return ""
    min_h = min(c[3] - c[1] for c in cells) or 1
    min_w = min(c[2] - c[0] for c in cells) or 1
    ys = _cluster([c[1] for c in cells] + [c[3] for c in cells], min_h * 0.4)
    xs = _cluster([c[0] for c in cells] + [c[2] for c in cells], min_w * 0.4)

    def idx(edges, v):
        return min(range(len(edges)), key=lambda i: abs(edges[i] - v))

    grid = {}
    for c in cells:
        r0, r1 = idx(ys, c[1]), idx(ys, c[3])
        c0, c1 = idx(xs, c[0]), idx(xs, c[2])
        if r1 <= r0 or c1 <= c0:
            continue
        inside = [ln for ln in lines
                  if c[0] <= (ln["box"][0] + ln["box"][2]) / 2 <= c[2] and c[1] <= (ln["box"][1] + ln["box"][3]) / 2 <= c[3]]
        _, text = reading_order(inside)
        grid[(r0, c0)] = (r1 - r0, c1 - c0, text.replace("\n", " "))
    covered, rows = set(), []
    for r in range(len(ys) - 1):
        tds = []
        for c in range(len(xs) - 1):
            if (r, c) in covered:
                continue
            if (r, c) in grid:
                rs, cs, text = grid[(r, c)]
                for dr in range(rs):
                    for dc in range(cs):
                        covered.add((r + dr, c + dc))
                span = (f' rowspan="{rs}"' if rs > 1 else "") + (f' colspan="{cs}"' if cs > 1 else "")
                tds.append(f"<td{span}>{html_escape(text)}</td>")
            else:
                tds.append("<td></td>")
        if tds:
            rows.append("<tr>" + "".join(tds) + "</tr>")
    return "<table border=\"1\">" + "".join(rows) + "</table>"


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def has_table_lines(image):
    """Ước lượng nhanh trang có bảng kẻ ô hay không (dùng cho chế độ Tự động)."""
    try:
        import cv2
        import numpy as np
        gray = np.array(image.convert("L"))
        scale = 1000 / max(gray.shape)
        if scale < 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale)
        bw = cv2.adaptiveThreshold(~gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)
        h, w = bw.shape
        horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 12), 1)))
        vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 25))))
        joints = cv2.bitwise_and(horiz, vert)
        n_joints = cv2.connectedComponents(joints)[0] - 1
        return n_joints >= 6
    except Exception:
        return False


# ==================================================
# Dịch vụ OCR (giữ model trong bộ nhớ, nạp khi cần)
# ==================================================
class OcrService:
    import_error = None   # lỗi import PaddleOCR (nếu có) - chỉ thử import 1 lần
    _paddle_ok = None

    def __init__(self, device_pref="auto"):
        self._lock = threading.RLock()
        self._models = {}
        self._loaded_at = {}
        self._viet = None
        self._viet_error = None
        self.device_pref = device_pref
        self.device = None

    # --- trạng thái ---
    @classmethod
    def paddle_available(cls):
        if cls._paddle_ok is None:
            try:
                import paddleocr  # noqa: F401
                cls._paddle_ok = True
            except Exception:
                cls._paddle_ok = False
                cls.import_error = traceback.format_exc()
        return cls._paddle_ok

    @staticmethod
    def model_dir(name):
        return os.path.join(config.PADDLEX_HOME, "official_models", name)

    @classmethod
    def models_ready(cls, engine):
        need = {
            "fast": [config.PPOCR_DET_MODEL],
            "structure": [config.PPOCR_DET_MODEL, config.PPOCR_REC_MODEL, "PP-DocLayout_plus-L"],
            "vl": ["PaddleOCR-VL-1.6", "PP-DocLayoutV3"],
            "ori": ["PP-LCNet_x1_0_doc_ori"],
        }[engine]
        return all(os.path.isdir(cls.model_dir(n)) for n in need)

    @staticmethod
    def vietocr_ready():
        return os.path.exists(config.VIETOCR_CONFIG) and os.path.exists(config.VIETOCR_WEIGHTS)

    def get_device(self):
        if self.device is None:
            self.device = detect_device(self.device_pref) if self.paddle_available() else "cpu"
        return self.device

    def set_device_pref(self, pref):
        with self._lock:
            if pref != self.device_pref:
                self.device_pref = pref
                self.device = None
                self.release(keep=())

    def device_label(self):
        return "GPU" if self.get_device().startswith("gpu") else "CPU"

    def model_status(self):
        """Thông tin model cho màn hình Quản lý mô hình."""
        out = []
        for info in MODEL_INFO:
            if info["key"] == "viet":
                paths = [config.VIETOCR_DIR]
                ready = self.vietocr_ready()
                loaded = self._viet is not None
            else:
                paths = [self.model_dir(d) for d in info["dirs"]]
                ready = all(os.path.isdir(p) for p in paths)
                keys = {"det": ("det", "rec"), "structure": ("structure",), "vl": ("vl",), "ori": ("ori",)}[info["key"]]
                loaded = any(k in self._models for k in keys)
            size = 0
            for p in paths:
                for root, _, files in os.walk(p):
                    size += sum(os.path.getsize(os.path.join(root, f)) for f in files)
            out.append({**{k: info[k] for k in ("key", "name", "desc", "icon")},
                        "ready": ready, "loaded": loaded, "size_mb": round(size / 1048576)})
        return out

    # --- nạp / giải phóng ---
    def _model(self, name, progress):
        if name in self._models:
            return self._models[name]
        # Chỉ giữ 1 pipeline lớn (PP-StructureV3 hoặc PaddleOCR-VL) trong bộ nhớ - vừa GPU 8 GB
        if name == "vl":
            self.release(keep=("det", "ori"))
        elif name == "structure" and "vl" in self._models:
            self.release(keep=("det", "rec", "ori"))
        labels = {"det": "PP-OCRv6", "rec": "PP-OCRv6", "structure": "PP-StructureV3",
                  "vl": "PaddleOCR-VL 1.6", "ori": "xoay hướng trang"}
        progress(f"Đang nạp mô hình {labels[name]} ({self.device_label()}) - lần đầu có thể mất một lúc")
        builder = {"det": build_detector, "rec": build_ppocr, "structure": build_structure,
                   "vl": build_vl, "ori": build_orientation}[name]
        self._models[name] = builder(self.get_device())
        self._loaded_at[name] = time.time()
        return self._models[name]

    def load(self, key, progress=lambda msg: None):
        """Nạp model theo yêu cầu từ màn hình Quản lý mô hình."""
        with self._lock:
            if key == "viet":
                return self._vietocr(progress) is not None
            if not self.paddle_available():
                return False
            self._model(key if key != "det" else "det", progress)
            return True

    def unload(self, key):
        with self._lock:
            if key == "viet":
                self._viet = None
                gc.collect()
                return
            keys = {"det": ("det", "rec")}.get(key, (key,))
            self.release(keep=tuple(k for k in self._models if k not in keys))

    def release(self, keep=("det",)):
        """Giải phóng các model không cần nữa (giảm RAM / VRAM)."""
        for name in list(self._models):
            if name not in keep:
                del self._models[name]
                self._loaded_at.pop(name, None)
        gc.collect()
        try:
            import paddle
            if paddle.device.is_compiled_with_cuda():
                paddle.device.cuda.empty_cache()
        except Exception:
            pass

    def _vietocr(self, progress):
        if self._viet is None and self.vietocr_ready():
            progress("Đang nạp mô hình VietOCR")
            try:
                self._viet = VietRecognizer()
                self._viet_error = None
            except Exception:
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

    # --- tiền xử lý ---
    def detect_orientation(self, image):
        """Góc cần xoay ngược chiều kim đồng hồ để trang đứng thẳng (0/90/180/270)."""
        with self._lock:
            if not self.paddle_available() or not self.models_ready("ori"):
                return 0
            try:
                import numpy as np
                model = self._model("ori", lambda m: None)
                arr = np.array(image.convert("RGB"))[:, :, ::-1].copy()
                res = next(iter(model.predict(arr)))
                # Chỉ xoay khi chắc chắn: trang thưa chữ dễ bị đoán nhầm 180° (đo thực tế: 0.79 khi sai, >0.92 khi đúng)
                if float(res["scores"][0]) < 0.9:
                    return 0
                return int(res["label_names"][0])
            except Exception:
                return 0

    # --- nhận dạng ---
    def resolve_engine(self, quality, engine, image):
        """Chọn engine theo chế độ Nhanh / Tự động / Chính xác và lựa chọn model thủ công."""
        if engine and engine != "auto":
            return engine, None
        if quality == "fast":
            return "fast", None
        if quality == "accurate":
            if self.device_label() == "GPU":
                return "vl", None
            return "structure", ("Máy không có GPU nên chế độ Chính xác dùng PP-StructureV3. "
                                 "Chọn thủ công PaddleOCR-VL 1.6 nếu cần (mất vài phút/trang trên CPU).")
        # Tự động: trang có bảng kẻ ô -> PP-StructureV3, còn lại PP-OCRv6 + VietOCR
        return ("structure", None) if has_table_lines(image) else ("fast", None)

    def recognize(self, image_path, quality="fast", engine="auto", progress=lambda msg: None):
        start = time.time()
        image = Image.open(image_path).convert("RGB")
        with self._lock:
            chosen, note = self.resolve_engine(quality, engine, image)
            if not self.paddle_available():
                result = self._tesseract(image)
                result.notes.append("Chưa cài PaddleOCR - đang dùng Tesseract")
            elif not self.models_ready(chosen):
                result = self._tesseract(image)
                result.notes.append(f"Chưa có mô hình {ENGINES[chosen]} - chạy download_models.py để tải về. "
                                    "Đang dùng Tesseract")
            else:
                try:
                    if chosen == "fast":
                        result = self._run_fast(image, progress)
                    else:
                        result = self._run_document(image_path, image, chosen, progress)
                except Exception as e:
                    self.release(keep=("det",) if chosen != "fast" else ())
                    result = self._tesseract(image)
                    result.notes.append(f"{ENGINES[chosen]} gặp lỗi ({e}) - đã chuyển sang Tesseract")
            if note:
                result.notes.append(note)
        result.size = image.size
        result.seconds = time.time() - start
        return result

    def recognize_region(self, image_path, box, progress=lambda msg: None):
        """OCR lại một vùng chọn trên trang (box theo pixel ảnh)."""
        image = Image.open(image_path).convert("RGB")
        x1, y1, x2, y2 = [int(v) for v in box]
        crop = image.crop((max(0, x1), max(0, y1), min(image.width, x2), min(image.height, y2)))
        if crop.width < 8 or crop.height < 8:
            return OcrResult(text="", engine="")
        with self._lock:
            if not self.paddle_available() or not self.models_ready("fast"):
                return self._tesseract(crop)
            viet = self._vietocr(progress)
            res = self._run_fast(crop, progress)
            if not res.lines and viet is not None:   # vùng chỉ có 1 dòng nhỏ: đọc thẳng bằng VietOCR
                texts, probs = viet.recognize([crop])
                res = OcrResult(text=texts[0], engine="VietOCR",
                                lines=[{"text": texts[0], "box": [0, 0, crop.width, crop.height], "score": probs[0]}])
        for ln in res.lines:   # đổi tọa độ về hệ của cả trang
            ln["box"] = [ln["box"][0] + x1, ln["box"][1] + y1, ln["box"][2] + x1, ln["box"][3] + y1]
        return res

    def _run_fast(self, image, progress):
        viet = self._vietocr(progress)
        if viet is None:
            # Chưa có VietOCR: dùng nguyên PP-OCRv6 (tiếng Việt có thể mất một số dấu)
            pipeline = self._model("rec", progress)
            progress("Đang nhận dạng bằng PP-OCRv6")
            import numpy as np
            res = next(iter(pipeline.predict(np.array(image)[:, :, ::-1].copy())))
            lines = [{"text": str(t), "box": [float(v) for v in b[:4]], "score": float(s)}
                     for t, b, s in zip(_as_list(res["rec_texts"]), _as_list(res["rec_boxes"]),
                                        _as_list(res["rec_scores"]))]
            lines, text = reading_order(lines)
            return OcrResult(text=text, engine="PP-OCRv6", lines=lines,
                             notes=["Chưa có VietOCR - chữ tiếng Việt có thể bị mất dấu"])

        import numpy as np
        detector = self._model("det", progress)
        progress("PP-OCRv6 đang tìm các dòng chữ")
        res = next(iter(detector.predict(np.array(image)[:, :, ::-1].copy())))
        boxes = [poly_to_box(p) for p in _as_list(res["dt_polys"])]
        if not boxes:
            return OcrResult(text="", engine="PP-OCRv6 + VietOCR")
        progress(f"VietOCR đang đọc {len(boxes)} dòng chữ")
        texts, probs = viet.recognize(crop_lines(image, boxes))
        lines = [{"text": t, "box": b, "score": p} for t, p, b in zip(texts, probs, boxes)
                 if t and p >= VIETOCR_MIN_PROB]
        lines, text = reading_order(lines)
        return OcrResult(text=text, engine="PP-OCRv6 + VietOCR", lines=lines)

    def _run_document(self, image_path, image, mode, progress):
        pipeline = self._model(mode, progress)
        name = ENGINES[mode]
        if mode == "vl" and self.device_label() == "CPU":
            progress(f"{name} đang phân tích tài liệu trên CPU - có thể mất vài phút")
        else:
            progress(f"{name} đang phân tích tài liệu")
        res = next(iter(pipeline.predict(image_path)))
        md = _markdown_of(res)
        blocks = _blocks_of(res)
        notes = []

        if mode == "structure":
            # Chữ do PP-OCRv6 đọc bị thiếu dấu tiếng Việt -> VietOCR đọc lại từng dòng rồi thay vào
            ocr = res["overall_ocr_res"]
            old_texts = [str(t) for t in _as_list(ocr["rec_texts"])]
            boxes = [[float(v) for v in b[:4]] for b in _as_list(ocr["rec_boxes"])]
            scores = [float(s) for s in _as_list(ocr["rec_scores"])]
            texts = old_texts
            viet = self._vietocr(progress)
            if viet is not None and boxes:
                progress(f"VietOCR đang đọc lại {len(boxes)} dòng chữ")
                new_texts, probs = viet.recognize(crop_lines(image, boxes))
                texts = [n if n and p >= VIETOCR_MIN_PROB else o for o, n, p in zip(old_texts, new_texts, probs)]
                scores = [p if n and p >= VIETOCR_MIN_PROB else s
                          for s, n, p in zip(scores, new_texts, probs)]
                name += " + VietOCR"
            else:
                notes.append("Chưa có VietOCR - chữ tiếng Việt có thể bị mất dấu")
            lines = [{"text": t, "box": b, "score": s} for t, b, s in zip(texts, boxes, scores) if t.strip()]

            # Dựng lại từng bảng từ tọa độ ô + chữ VietOCR (mô hình bảng đôi khi trả thứ tự ô bị đảo)
            table_res = res.get("table_res_list") or []
            tables = [rebuild_table(_as_list(t.get("cell_box_list")), lines) for t in table_res]
            table_boxes = [b["box"] for b in blocks if b["label"] == "table"]

            def in_table(box):
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                return any(t[0] <= cx <= t[2] and t[1] <= cy <= t[3] for t in table_boxes)

            # Thay chữ đã sửa dấu vào phần ngoài bảng (bảng thay nguyên khối, tránh khớp nhầm chữ trong ô)
            pairs = [(o, t) for o, t, b in zip(old_texts, texts, boxes) if not in_table(b)]
            segments = re.split(r"(<table.*?</table>)", md, flags=re.S | re.I)
            outside = [seg for seg in segments if not seg.lower().startswith("<table")]
            fixed = iter(replace_in_order("\x00".join(outside), pairs).split("\x00"))
            rebuilt, it = [], iter(tables)
            for seg in segments:
                if seg.lower().startswith("<table"):
                    rebuilt.append(next(it, "") or seg)
                else:
                    rebuilt.append(next(fixed))
            md = "".join(rebuilt)
            it = iter(tables)
            for b in blocks:
                if b["label"] == "table":
                    b["content"] = next(it, "") or b["content"]
                else:
                    b["content"] = replace_in_order(b["content"], pairs)
            lines, text = reading_order(lines)
        else:
            text = markdown_to_plain(md)
            lines = [{"text": markdown_to_plain(b["content"]), "box": b["box"], "score": None}
                     for b in blocks if b["content"].strip() and b["label"] not in ("table", "image", "chart")]
            self.release(keep=("det", "ori", "vl"))  # dọn bộ nhớ tạm sau mỗi tài liệu
        return OcrResult(text=text, engine=name, markdown=md, lines=lines, blocks=blocks, notes=notes)

    @staticmethod
    def _tesseract(image):
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH
        data = pytesseract.image_to_data(image, lang=config.LANG, output_type=pytesseract.Output.DICT)
        groups = {}
        for i, word in enumerate(data["text"]):
            if not word.strip() or float(data["conf"][i]) < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            g = groups.setdefault(key, {"words": [], "box": [x, y, x + w, y + h], "conf": []})
            g["words"].append(word)
            g["conf"].append(float(data["conf"][i]) / 100)
            b = g["box"]
            g["box"] = [min(b[0], x), min(b[1], y), max(b[2], x + w), max(b[3], y + h)]
        lines = [{"text": " ".join(g["words"]), "box": [float(v) for v in g["box"]],
                  "score": sum(g["conf"]) / len(g["conf"])} for g in groups.values()]
        lines, text = reading_order(lines)
        return OcrResult(text=text, engine="Tesseract", lines=lines)
