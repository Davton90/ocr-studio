# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec - builds the portable (onedir) OCR Studio folder.

Same payload as build.spec, but the runtime files live in a sibling
_internal/ folder instead of being extracted on every launch. Result:
startup ~2-3 s instead of ~10-20 s, at the cost of shipping a folder
instead of a single file.
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = []
datas += collect_data_files("rapidocr", includes=["*.yaml"])
datas += collect_data_files("webview")

# pillow-heif / pillow-jxl ship native DLLs (libheif, libjxl) that the default
# hooks do not pick up
binaries = []
plugin_hidden = []
for _pkg in ("pillow_heif", "pillow_jxl"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    plugin_hidden += _h
datas += [
    ("web", "web"),
    ("samples", "samples"),
    ("assets/models", "models"),
    ("assets/indra", "assets/indra"),
]

hiddenimports = collect_submodules("rapidocr") + collect_submodules("webview") + collect_submodules("indra_ocr") + plugin_hidden + [
    "pillow_heif",
    "pillow_jxl",
    "clr",
    "clr_loader",
    "pythonnet",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "onnxruntime",
    "pypdfium2",
    "pypdfium2_raw",
    "multipart",
]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "matplotlib", "scipy", "pandas", "tkinter", "PyQt5", "PySide6",
        "IPython", "pytest", "notebook", "jupyter", "torch", "tensorflow",
    ],
    noarchive=False,
)

# OpenCV's ffmpeg video backend (~31 MB) is only used for reading video files.
a.binaries = [b for b in a.binaries if "opencv_videoio_ffmpeg" not in b[0].lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OCR-Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OCR-Studio-portable",
)
