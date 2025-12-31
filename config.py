TESSERACT_PATH = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
DPI = 200  # Giảm từ 300 xuống 200 để OCR nhanh hơn, vẫn đủ chất lượng
LANG = "vie+eng"
TEMP_IMAGE_FOLDER = "data/temp_images"

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POPPLER_PATH = os.path.join(BASE_DIR, "poppler-24.08.0", "Library", "bin")