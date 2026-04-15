@echo off
chcp 65001 >nul
echo ========================================
echo   TẠO LẠI VIRTUAL ENVIRONMENT
echo ========================================
echo.

REM Kiểm tra Python 3.10
py -3.10 --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 3.10 không tìm thấy!
    pause
    exit /b 1
)

echo ✅ Python 3.10 đã sẵn sàng
echo.

REM Xóa venv cũ nếu tồn tại
if exist "venv" (
    echo 🗑️ Đang xóa virtual environment cũ...
    rmdir /s /q venv
    echo ✅ Đã xóa venv cũ
    echo.
)

REM Tạo venv mới
echo 📦 Đang tạo virtual environment mới...
py -3.10 -m venv venv
if errorlevel 1 (
    echo ❌ Không thể tạo virtual environment!
    pause
    exit /b 1
)
echo ✅ Đã tạo venv mới
echo.

REM Kích hoạt venv
call venv\Scripts\activate

REM Upgrade pip
echo 📥 Đang upgrade pip...
python -m pip install --upgrade pip setuptools wheel --quiet
echo ✅ Đã upgrade pip
echo.

REM Cài RASA
echo 📥 Đang cài đặt RASA 3.6.0 (có thể mất 5-10 phút)...
echo Vui lòng đợi...
pip install rasa==3.6.0

if errorlevel 1 (
    echo.
    echo ⚠️ Lỗi khi cài RASA 3.6.0
    echo Thử cài RASA 3.5.17...
    pip install rasa==3.5.17
)

echo.

REM Cài rasa-sdk
echo 📥 Đang cài đặt rasa-sdk...
pip install rasa-sdk==3.6.0
echo.

REM Kiểm tra
echo ========================================
echo   KIỂM TRA CÀI ĐẶT
echo ========================================
echo.

rasa --version

if errorlevel 1 (
    echo ❌ Cài đặt không thành công
) else (
    echo.
    echo ✅ CÀI ĐẶT THÀNH CÔNG!
    echo.
    echo Bước tiếp theo:
    echo 1. python merge_domain.py
    echo 2. rasa train
    echo 3. rasa shell
)

echo.
pause
