# -*- mode: python ; coding: utf-8 -*-
# Build:  .venv\Scripts\pyinstaller.exe pdf_gui.spec --noconfirm
# Kết quả: dist\OCR_PDF\OCR_PDF.exe (dạng thư mục — Paddle + PyTorch quá nặng để gói 1 file,
# mỗi lần mở sẽ phải giải nén ~1.5 GB).
# Sau khi build: copy thư mục models\ (tải bằng download_models.py) vào dist\OCR_PDF\models\

from importlib.metadata import distributions

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [
    ('poppler-24.08.0', 'poppler-24.08.0'),
    ('tesseract-ocr', 'tesseract-ocr'),
    ('assets', 'assets'),  # Include assets folder (logo.ico, logo.png)
]
binaries = []
hiddenimports = []

# Paddle / PaddleX / PaddleOCR / VietOCR nạp module và file cấu hình (.yaml) động.
# torchvision cần đủ thư viện C (_C.pyd), thiếu sẽ lỗi "operator torchvision::nms does not exist".
for pkg in ('paddle', 'paddlex', 'paddleocr', 'vietocr', 'torch', 'torchvision'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# PaddleX kiểm tra thư viện phụ thuộc qua importlib.metadata -> cần metadata của mọi gói đã cài
for dist in distributions():
    try:
        datas += copy_metadata(dist.metadata['Name'])
    except Exception:
        pass

# Bỏ header C++ của Paddle (chỉ dùng khi biên dịch extension, nặng và đường dẫn rất dài)
datas = [(src, dst) for src, dst in datas if not dst.replace('\\', '/').startswith('paddle/include')]

a = Analysis(
    ['pdf_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tensorflow', 'IPython', 'jupyter', 'notebook', 'pytest'],  # PaddleX cần matplotlib
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OCR_PDF',  # Tên file .exe (không dấu để tránh lỗi trên Windows)
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX làm hỏng một số DLL của Paddle/PyTorch
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',  # Icon cho file .exe
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='OCR_PDF',
)
