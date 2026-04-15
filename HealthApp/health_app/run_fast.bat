@echo off
REM Script chay nhanh nhat - Bo qua tat ca kiem tra
cd /d "%~dp0"
set PATH=%CD%\..\flutter\bin;%PATH%

REM Chay truc tiep voi hot reload
..\flutter\bin\flutter.bat run -d chrome --web-port=53209 --hot
