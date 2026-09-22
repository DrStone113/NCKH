@echo off
setlocal EnableExtensions
title HealthApp - Khoi Dong Tat Ca Service

set "ROOT_DIR=%~dp0"
set "DEV_COMPOSE=%~dp0docker-compose.dev.yml"
set "MOBILE_DIR=%~dp0apps\mobile"
set "CLEANUP_SCRIPT=%~dp0scripts\cleanup-generated.ps1"
set "WEB_HASH_SCRIPT=%MOBILE_DIR%\tool\web_build_fingerprint.ps1"
set "WEB_BUILD_HASH=%MOBILE_DIR%\build\web\.source_hash"
set "WEB_INDEX=%MOBILE_DIR%\build\web\index.html"

echo ========================================================
echo   DANG KHOI DONG HE THONG HEALTHAPP
echo ========================================================
echo.

REM 1. Remove stale generated artifacts and release the old local web listener.
echo [1/5] Don artefact tam va tien trinh Web cu...
if exist "%CLEANUP_SCRIPT%" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CLEANUP_SCRIPT%" -Phase Start
    if errorlevel 1 echo [!] Cleanup gap loi; tiep tuc khoi dong dich vu.
) else (
    echo [!] Khong tim thay cleanup helper: %CLEANUP_SCRIPT%
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr /R /C:":3000 .*LISTENING"') do taskkill /t /f /pid %%a >nul 2>&1

REM 2. Deploy Database Docker
echo.
echo [2/5] Kiem tra va khoi dong Database Postgres (pgvector)...

REM Detect Docker Desktop path
set "DOCKER_EXE=docker"
if exist "%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" (
    set "DOCKER_EXE=%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
)
if exist "C:\Program Files\Docker\Docker\resources\bin\docker.exe" (
    set "DOCKER_EXE=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
)

"%DOCKER_EXE%" compose up -d postgres
if %ERRORLEVEL% NEQ 0 (
    echo [!] Kiem tra Docker Desktop xem da mo chua!
    pause
    exit /b %ERRORLEVEL%
)

REM 3. Prepare Flutter Web
echo.
echo [3/5] Kiem tra ban build Flutter Web...

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

REM 4. Launch Backend in the pinned Python 3.11 Docker environment.
REM The repository-local venv is optional and is not present on every machine.
echo.
echo [4/5] Khoi dong Backend FastAPI (Port 8080)...
pushd "%ROOT_DIR%"
"%DOCKER_EXE%" compose -f docker-compose.yml -f docker-compose.dev.yml up -d fastapi_backend
if errorlevel 1 (
    popd
    echo [!] Backend Docker khoi dong that bai.
    pause
    exit /b 1
)
popd

echo [*] Doi Backend va local SLM san sang...
for /l %%I in (1,1,180) do (
    curl.exe -fsS http://localhost:8080/health >nul 2>&1 && goto backend_ready
    ping 127.0.0.1 -n 2 >nul
)
echo [!] Backend/local SLM khong san sang tren port 8080 sau 180 giay.
"%DOCKER_EXE%" compose -f docker-compose.yml -f docker-compose.dev.yml logs --tail 80 fastapi_backend
pause
exit /b 1

:backend_ready
echo [+] Backend da san sang.
start "HealthApp Backend" /D "%ROOT_DIR%" /min "%DOCKER_EXE%" compose -f docker-compose.yml -f docker-compose.dev.yml logs -f fastapi_backend

REM 5. Launch Web Server
echo.
echo [5/5] Khoi dong Web Server (Port 3000)...
where python >nul 2>&1
if errorlevel 1 (
    echo [!] Khong tim thay Python tren PATH de chay static web server.
    pause
    exit /b 1
)
start "HealthApp Web Server" /D "%MOBILE_DIR%" /min python serve_web.py

echo [*] Doi Web Server san sang...
for /l %%I in (1,1,30) do (
    curl.exe -fsS http://localhost:3000 >nul 2>&1 && goto web_ready
    ping 127.0.0.1 -n 2 >nul
)
echo [!] Web Server khong san sang tren port 3000 sau 30 giay.
pause
exit /b 1

:web_ready
echo [+] Web Server da san sang.

echo.
echo ========================================================
echo   KHOI DONG THANH CONG!
echo ========================================================
echo   - Backend API : http://localhost:8080/docs
echo   - Web App     : http://localhost:3000
echo.
echo   Cua so nay se tu dong dong sau 5 giay...
powershell.exe -NoProfile -Command "Start-Sleep -Seconds 5"
exit /b 0
