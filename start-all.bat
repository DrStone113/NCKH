@echo off
chcp 65001 >nul
title HealthApp - Khởi Động Tất Cả Service

echo ========================================================
echo   🚀 DANG KHOI DONG HE THONG HEALTHAPP
echo ========================================================
echo.

:: 1. Deploy Database Docker
echo [1/3] Kiem tra va khoi dong Database Postgres (pgvector)...
docker compose up -d postgres
if %ERRORLEVEL% NEQ 0 (
    echo [!] Kiem tra Docker Desktop xem da mo chua!
    pause
    exit /b %ERRORLEVEL%
)

:: 2. Launch Backend
echo.
echo [2/3] Khoi dong Backend FastAPI (Port 8080)...
start "HealthApp Backend" /min cmd /k "cd /d %~dp0HealthApp\ai_backend\backend && venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload"

:: 3. Launch Web Server
echo.
echo [3/3] Khoi dong Web Server (Port 3000)...
start "HealthApp Web Server" /min cmd /k "cd /d %~dp0HealthApp\health_app && ..\ai_backend\backend\venv\Scripts\python.exe -m http.server 3000 --directory build\web"

echo.
echo ========================================================
echo   ✅ KHOI DONG THANH CONG!
echo ========================================================
echo   - Backend API : http://localhost:8080/docs
echo   - Web App     : http://localhost:3000
echo.
echo   Cua so nay se tu dong dong sau 5 giây...
timeout /t 5 >nul
