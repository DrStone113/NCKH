@echo off
setlocal EnableExtensions
title HealthApp - Khoi Dong Tat Ca Service

set "MOBILE_DIR=%~dp0apps\mobile"
set "WEB_HASH_SCRIPT=%MOBILE_DIR%\tool\web_build_fingerprint.ps1"
set "WEB_BUILD_HASH=%MOBILE_DIR%\build\web\.source_hash"
set "WEB_INDEX=%MOBILE_DIR%\build\web\index.html"

echo ========================================================
echo   DANG KHOI DONG HE THONG HEALTHAPP
echo ========================================================
echo.

REM 1. Deploy Database Docker
echo [1/4] Kiem tra va khoi dong Database Postgres (pgvector)...

REM Detect Docker Desktop path
set DOCKER_CMD=docker
if exist "%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" (
    set DOCKER_CMD="%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
)
if exist "C:\Program Files\Docker\Docker\resources\bin\docker.exe" (
    set DOCKER_CMD="C:\Program Files\Docker\Docker\resources\bin\docker.exe"
)

%DOCKER_CMD% compose up -d postgres
if %ERRORLEVEL% NEQ 0 (
    echo [!] Kiem tra Docker Desktop xem da mo chua!
    pause
    exit /b %ERRORLEVEL%
)

REM 2. Prepare Flutter Web
echo.
echo [2/4] Kiem tra ban build Flutter Web...

set "CURRENT_WEB_HASH="
for /f "usebackq delims=" %%H in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%WEB_HASH_SCRIPT%"`) do set "CURRENT_WEB_HASH=%%H"

if not defined CURRENT_WEB_HASH (
    echo [!] Khong the kiem tra thay doi cua Flutter Web.
    pause
    exit /b 1
)

set "SAVED_WEB_HASH="
if exist "%WEB_BUILD_HASH%" set /p SAVED_WEB_HASH=<"%WEB_BUILD_HASH%"

set "WEB_NEEDS_BUILD=1"
if exist "%WEB_INDEX%" if /i "%CURRENT_WEB_HASH%"=="%SAVED_WEB_HASH%" set "WEB_NEEDS_BUILD=0"

if "%WEB_NEEDS_BUILD%"=="1" (
    echo [*] Phat hien thay doi. Dang build lai Flutter Web...
    pushd "%MOBILE_DIR%"
    call flutter build web --release --no-tree-shake-icons
    if errorlevel 1 (
        popd
        echo [!] Build Flutter Web that bai. Web Server se khong khoi dong.
        pause
        exit /b 1
    )
    popd
    >"%WEB_BUILD_HASH%" echo %CURRENT_WEB_HASH%
    echo [+] Build Flutter Web thanh cong.
) else (
    echo [+] Khong co thay doi. Su dung ban build hien tai.
)

REM 3. Launch Backend
echo.
echo [3/4] Khoi dong Backend FastAPI (Port 8080)...
start "HealthApp Backend" /min cmd /k "cd /d %~dp0apps\backend && venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload"

REM 4. Launch Web Server
echo.
echo [4/4] Khoi dong Web Server (Port 3000)...
start "HealthApp Web Server" /min cmd /k "cd /d %~dp0apps\mobile && ..\backend\venv\Scripts\python.exe serve_web.py"

echo.
echo ========================================================
echo   KHOI DONG THANH CONG!
echo ========================================================
echo   - Backend API : http://localhost:8080/docs
echo   - Web App     : http://localhost:3000
echo.
echo   Cua so nay se tu dong dong sau 5 giay...
timeout /t 5 >nul
