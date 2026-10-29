@echo off
setlocal
cd /d "%~dp0"

title Build OCR Studio (portable)

if not exist ".venv\Scripts\python.exe" (
    echo [!] .venv belum ada. Jalankan start.bat dulu sekali.
    pause
    exit /b 1
)

echo.
echo   Membangun dist\OCR-Studio-portable\ ...
".venv\Scripts\pyinstaller.exe" build-portable.spec --noconfirm --clean || goto :fail

echo.
echo   Selesai: dist\OCR-Studio-portable\OCR-Studio.exe
echo   (start ~2-3 detik, tapi berupa folder - bukan satu file)
pause
exit /b 0

:fail
echo.
echo [!] Build gagal.
pause
exit /b 1
