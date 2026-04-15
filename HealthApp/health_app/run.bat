@echo off
echo ====================================
echo Health App - Ung dung Quan ly Suc khoe
echo ====================================
echo.

cd /d "%~dp0"

REM Kiem tra Flutter nhanh (khong hien thi output)
if not exist "..\flutter\bin\flutter.bat" (
    echo [ERROR] Khong tim thay Flutter SDK!
    pause
    exit /b 1
)

set PATH=%CD%\..\flutter\bin;%PATH%

REM Kiem tra xem da pub get chua (kiem tra .dart_tool)
if not exist ".dart_tool\package_config.json" (
    echo [1/2] Cai dat dependencies lan dau...
    call ..\flutter\bin\flutter.bat pub get >nul 2>&1
) else (
    echo [1/2] Dependencies da duoc cai dat, bo qua...
)

echo [2/2] Chay ung dung...
echo.

REM Chay truc tiep khong pause
call ..\flutter\bin\flutter.bat run -d chrome --web-port=53209

REM Chi pause neu co loi
if errorlevel 1 pause
