@echo off
rem === جهاز التطوير: ارفع تعديلاتك ===
cd /d "%~dp0"
git add -A
git commit -m "update %date% %time%"
git push
echo.
echo Done. Now run update.bat on the shop PC.
pause
