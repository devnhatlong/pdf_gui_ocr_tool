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
# Thư mục models/ đặt cạnh file .exe (hoặc cạnh app.py khi chạy bằng Python),
# không nhúng vào .exe để khỏi giải nén vài GB mỗi lần mở phần mềm.
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR
MODELS_DIR = os.path.join(APP_DIR, "models")
PADDLEX_HOME = os.path.join(MODELS_DIR, "paddlex")     # model Paddle nằm ở paddlex/official_models/<tên>
VIETOCR_DIR = os.path.join(MODELS_DIR, "vietocr")
VIETOCR_CONFIG = os.path.join(VIETOCR_DIR, "vgg_transformer.yml")
VIETOCR_WEIGHTS = os.path.join(VIETOCR_DIR, "vgg_transformer.pth")

# ==================================================
# ỨNG DỤNG
# ==================================================
APP_NAME = "OfflineOCR Studio"
APP_VERSION = "2.0"
AUTHOR_LINES = [
    ("Phát triển bởi", "Nguyễn Nhật Long"),
    ("Đơn vị", "Đội CNTT - Phòng Tham mưu"),
    ("Liên hệ", "0365 756 687"),
]
WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.path.join(APP_DIR, "data")                 # lịch sử, cấu hình, bản nháp, file tạm
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
    """Gọi TRƯỚC khi import paddleocr/paddlex: trỏ kho model về thư mục models/ của phần mềm.
    offline=True: không kiểm tra/kết nối máy chủ model, không gọi HuggingFace."""
    os.environ["PADDLE_PDX_CACHE_HOME"] = PADDLEX_HOME
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "huggingface")
    if offline:
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
