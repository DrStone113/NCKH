@echo off
setlocal EnableExtensions
title HealthApp - Dung Tat Ca Service

set "ROOT_DIR=%~dp0"
set "CLEANUP_SCRIPT=%~dp0scripts\cleanup-generated.ps1"
set "COMPOSE_EXIT=0"
set "CLEANUP_EXIT=0"

echo ========================================================
echo   DANG DUNG TAT CA DICH VU HEALTHAPP
echo ========================================================
echo.

:: The backend runs in Docker; only the host static web server owns port 3000.
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /R /C:":3000 .*LISTENING"') do taskkill /t /f /pid %%a >nul 2>&1

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
    goto cleanup
)

"%DOCKER_EXE%" compose ^
    -f docker-compose.yml ^
    -f docker-compose.dev.yml ^
    --profile init ^
    --profile production ^
    down --remove-orphans
set "COMPOSE_EXIT=%ERRORLEVEL%"
popd

:cleanup
echo.
echo Don artefact tam cua project...
if exist "%CLEANUP_SCRIPT%" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CLEANUP_SCRIPT%" -Phase Stop
    if errorlevel 1 set "CLEANUP_EXIT=1"
) else (
    echo [!] Khong tim thay cleanup helper: %CLEANUP_SCRIPT%
    set "CLEANUP_EXIT=1"
)

:done
echo.
if not "%COMPOSE_EXIT%"=="0" echo [!] Khong the don het Docker Compose resources.
if not "%CLEANUP_EXIT%"=="0" echo [!] Cleanup artefact tam chua hoan tat.
if "%COMPOSE_EXIT%"=="0" if "%CLEANUP_EXIT%"=="0" echo Da dung va don dep tat ca cac dich vu!
echo Cac named volume, bao gom du lieu PostgreSQL, van duoc giu nguyen.

if not "%COMPOSE_EXIT%"=="0" goto exit_compose_error
if not "%CLEANUP_EXIT%"=="0" goto exit_cleanup_error
endlocal & exit /b 0

:exit_compose_error
endlocal & exit /b %COMPOSE_EXIT%

:exit_cleanup_error
endlocal & exit /b %CLEANUP_EXIT%
