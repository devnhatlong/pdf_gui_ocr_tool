import pytesseract
from config import TESSERACT_PATH, LANG
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

def extract_text_from_image(image_path):
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang=LANG)