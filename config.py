DPI = 200  # Giảm từ 300 xuống 200 để OCR nhanh hơn, vẫn đủ chất lượng
LANG = "vie+eng"
TEMP_IMAGE_FOLDER = "data/temp_images"

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POPPLER_PATH = os.path.join(BASE_DIR, "poppler-24.08.0", "Library", "bin")

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