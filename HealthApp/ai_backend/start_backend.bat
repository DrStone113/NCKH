@echo off
cd /d "%~dp0"
title AI Health Chatbot - Backend
echo ========================================
echo   AI Health Chatbot Backend
echo ========================================
echo.

REM Kiem tra Docker
docker --version >nul 2>&1
if %errorlevel% == 0 (
    echo [Docker] Tim thay Docker - chay bang Docker Compose...
    echo.
    docker compose up
) else (
    echo [Local] Khong tim thay Docker - chay FastAPI truc tiep...
    echo.

    REM Kiem tra Python (thu ca python va py)
    set PYTHON_CMD=
    python --version >nul 2>&1
    if %errorlevel% == 0 set PYTHON_CMD=python
    py --version >nul 2>&1
    if %errorlevel% == 0 set PYTHON_CMD=py

    if "%PYTHON_CMD%"=="" (
        echo [LOI] Khong tim thay Python. Vui long cai Python truoc.
        pause
        exit /b 1
    )
    echo [Python] Tim thay: %PYTHON_CMD%

    REM Cai dependencies neu chua co
    if not exist "backend\venv" (
        echo [Setup] Tao virtual environment...
        %PYTHON_CMD% -m venv backend\venv
    )

    echo [Setup] Kich hoat venv va cai dependencies...
    call backend\venv\Scripts\activate.bat
    pip install -r backend\requirements.txt --quiet

    echo.
    echo [Ollama] Kiem tra Ollama...
    ollama --version >nul 2>&1
    if %errorlevel% == 0 (
        echo [Ollama] Dang khoi dong Ollama server...
        start "Ollama Server" cmd /c "ollama serve"
        timeout /t 3 /nobreak >nul
    ) else (
        echo [CANH BAO] Ollama chua duoc cai. Tai tai: https://ollama.com
        echo            Chatbot se khong hoat dong cho den khi cai Ollama.
    )

    echo.
    echo [FastAPI] Khoi dong server tai http://localhost:8000
    echo [FastAPI] Nhan Ctrl+C de dung
    echo.
    cd backend
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
)

pause
