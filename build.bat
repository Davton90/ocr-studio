@echo off
setlocal
cd /d "%~dp0"

title Build OCR Studio

if not exist ".venv\Scripts\python.exe" (
    echo [!] .venv belum ada. Jalankan start.bat dulu sekali.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [i] Memasang PyInstaller...
    uv pip install --python ".venv\Scripts\python.exe" pyinstaller || exit /b 1
)

echo.
echo   Membangun dist\OCR-Studio.exe ...
".venv\Scripts\pyinstaller.exe" build.spec --noconfirm --clean || goto :fail

echo.
echo   Selesai: dist\OCR-Studio.exe
pause
exit /b 0

:fail
echo.
echo [!] Build gagal.
pause
exit /b 1
