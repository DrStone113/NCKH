@echo off
setlocal EnableExtensions
title HealthApp - Dung Tat Ca Service

set "ROOT_DIR=%~dp0"

echo ========================================================
echo   DANG DUNG TAT CA DICH VU HEALTHAPP
echo ========================================================
echo.

:: The backend runs in Docker; only the host static web server owns port 3000.
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /R /C:":3000 .*LISTENING"') do taskkill /f /pid %%a >nul 2>&1

:: Stop and remove project containers/networks. Named volumes are preserved.
echo Dung va don container Docker cua HealthApp...

REM Detect Docker Desktop path
set "DOCKER_EXE=docker"
if exist "%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" (
    set "DOCKER_EXE=%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
)
if exist "C:\Program Files\Docker\Docker\resources\bin\docker.exe" (
    set "DOCKER_EXE=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
)

pushd "%ROOT_DIR%"
"%DOCKER_EXE%" info >nul 2>&1
if errorlevel 1 (
    echo [i] Docker Desktop dang tat; khong co container dang chay.
    popd
    goto done
)

"%DOCKER_EXE%" compose ^
    -f docker-compose.yml ^
    -f docker-compose.dev.yml ^
    --profile init ^
    --profile production ^
    down --remove-orphans
set "COMPOSE_EXIT=%ERRORLEVEL%"
popd

if not "%COMPOSE_EXIT%"=="0" (
    echo [!] Khong the don Docker Compose resources.
    endlocal & exit /b %COMPOSE_EXIT%
)

:done
echo.
echo Da dung tat ca cac dich vu!
echo Cac named volume, bao gom du lieu PostgreSQL, van duoc giu nguyen.
endlocal
exit /b 0
