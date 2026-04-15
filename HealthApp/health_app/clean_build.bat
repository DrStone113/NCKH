@echo off
echo ====================================
echo Clean Build - Xoa cache va build lai
echo ====================================
echo.

cd /d "%~dp0"
set PATH=%CD%\..\flutter\bin;%PATH%

echo [1/4] Cleaning Flutter cache...
call ..\flutter\bin\flutter.bat clean

echo.
echo [2/4] Xoa pub cache...
rd /s /q .dart_tool 2>nul
rd /s /q build 2>nul

echo.
echo [3/4] Get dependencies...
call ..\flutter\bin\flutter.bat pub get

echo.
echo [4/4] Rebuild...
call ..\flutter\bin\flutter.bat build web --release

echo.
echo Clean build hoan tat!
pause
