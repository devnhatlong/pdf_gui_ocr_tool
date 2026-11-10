LANG = "vie+eng"   # ngôn ngữ Tesseract (chỉ dùng khi chưa có model PaddleOCR)

import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Tesseract path - ưu tiên dùng local, nếu không có thì dùng system path
TESSERACT_LOCAL = os.path.join(BASE_DIR, "tesseract-ocr", "tesseract.exe")
TESSERACT_SYSTEM = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_PATH = TESSERACT_LOCAL if os.path.exists(TESSERACT_LOCAL) else TESSERACT_SYSTEM

# TESSDATA_PREFIX - đường dẫn đến thư mục tessdata
if os.path.exists(TESSERACT_LOCAL):
    TESSDATA_PREFIX = os.path.join(BASE_DIR, "tesseract-ocr", "tessdata")
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PREFIX
elif os.path.exists(TESSERACT_SYSTEM):
    TESSDATA_PREFIX = r"C:\Program Files\Tesseract-OCR\tessdata"
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PREFIX

# ==================================================
# MODEL OCR (chạy offline)
# ==================================================
# Thư mục models/ đặt cạnh file .exe (hoặc cạnh app.py khi chạy bằng Python) — bộ cài chép sẵn vào đây.
# Khi cài vào Program Files thư mục này CHỈ ĐỌC; mọi thứ cần ghi (dữ liệu, bộ đệm PaddleX, model nhập thêm)
# nằm ở USER_DIR = %LOCALAPPDATA%\OfflineOCR Studio. Chạy từ mã nguồn thì USER_DIR là thư mục dự án.
FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else BASE_DIR
USER_DIR = (os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "OfflineOCR Studio")
            if FROZEN else BASE_DIR)
MODELS_DIR = os.path.join(APP_DIR, "models")                         # model đi kèm bộ cài (chỉ đọc)
USER_MODELS_DIR = os.path.join(USER_DIR, "models")                   # model nhập thêm từ màn hình Quản lý mô hình
PADDLEX_MODEL_DIRS = [os.path.join(d, "paddlex", "official_models")  # tìm model Paddle theo thứ tự này
                      for d in dict.fromkeys([USER_MODELS_DIR, MODELS_DIR])]
VIETOCR_DIRS = [os.path.join(d, "vietocr") for d in dict.fromkeys([USER_MODELS_DIR, MODELS_DIR])]
VIETOCR_CONFIG_NAME = "vgg_transformer.yml"
VIETOCR_WEIGHTS_NAME = "vgg_transformer.pth"


def find_paddlex_model(name):
    """Thư mục model PaddleX (ưu tiên model người dùng nhập thêm), hoặc None nếu chưa có."""
    for root in PADDLEX_MODEL_DIRS:
        path = os.path.join(root, name)
        if os.path.isdir(path):
            return path
    return None


def vietocr_dir():
    """Thư mục VietOCR có đủ config + trọng số, hoặc None."""
    for d in VIETOCR_DIRS:
        if os.path.exists(os.path.join(d, VIETOCR_CONFIG_NAME)) and os.path.exists(os.path.join(d, VIETOCR_WEIGHTS_NAME)):
            return d
    return None

# ==================================================
# ỨNG DỤNG
# ==================================================
APP_NAME = "OfflineOCR Studio"
APP_VERSION = "2.5.0"
AUTHOR_LINES = [
    ("Phát triển bởi", "Nguyễn Nhật Long"),
    ("Đơn vị", "Đội CNTT - Phòng Tham mưu"),
    ("Liên hệ", "0365 756 687"),
]
WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.path.join(USER_DIR, "data")                # lịch sử, cấu hình, bản quyền, bản nháp, file tạm
LICENSE_FILE = os.path.join(DATA_DIR, "license.dat")
PADDLEX_CACHE = os.path.join(DATA_DIR, "paddlex_cache")   # file khóa / bộ đệm PaddleX (phải ghi được)
WORKSPACE_DIR = os.path.join(DATA_DIR, "workspace")       # ảnh trang đã dựng, file PDF tạm
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
HISTORY_DB = os.path.join(DATA_DIR, "history.db")
DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "OfflineOCR_Output")
SYSTEM_FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")  # lớp chữ PDF

OCR_LANG = "vi"
PPOCR_DET_MODEL = "PP-OCRv6_medium_det"
PPOCR_REC_MODEL = "PP-OCRv6_medium_rec"
VL_PIPELINE_VERSION = "v1.6"
VIETOCR_MIN_SCORE = 0.90   # Dòng PP-OCRv6 đọc với độ tin cậy thấp hơn mức này sẽ được VietOCR đọc lại


def apply_model_env(offline=True):
    """Gọi TRƯỚC khi import paddleocr/paddlex. Bộ đệm/khóa PaddleX ghi vào PADDLEX_CACHE (ghi được);
    nơi tìm model được trỏ về models/ bằng utils.ocr_engine.patch_model_dirs() sau khi import.
    offline=True: không kiểm tra/kết nối máy chủ model, không gọi HuggingFace."""
    os.makedirs(PADDLEX_CACHE, exist_ok=True)
    os.environ["PADDLE_PDX_CACHE_HOME"] = PADDLEX_CACHE
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "huggingface")
    if offline:
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
