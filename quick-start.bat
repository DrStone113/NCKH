@echo off
setlocal EnableDelayedExpansion
title HealthApp Quick Start
color 0B

REM ==========================================
REM  QUICK START - KHOI DONG NHANH
REM ==========================================

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%HealthApp\ai_backend\backend"
set "FLUTTER_DIR=%ROOT%HealthApp\health_app"
set "VENV_PYTHON=%BACKEND_DIR%\venv\Scripts\python.exe"

REM Port Configuration
set "PORT_OLLAMA=11434"
set "PORT_BACKEND=8080"
set "PORT_FLUTTER=3000"

echo.
echo  ==========================================
echo    HealthApp Quick Start
echo  ==========================================
echo.
echo  [*] Dang khoi dong cac dich vu...
echo.

REM ==========================================
REM  1. KHOI DONG OLLAMA
REM ==========================================
echo  [1/3] Khoi dong Ollama...
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] Ollama chua duoc cai dat
    echo  [*] Bo qua Ollama
    goto START_BACKEND
)

REM Kiem tra xem Ollama da chay chua
netstat -ano 2>nul | findstr ":%PORT_OLLAMA% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] Ollama da dang chay
) else (
    start "Ollama Server" ollama serve
    timeout /t 3 /nobreak >nul
    echo  [OK] Ollama da khoi dong
)

REM ==========================================
REM  2. KHOI DONG BACKEND
REM ==========================================
:START_BACKEND
echo.
echo  [2/3] Khoi dong Backend...

if not exist "%VENV_PYTHON%" (
    echo  [!] Python environment chua duoc cai dat
    echo  [*] Chay 'dev.bat' va chon [4] de cai dat dependencies
    pause
    exit /b 1
)

REM Kiem tra xem Backend da chay chua
netstat -ano 2>nul | findstr ":%PORT_BACKEND% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] Backend da dang chay
) else (
    pushd "%BACKEND_DIR%"
    start "FastAPI Backend" cmd /k "%VENV_PYTHON%" -m uvicorn main:app --host 0.0.0.0 --port %PORT_BACKEND% --reload
    popd
    timeout /t 4 /nobreak >nul
    echo  [OK] Backend da khoi dong
)

REM ==========================================
REM  3. KHOI DONG FLUTTER
REM ==========================================
echo.
echo  [3/3] Khoi dong Flutter...

REM Tim Flutter command
set "FLUTTER_CMD="
where flutter >nul 2>&1 && set "FLUTTER_CMD=flutter"
if "%FLUTTER_CMD%"=="" (
    set "FLUTTER_SDK=%ROOT%HealthApp\flutter\bin\flutter.bat"
    if exist "!FLUTTER_SDK!" set "FLUTTER_CMD=!FLUTTER_SDK!"
)

if "%FLUTTER_CMD%"=="" (
    echo  [!] Flutter chua duoc cai dat
    pause
    exit /b 1
)

REM Kiem tra xem Flutter da chay chua
netstat -ano 2>nul | findstr ":%PORT_FLUTTER% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] Flutter da dang chay
) else (
    pushd "%FLUTTER_DIR%"
    start "Flutter Web" cmd /k "%FLUTTER_CMD%" run -d web-server --web-port %PORT_FLUTTER%
    popd
    timeout /t 2 /nobreak >nul
    echo  [OK] Flutter dang khoi dong
    echo  [*] Mo trinh duyet va truy cap: http://localhost:%PORT_FLUTTER%
)

REM ==========================================
REM  HOAN TAT
REM ==========================================
echo.
echo  ==========================================
echo   KHOI DONG HOAN TAT!
echo  ==========================================
echo.
echo   Ollama  : http://localhost:%PORT_OLLAMA%
echo   Backend : http://localhost:%PORT_BACKEND%
echo   API Docs: http://localhost:%PORT_BACKEND%/docs
echo   Flutter : http://localhost:%PORT_FLUTTER%
echo.
echo  [*] Cac dich vu dang chay trong cac cua so rieng biet
echo  [*] Xem cac cua so de theo doi logs va debug
echo  [*] Dong cua so nay de giu cac dich vu chay
echo  [*] Chay 'stop-all.bat' de dung tat ca dich vu
echo.
echo  ==========================================
echo.
echo  [*] Mo Flutter trong trinh duyet?
echo      URL: http://localhost:%PORT_FLUTTER%
echo.
set "OPEN_BROWSER="
set /p OPEN_BROWSER="  Mo trinh duyet? (Y/N): "

if /i "!OPEN_BROWSER!"=="Y" (
    echo  [*] Dang mo trinh duyet...
    start http://localhost:%PORT_FLUTTER%
)

exit
