# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\Develop\\pdf_gui_ocr_tool\\pdf_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\Develop\\pdf_gui_ocr_tool\\poppler-24.08.0', 'poppler-24.08.0')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pdf_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
