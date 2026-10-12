@echo off
rem === جهاز المحل: اسحب آخر تعديلات ===
cd /d "%~dp0"
git pull
python -m pip install -r requirements.txt -q
echo.
echo Updated. Close the running program and start it again to apply changes.
pause
