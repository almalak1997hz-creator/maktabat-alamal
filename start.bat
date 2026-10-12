@echo off
cd /d "%~dp0"
chcp 65001 >nul

rem === تحديث تلقائي من GitHub (يتجاوز الخطأ إن لم يوجد إنترنت أو Git) ===
if exist ".git" (
    where git >nul 2>nul && (
        echo Checking for updates...
        git pull --ff-only
        python -m pip install -r requirements.txt -q
    )
)

python launcher.py
pause
