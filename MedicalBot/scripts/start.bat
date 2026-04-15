@echo off
chcp 65001 >nul
echo ========================================
echo   CHATBOT Y TẾ - RASA
echo   Đề tài: THS2025-78
echo ========================================
echo.

:menu
echo Chọn chức năng:
echo 1. Merge domain_faq.yml vào domain.yml
echo 2. Train model
echo 3. Chạy action server
echo 4. Chạy chatbot (shell)
echo 5. Chạy API server
echo 6. Tạo lại training data
echo 0. Thoát
echo.

set /p choice="Nhập lựa chọn (0-6): "

if "%choice%"=="1" goto merge
if "%choice%"=="2" goto train
if "%choice%"=="3" goto actions
if "%choice%"=="4" goto shell
if "%choice%"=="5" goto api
if "%choice%"=="6" goto generate
if "%choice%"=="0" goto end
goto menu

:merge
echo.
echo Đang merge domain files...
python merge_domain.py
echo.
pause
goto menu

:train
echo.
echo Đang train model (có thể mất 10-30 phút)...
rasa train
echo.
pause
goto menu

:actions
echo.
echo Đang khởi động action server...
echo (Nhấn Ctrl+C để dừng)
rasa run actions
pause
goto menu

:shell
echo.
echo Đang khởi động chatbot shell...
echo (Nhấn Ctrl+C hoặc gõ /stop để dừng)
rasa shell
pause
goto menu

:api
echo.
echo Đang khởi động API server...
echo (Nhấn Ctrl+C để dừng)
rasa run --enable-api --cors "*"
pause
goto menu

:generate
echo.
echo Đang tạo lại training data...
python train_data_generator.py
echo.
pause
goto menu

:end
echo.
echo Tạm biệt!
exit
