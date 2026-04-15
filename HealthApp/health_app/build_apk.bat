@echo off
echo ====================================
echo Build APK - Health App
echo ====================================
echo.

cd /d "%~dp0"
set PATH=%CD%\..\flutter\bin;%PATH%

REM Khong clean neu khong can thiet (tiet kiem thoi gian)
set /p CLEAN="Clean project truoc khi build? (y/N): "
if /i "%CLEAN%"=="y" (
    echo [1/4] Cleaning project...
    call ..\flutter\bin\flutter.bat clean
) else (
    echo [1/4] Bo qua clean, build nhanh hon...
)

echo.
echo [2/4] Get dependencies...
call ..\flutter\bin\flutter.bat pub get

echo.
echo [3/4] Build APK (release mode)...
REM Them cac flag toi uu
call ..\flutter\bin\flutter.bat build apk --release --split-per-abi --obfuscate --split-debug-info=build/debug-info

echo.
echo [4/4] Toi uu APK...
echo - Split per ABI: Tao APK rieng cho tung kien truc CPU
echo - Obfuscate: Ma hoa code de bao mat
echo - Split debug info: Tach debug info de giam kich thuoc

echo.
echo ====================================
echo Build hoan tat!
echo ====================================
echo.
echo Cac file APK:
dir /b build\app\outputs\flutter-apk\*.apk
echo.
echo Vi tri: build\app\outputs\flutter-apk\
echo.
pause
