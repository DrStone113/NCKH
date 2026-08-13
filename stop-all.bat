@echo off
title HealthApp - Dung Tat Ca Service

echo ========================================================
echo   DANG DUNG TAT CA DICH VU HEALTHAPP
echo ========================================================
echo.

:: Stop processes on port 8080 (Backend) and port 3000 (Flutter Web)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do taskkill /f /pid %%a >nul 2>&1

:: Stop Docker container
echo Dung container Database...

REM Detect Docker Desktop path
set DOCKER_CMD=docker
if exist "%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" (
    set DOCKER_CMD="%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
)
if exist "C:\Program Files\Docker\Docker\resources\bin\docker.exe" (
    set DOCKER_CMD="C:\Program Files\Docker\Docker\resources\bin\docker.exe"
)

%DOCKER_CMD% compose stop postgres

echo.
echo Da dung tat ca cac dich vu!
timeout /t 3 >nul
