@echo off
echo ====================================
echo Cai dat Health App
echo ====================================
echo.

cd /d "%~dp0"

echo [1/4] Kiem tra Flutter...
if not exist "..\flutter\bin\flutter.bat" (
    echo Loi: Khong tim thay Flutter SDK!
    pause
    exit /b 1
)

set PATH=%CD%\..\flutter\bin;%PATH%

echo Flutter SDK: OK
echo.

echo [2/4] Kiem tra Flutter doctor...
call ..\flutter\bin\flutter.bat doctor

echo.
echo [3/4] Cai dat dependencies...
call ..\flutter\bin\flutter.bat pub get

echo.
echo [4/4] Tao cau truc thu muc...
if not exist "android\app" mkdir android\app

echo.
echo ====================================
echo Cai dat hoan tat!
echo ====================================
echo.
echo Buoc tiep theo:
echo 1. Tao Firebase project tai: https://console.firebase.google.com
echo 2. Them Android app vao Firebase project
echo 3. Tai file google-services.json
echo 4. Sao chep google-services.json vao: health_app\android\app\
echo 5. Chay run.bat de khoi dong ung dung
echo.
pause
