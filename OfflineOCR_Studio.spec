# -*- mode: python ; coding: utf-8 -*-
# Build:  .venv\Scripts\pyinstaller.exe OfflineOCR_Studio.spec --noconfirm
# Kết quả: dist\OfflineOCR_Studio\OfflineOCR_Studio.exe (dạng thư mục - Paddle + PyTorch quá nặng để gói 1 file,
# mỗi lần mở sẽ phải giải nén ~1.5 GB).
# Sau khi build: copy thư mục models\ (tải bằng download_models.py) vào dist\OfflineOCR_Studio\models\

from importlib.metadata import distributions

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [
    ('tesseract-ocr', 'tesseract-ocr'),
    ('assets/logo.ico', 'assets'),  # Icon Windows; logo giao dien nam trong web/assets
    ('web', 'web'),        # giao diện HTML/CSS/JS
]
binaries = []
hiddenimports = []

# Paddle / PaddleX / PaddleOCR / VietOCR nạp module và file cấu hình (.yaml) động.
# torchvision cần đủ thư viện C (_C.pyd), thiếu sẽ lỗi "operator torchvision::nms does not exist".
for pkg in ('paddle', 'paddlex', 'paddleocr', 'vietocr', 'torch', 'torchvision', 'webview', 'pypdfium2', 'reportlab', 'docx'):
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

# Bỏ header C++ và thư viện tĩnh (.lib/.a) của Paddle / PyTorch: chỉ dùng khi biên dịch extension,
# nặng (~90 MB) và có đường dẫn rất dài (vượt 260 ký tự khi cài vào thư mục sâu -> bộ cài báo lỗi).
DEV_ONLY_DIRS = ('paddle/include', 'torch/include')


def _runtime_file(src, dst):
    dst = dst.replace('\\', '/')
    return not dst.startswith(DEV_ONLY_DIRS) and not src.lower().endswith(('.lib', '.a'))


datas = [(src, dst) for src, dst in datas if _runtime_file(src, dst)]
binaries = [(src, dst) for src, dst in binaries if _runtime_file(src, dst)]

a = Analysis(
    ['app.py'],
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
    name='OfflineOCR_Studio',  # Tên file .exe (không dấu để tránh lỗi trên Windows)
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
    name='OfflineOCR_Studio',
)
