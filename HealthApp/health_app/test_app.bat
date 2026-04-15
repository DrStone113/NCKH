@echo off
echo ====================================
echo Kiem tra ung dung Health App
echo ====================================
echo.

cd /d "%~dp0"
set PATH=%CD%\..\flutter\bin;%PATH%

echo [1] Kiem tra Flutter doctor...
call ..\flutter\bin\flutter.bat doctor -v

echo.
echo [2] Kiem tra thiet bi ket noi...
call ..\flutter\bin\flutter.bat devices

echo.
echo [3] Phan tich code...
call ..\flutter\bin\flutter.bat analyze

echo.
echo ====================================
echo Kiem tra hoan tat!
echo ====================================
pause
