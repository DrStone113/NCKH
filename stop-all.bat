@echo off
title HealthApp - Dung Tat Ca Service

echo ========================================================
echo   DANG DUNG TAT CA DICH VU HEALTHAPP
echo ========================================================
echo.

:: The backend runs in Docker; only the host static web server owns port 3000.
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do taskkill /f /pid %%a >nul 2>&1

:: Stop Docker container
echo Dung container Database...

REM Detect Docker Desktop path
set "DOCKER_EXE=docker"
if exist "%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" (
    set "DOCKER_EXE=%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
)
if exist "C:\Program Files\Docker\Docker\resources\bin\docker.exe" (
    set "DOCKER_EXE=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
)

"%DOCKER_EXE%" compose -f docker-compose.yml -f docker-compose.dev.yml stop fastapi_backend postgres

echo.
echo Da dung tat ca cac dich vu!
powershell.exe -NoProfile -Command "Start-Sleep -Seconds 3"
exit /b 0
