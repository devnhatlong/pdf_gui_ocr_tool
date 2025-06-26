TESSERACT_PATH = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
DPI = 300
LANG = "vie+eng"
TEMP_IMAGE_FOLDER = "data/temp_images"


# === utils/__init__.py ===
# Để thư mục utils thành package Python


# === utils/pdf_utils.py ===
from pdf2image import convert_from_path
from config import DPI, TEMP_IMAGE_FOLDER
import os

def pdf_to_images(pdf_path, max_pages=1):
    images = convert_from_path(pdf_path, dpi=DPI)
    os.makedirs(TEMP_IMAGE_FOLDER, exist_ok=True)
    paths = []
    for i, img in enumerate(images[:max_pages]):
        path = os.path.join(TEMP_IMAGE_FOLDER, f"page_{i+1}.png")
        img.save(path, "PNG")
        paths.append(path)
    return paths