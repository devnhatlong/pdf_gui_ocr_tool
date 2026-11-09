# === app.py ===
# OfflineOCR Studio - điểm khởi chạy. Giao diện HTML (web/) hiển thị bằng Edge WebView2 qua pywebview,
# toàn bộ xử lý OCR / PDF chạy trong Python, hoàn toàn offline.
#
#   python app.py                       # mở phần mềm
#   python app.py --selftest file.pdf   # kiểm tra OCR trên máy, ghi kết quả ra selftest.txt

import os
import sys

# PyInstaller's spawn dispatch must run before importing application modules.
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

import config


def selftest(path):
    """Kiểm tra OCR không cần giao diện (dùng khi cài đặt cho khách hàng)."""
    lines = []
    try:
        from core.document import Document
        from utils.ocr_engine import ENGINES, OcrService
        service = OcrService()
        lines.append(f"Thư mục model: {config.MODELS_DIR}")
        lines.append(f"PaddleOCR: {'có' if service.paddle_available() else 'KHÔNG'}"
                     f" | VietOCR: {'có' if service.vietocr_ready() else 'KHÔNG'}")
        if service.import_error:
            lines.append(service.import_error)
        doc = Document(path, os.path.join(config.WORKSPACE_DIR, "selftest"))
        _img, image_path = doc.render(doc.pages[0], 200)
        if not os.path.exists(image_path):
            _img.save(image_path)
        for engine in ("fast", "structure"):
            r = service.recognize(image_path, engine=engine)
            lines.append(f"\n[{ENGINES[engine]}] {r.engine} · {r.seconds:.1f} giây · "
                         f"{service.device_label() if r.engine != 'Tesseract' else ''} {r.notes}")
            lines.append(r.text[:500])
            if service._viet_error:
                lines.append(f"Lỗi VietOCR:\n{service._viet_error}")
    except Exception:
        import traceback
        lines.append("LỖI:\n" + traceback.format_exc())
    os.makedirs(config.DATA_DIR, exist_ok=True)
    out = os.path.join(config.DATA_DIR, "selftest.txt")
    print(f"Kết quả kiểm tra: {out}")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
        return

    import webview
    from webview.dom import DOMEventHandler

    from core.api import Api

    api = Api()
    # OFFLINEOCR_WINDOW_POS="x,y": đặt vị trí cửa sổ, không phóng to (dùng khi kiểm thử tự động)
    pos = os.environ.get("OFFLINEOCR_WINDOW_POS")
    x, y = (int(v) for v in pos.split(",")) if pos else (None, None)
    window = webview.create_window(
        config.APP_NAME,
        url=os.path.join(config.WEB_DIR, "index.html"),
        js_api=api,
        width=1440, height=900, min_size=(1100, 680), x=x, y=y,
        background_color="#f4f7fc",
        text_select=True,
    )
    api._set_window(window)

    def on_drop(event):
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            api._push({"type": "drop", "paths": paths})

    def on_loaded():
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        if not pos:
            window.maximize()

    window.events.loaded += on_loaded
    window.events.closed += api._close
    icon = os.path.join(config.BASE_DIR, "assets", "logo.ico")
    webview.start(gui="edgechromium", debug="--debug" in sys.argv,
                  icon=icon if os.path.exists(icon) else None,
                  storage_path=os.path.join(config.DATA_DIR, "webview"))


if __name__ == "__main__":
    main()
