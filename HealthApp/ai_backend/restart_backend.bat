@echo off
echo ========================================
echo KHOI DONG LAI BACKEND VOI GPU
echo ========================================
echo.

REM Kich hoat virtual environment
if exist venv (
    call venv\Scripts\activate.bat
) else (
    echo [ERROR] Virtual environment khong ton tai!
    echo Chay: python -m venv venv
    pause
    exit /b 1
)

echo [1/3] Kiem tra GPU...
python check_gpu.py
echo.

echo [2/3] Dung backend cu (neu dang chay)...
echo Nhan Ctrl+C de dung backend cu neu can
echo.

echo [3/3] Khoi dong backend...
echo Backend se chay voi GPU neu co
echo.
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
