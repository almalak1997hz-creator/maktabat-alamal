@echo off
cd /d "%~dp0"
chcp 65001 >nul
where python >nul 2>nul
if errorlevel 1 (
  echo لم يتم العثور على Python.
  echo ثبّت Python ثم أعد تشغيل هذا الملف.
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo فشل تثبيت المكونات.
  pause
  exit /b 1
)
if not exist cloudflared.exe (
  echo.
  echo لم يتم العثور على cloudflared.exe
  echo حمّل نسخة Windows 64-bit من صفحة Cloudflare الرسمية وضعها هنا باسم cloudflared.exe
  echo ثم شغّل start.bat
  start https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/
  pause
  exit /b 0
)
echo تم تجهيز مكتبة الأمل.
pause
