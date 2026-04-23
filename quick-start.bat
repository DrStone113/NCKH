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
    echo  [!] Ollama chua duoc cai dat - Dang tu dong cai dat...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://ollama.com/install.ps1 | iex"
    if errorlevel 1 (
        echo  [LOI] Cai dat Ollama that bai. Vui long cai thu cong tai: https://ollama.com
        echo  [*] Bo qua Ollama, tiep tuc...
        goto START_BACKEND
    )
    echo  [OK] Cai dat Ollama thanh cong
    echo.
    echo  ==========================================
    echo   YEU CAU KHOI DONG LAI TERMINAL
    echo  ==========================================
    echo.
    echo  Ollama vua duoc cai dat nhung can khoi dong
    echo  lai terminal de cap nhat PATH.
    echo.
    echo  Vui long:
    echo    1. Dong cua so nay
    echo    2. Mo lai quick-start.bat
    echo.
    pause
    exit /b 0
)

REM Kiem tra xem Ollama da chay chua
netstat -ano 2>nul | findstr ":%PORT_OLLAMA% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] Ollama da dang chay
) else (
    start "Ollama Server" ollama serve
    timeout /t 8 /nobreak >nul
    echo  [OK] Ollama da khoi dong
)

REM Pull model (neu da co ollama se bo qua, khong tai lai)
echo  [Ollama] Dang kiem tra va cap nhat model llama3:8b-instruct-q4_K_M...
ollama pull llama3:8b-instruct-q4_K_M
if errorlevel 1 (
    echo  [CANH BAO] Khong the tai model. Chatbot se khong hoat dong.
) else (
    echo  [OK] Model san sang
)

REM ==========================================
REM  2. KHOI DONG BACKEND
REM ==========================================
:START_BACKEND
echo.
echo  [2/3] Khoi dong Backend...

REM Tim Python
set "PYTHON_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 set "PYTHON_CMD=python"
if "!PYTHON_CMD!"=="" (
    where py >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_CMD=py"
)
if "!PYTHON_CMD!"=="" (
    echo  [LOI] Khong tim thay Python. Vui long cai Python truoc.
    pause
    exit /b 1
)
echo  [Python] Tim thay: !PYTHON_CMD!

REM Tao venv neu chua co
if not exist "%VENV_PYTHON%" (
    echo  [Setup] Tao virtual environment...
    !PYTHON_CMD! -m venv "%BACKEND_DIR%\venv"
    if errorlevel 1 (
        echo  [LOI] Khong the tao venv.
        pause
        exit /b 1
    )
    echo  [OK] Tao venv thanh cong
)

REM Tao .env neu chua co
set "ENV_FILE=%ROOT%HealthApp\ai_backend\.env"
set "ENV_EXAMPLE=%ROOT%HealthApp\ai_backend\.env.example"
if not exist "!ENV_FILE!" (
    if exist "!ENV_EXAMPLE!" (
        echo  [Setup] Tao file .env tu .env.example...
        copy "!ENV_EXAMPLE!" "!ENV_FILE!" >nul
        echo  [OK] Tao .env thanh cong - Kiem tra va chinh sua neu can: HealthApp\ai_backend\.env
    ) else (
        echo  [CANH BAO] Khong tim thay .env.example
    )
) else (
    echo  [OK] File .env da ton tai
)

REM Cai torch voi CUDA neu chua co (phai cai truoc requirements)
"%BACKEND_DIR%\venv\Scripts\python.exe" -c "import torch; assert torch.cuda.is_available()" >nul 2>&1
if errorlevel 1 (
    echo  [Setup] Cai PyTorch voi CUDA 12.4 cho GPU...
    "%BACKEND_DIR%\venv\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cu124
    if errorlevel 1 (
        echo  [CANH BAO] Cai torch CUDA that bai, dung ban CPU
    ) else (
        echo  [OK] PyTorch CUDA da san sang
    )
) else (
    echo  [OK] PyTorch CUDA da co san
)

REM Cai dependencies neu chua co hoac requirements thay doi
echo  [Setup] Cai dat dependencies...
"%BACKEND_DIR%\venv\Scripts\pip.exe" install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    echo  [LOI] Cai dat dependencies that bai.
    pause
    exit /b 1
)
echo  [OK] Dependencies da san sang

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

REM Sync wger data vao RAG (chi chay lan dau hoac khi can cap nhat)
set "SYNC_FLAG=%BACKEND_DIR%\.wger_synced"
if not exist "!SYNC_FLAG!" (
    echo  [RAG] Chua co du lieu wger - Dang dong bo bai tap va thuc pham vao AI...
    echo  [RAG] Qua trinh nay co the mat 5-15 phut lan dau, vui long cho...
    pushd "%BACKEND_DIR%"
    "%VENV_PYTHON%" -m scripts.sync_wger
    if errorlevel 1 (
        echo  [CANH BAO] Dong bo wger that bai - AI se khong co du lieu bai tap
    ) else (
        echo. > "!SYNC_FLAG!"
        echo  [OK] Dong bo wger hoan tat - AI da co du lieu bai tap va thuc pham
    )
    popd
) else (
    echo  [OK] Du lieu wger da duoc dong bo truoc do
)

REM ==========================================
REM  3. KHOI DONG FLUTTER
REM ==========================================
echo.
echo  [3/3] Khoi dong Flutter...

REM Tim Flutter command
set "FLUTTER_CMD="
where flutter >nul 2>&1
if %errorlevel% equ 0 set "FLUTTER_CMD=flutter"
if "!FLUTTER_CMD!"=="" (
    set "FLUTTER_SDK=%ROOT%HealthApp\flutter\bin\flutter.bat"
    if exist "!FLUTTER_SDK!" set "FLUTTER_CMD=!FLUTTER_SDK!"
)

if "!FLUTTER_CMD!"=="" (
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

echo.
pause
exit /b 0
