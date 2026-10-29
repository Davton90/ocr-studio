@echo off
setlocal
cd /d "%~dp0"

title OCR Studio

if not exist ".venv\Scripts\python.exe" (
    echo [i] Virtual environment belum ada, menyiapkan...
    where uv >nul 2>nul
    if errorlevel 1 (
        python -m venv .venv || goto :fail
        ".venv\Scripts\python.exe" -m pip install --upgrade pip
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
    ) else (
        uv venv --python 3.13 .venv || goto :fail
        uv pip install --python ".venv\Scripts\python.exe" -r requirements.txt || goto :fail
    )
)

echo.
echo   Menjalankan OCR Studio (jendela aplikasi)...
".venv\Scripts\python.exe" desktop.py
if errorlevel 1 goto :fail
goto :eof

:fail
echo.
echo [!] Gagal menjalankan OCR Studio.
pause
