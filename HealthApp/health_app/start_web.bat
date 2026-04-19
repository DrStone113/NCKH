@echo off
title AI Health Chatbot - Flutter Web
echo ========================================
echo   AI Health Chatbot - Flutter Web
echo ========================================
echo.

REM Kiem tra Flutter
flutter --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Flutter. Vui long cai Flutter truoc.
    pause
    exit /b 1
)

REM flutter pub get neu chua co packages
if not exist ".dart_tool" (
    echo [Setup] Chay flutter pub get...
    flutter pub get
    echo.
)

echo [Flutter] Khoi dong app tren Chrome...
echo [Flutter] Backend phai dang chay tai http://localhost:8000
echo [Flutter] Nhan Ctrl+C de dung
echo.
flutter run -d chrome --web-port 3000

pause
