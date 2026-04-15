@echo off
REM Development mode - Chay voi hot reload va debug
cd /d "%~dp0"
set PATH=%CD%\..\flutter\bin;%PATH%

echo ====================================
echo Development Mode - Hot Reload Enabled
echo ====================================
echo.
echo Nhan 'r' de hot reload
echo Nhan 'R' de hot restart
echo Nhan 'q' de thoat
echo.

..\flutter\bin\flutter.bat run -d chrome --web-port=53209 --hot --verbose
