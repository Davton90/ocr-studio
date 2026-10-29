"""
OCR Studio - desktop entry point.

Runs the FastAPI engine in a background thread and shows the UI in a native
window using the WebView2 runtime that ships with Windows (no extra browser).
Falls back to the default browser if WebView2 is unavailable.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from server import FROZEN, app, _free_port


def _wait_ready(port: int, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _fatal(msg: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "OCR Studio", 0x10)
    except Exception:  # noqa: BLE001
        pass


def _window_geometry() -> tuple[int, int, int, int]:
    """Pick a window size/position that fits the screen.

    Two things go wrong when we let the toolkit decide: asking for a size larger
    than the display gets clamped after creation (WebView2 keeps the stale
    viewport), and the default position can push the bottom edge off-screen.
    """
    try:
        import ctypes

        u = ctypes.windll.user32
        sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    except Exception:  # noqa: BLE001
        return 40, 40, 1280, 820

    w = max(900, min(1440, int(sw * 0.90)))
    h = max(600, min(920, int(sh * 0.90)))
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    return x, y, w, h


def main() -> None:
    if FROZEN:
        log = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OCRStudio" / "app.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            fh = open(log, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
            if sys.stdout is None:
                sys.stdout = fh
            if sys.stderr is None:
                sys.stderr = fh
        except OSError:
            pass

    port = _free_port(8848)
    url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="uvicorn").start()

    if not _wait_ready(port):
        _fatal("Server OCR tidak bisa dimulai. Cek log di %LOCALAPPDATA%\\OCRStudio\\app.log")
        return

    try:
        import webview

        x, y, w, h = _window_geometry()
        webview.create_window(
            "OCR Studio",
            url,
            x=x,
            y=y,
            width=w,
            height=h,
            min_size=(900, 600),
            background_color="#0a0c11",
            text_select=True,
        )
        webview.start()
    except Exception as exc:  # noqa: BLE001
        print(f"[i] Jendela native gagal ({type(exc).__name__}: {exc}), pakai browser.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        server.should_exit = True


if __name__ == "__main__":
    main()
