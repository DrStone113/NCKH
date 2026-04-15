@echo off
chcp 65001 >nul
echo ========================================
echo   TRAIN RASA MODEL - FINAL
echo ========================================
echo.

call venv\Scripts\activate

echo [1/3] Fix duplicate responses trong domain.yml...
python fix_duplicate_responses.py
echo.

echo [2/3] Validate domain.yml...
rasa data validate --domain domain.yml
if errorlevel 1 (
    echo ⚠️ Có warning trong domain.yml, nhưng tiếp tục train...
)
echo.

echo [3/3] Train model (10-30 phút)...
echo Vui lòng đợi...
echo.
rasa train

if errorlevel 1 (
    echo.
    echo ❌ Train thất bại!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   ✅ TRAIN THÀNH CÔNG!
echo ========================================
echo.
echo Model đã được lưu trong: models/
echo.
echo Bước tiếp theo:
echo   Terminal 1: rasa run actions
echo   Terminal 2: rasa shell
echo.
pause
