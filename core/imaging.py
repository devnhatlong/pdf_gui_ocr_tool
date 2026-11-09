# === imaging.py ===
# Xử lý ảnh trang: làm thẳng (deskew), giảm nhiễu, phát hiện trang trắng, đọc mã QR / barcode.

import base64
import io

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


def to_data_url(image, max_side=None, quality=82):
    """Ảnh -> data URL JPEG để hiển thị trên giao diện."""
    img = image.convert("RGB")
    if max_side and max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def deskew(image, max_angle=8.0):
    """Làm thẳng trang scan bị nghiêng nhẹ. Trả về (ảnh, góc đã xoay)."""
    try:
        import cv2
        gray = np.array(image.convert("L"))
        scale = 1200 / max(gray.shape)
        small = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
        bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        # Nối các chữ trên cùng dòng thành vệt ngang rồi đo góc các vệt
        bw = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3)))
        contours = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
        angles = []
        for c in contours:
            (_, _), (w, h), a = cv2.minAreaRect(c)
            if max(w, h) < small.shape[1] * 0.15:
                continue
            if w < h:
                a -= 90
            if abs(a) <= max_angle:
                angles.append(a)
        if len(angles) < 3:
            return image, 0.0
        angle = float(np.median(angles))
        if abs(angle) < 0.3:
            return image, 0.0
        return image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white"), angle
    except Exception:
        return image, 0.0


def denoise(image):
    try:
        import cv2
        arr = np.array(image.convert("L"))
        arr = cv2.fastNlMeansDenoising(arr, None, h=12, templateWindowSize=7, searchWindowSize=21)
        return Image.fromarray(arr).convert("RGB")
    except Exception:
        return image


def enhance(image):
    """Tăng tương phản nhẹ cho ảnh scan mờ."""
    return ImageOps.autocontrast(image.convert("RGB"), cutoff=1)


def boost_ink(image, level):
    """Tăng độ đậm chữ trước khi OCR. level: off | light (tăng tương phản) | strong (thêm gamma làm tối nét nhạt)."""
    if level == "light":
        return enhance(image)
    if level == "strong":
        curve = [round(255 * (i / 255) ** 1.8) for i in range(256)]   # nền trắng giữ nguyên, nét xám tối đi
        return enhance(image).point(curve * 3)
    return image


def apply_color_mode(image, mode):
    """Đổi màu ảnh trước khi OCR. mode: keep | gray | vivid (tăng màu) | bw (trắng đen, ngưỡng theo từng vùng)."""
    if mode == "gray":
        return image.convert("L").convert("RGB")
    if mode == "vivid":
        return ImageEnhance.Color(image.convert("RGB")).enhance(2.5)
    if mode == "bw":
        try:
            import cv2
            arr = np.array(image.convert("L"))
            arr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 12)
            return Image.fromarray(arr).convert("RGB")
        except Exception:
            return image
    return image


def is_blank(image, ink_ratio=0.003):
    """Trang trắng: rất ít điểm mực sau khi bỏ lề 6% (vết ghim, bóng mép giấy)."""
    gray = np.array(image.convert("L").resize((300, int(300 * image.height / max(1, image.width)))))
    h, w = gray.shape
    core = gray[int(h * 0.06):int(h * 0.94), int(w * 0.06):int(w * 0.94)]
    if core.size == 0:
        return True
    return float((core < 160).mean()) < ink_ratio


def read_codes(image):
    """Đọc mã QR và barcode trên trang (dùng làm trang phân cách). Trả về danh sách nội dung."""
    found = []
    try:
        import cv2
        arr = np.array(image.convert("RGB"))[:, :, ::-1].copy()
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(arr)
        if text:
            found.append("QR:" + text)
        if hasattr(cv2, "barcode"):
            ok, infos, _types, _pts = _barcode(cv2, arr)
            if ok:
                found += ["BAR:" + t for t in infos if t]
    except Exception:
        pass
    return found


def _barcode(cv2, arr):
    res = cv2.barcode.BarcodeDetector().detectAndDecodeWithType(arr)
    if len(res) == 4:
        return res
    ok, infos, types = res[0], res[1], res[2]
    return ok, infos, types, None
