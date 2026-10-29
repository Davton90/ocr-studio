# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec - builds a single-file OCR-Studio.exe."""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = []
# rapidocr reads config.yaml / default_models.yaml at runtime (not .onnx, those
# are shipped from assets/models so the exe only carries the tiny variant)
datas += collect_data_files("rapidocr", includes=["*.yaml"])
# pywebview ships the WebView2 interop assemblies next to the package
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
]

hiddenimports = collect_submodules("rapidocr") + collect_submodules("webview") + plugin_hidden + [
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

pyz = PYZ(a.pure)

# OpenCV's ffmpeg video backend (~31 MB) is only used for reading video files.
# This app reads images and PDFs only, so it is dead weight in the bundle.
a.binaries = [b for b in a.binaries if "opencv_videoio_ffmpeg" not in b[0].lower()]

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OCR-Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/icon.ico",
)
