@echo off
cd /d "%~dp0"
setlocal EnableDelayedExpansion
title Stop All Services
color 0C

REM ==========================================
REM  STOP ALL SERVICES
REM ==========================================

set "PORT_OLLAMA=11434"
set "PORT_BACKEND=8080"
set "PORT_FLUTTER=3000"

echo.
echo  ==========================================
echo    DUNG TAT CA DICH VU
echo  ==========================================
echo.

REM ==========================================
REM  DUNG THEO PORT
REM ==========================================

echo  [*] Dang dung cac dich vu...
echo.

REM Dung Ollama
echo  [1/4] Dung Ollama (port %PORT_OLLAMA%)...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT_OLLAMA% " ^| findstr "LISTENING"') do (
    if not "%%a"=="0" (
        taskkill /f /pid %%a >nul 2>&1
        echo       Killed PID %%a
    )
)
REM Dung process Ollama theo ten
taskkill /f /im "ollama.exe" >nul 2>&1
echo  [OK] Ollama da dung

REM Dung Backend
echo.
echo  [2/4] Dung Backend (port %PORT_BACKEND%)...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT_BACKEND% " ^| findstr "LISTENING"') do (
    if not "%%a"=="0" (
        taskkill /f /pid %%a >nul 2>&1
        echo       Killed PID %%a
    )
)
echo  [OK] Backend da dung

REM Dung Flutter
echo.
echo  [3/4] Dung Flutter (port %PORT_FLUTTER%)...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT_FLUTTER% " ^| findstr "LISTENING"') do (
    if not "%%a"=="0" (
        taskkill /f /pid %%a >nul 2>&1
        echo       Killed PID %%a
    )
)
echo  [OK] Flutter da dung

REM Dong cac cua so terminal da mo
echo.
echo  [4/4] Dong cac cua so terminal...
REM Dong cac cua so co title cua chung ta
taskkill /fi "WINDOWTITLE eq Ollama Server" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq FastAPI Backend" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Flutter Web" /f >nul 2>&1
echo  [OK] Da dong cac cua so terminal

REM ==========================================
REM  HOAN TAT
REM ==========================================
echo.
echo  ==========================================
echo   DA DUNG TAT CA DICH VU!
echo  ==========================================
echo.
echo  [*] Tat ca cac dich vu da duoc dung
echo  [*] Chay 'quick-start.bat' de khoi dong lai
echo.

timeout /t 3 /nobreak >nul
exit
