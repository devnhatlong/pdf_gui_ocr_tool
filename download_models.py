# === download_models.py ===
# Chạy 1 LẦN trên máy có Internet để tải toàn bộ model OCR về thư mục models/.
# Sau đó phần mềm chạy hoàn toàn offline. Khi đóng gói, copy thư mục models/ đặt cạnh file .exe.
#
#   python download_models.py                 # tải tất cả (~3 GB)
#   python download_models.py fast vietocr    # chỉ PP-OCRv6 + VietOCR (bản nhẹ, ~150 MB)
#
# Các mục: fast (PP-OCRv6 Medium), vietocr, structure (PP-StructureV3), vl (PaddleOCR-VL 1.6)

import os
import sys
import tempfile

os.environ["OCR_MODEL_DOWNLOAD"] = "1"
import config  # noqa: E402

config.apply_model_env(offline=False)

from PIL import Image, ImageDraw  # noqa: E402

from utils import ocr_engine  # noqa: E402

PARTS = ["fast", "vietocr", "structure", "vl"]


def sample_page():
    """Trang mẫu có chữ và bảng để chạy thử: một số model chỉ được tải khi nhận dạng lần đầu."""
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    for i in range(6):
        d.text((120, 120 + i * 40), f"Sample text line {i + 1} - 123/BC-CAT", fill="black")
    for r in range(5):
        d.line((120, 500 + r * 60, 1100, 500 + r * 60), fill="black", width=2)
    for c in range(4):
        d.line((120 + c * 326, 500, 120 + c * 326, 740), fill="black", width=2)
    path = os.path.join(tempfile.gettempdir(), "ocr_sample_page.png")
    img.save(path)
    return path


def download_vietocr():
    import requests
    import yaml
    from vietocr.tool.utils import download_config

    os.makedirs(config.VIETOCR_DIR, exist_ok=True)
    cfg = download_config("base.yml")
    cfg.update(download_config("vgg-transformer.yml"))
    url = cfg["weights"]
    with open(config.VIETOCR_CONFIG, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    if not os.path.exists(config.VIETOCR_WEIGHTS):
        print(f"  Tải trọng số: {url}")
        tmp = config.VIETOCR_WEIGHTS + ".part"
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        os.replace(tmp, config.VIETOCR_WEIGHTS)
    ocr_engine.VietRecognizer()  # kiểm tra nạp được từ file cục bộ


def main():
    parts = [p for p in sys.argv[1:] if p in PARTS] or PARTS
    device = "cpu"  # chỉ để tải model, không cần GPU
    print(f"Thư mục model: {config.MODELS_DIR}")
    for part in parts:
        print(f"\n=== {part} ===", flush=True)
        if part == "vietocr":
            download_vietocr()
        elif part == "fast":
            ocr_engine.build_detector(device)
            ocr_engine.build_ppocr(device)
        elif part == "structure":
            # Chạy thử 1 trang để tải nốt các model phụ (xoay trang, hướng dòng chữ...)
            next(iter(ocr_engine.build_structure(device).predict(sample_page())))
        elif part == "vl":
            ocr_engine.build_vl(device)  # không chạy thử: trên CPU mất vài phút
        print(f"  OK: {part}", flush=True)
    print("\nHoàn tất. Thư mục models/ đã sẵn sàng để dùng offline.")


if __name__ == "__main__":
    main()
