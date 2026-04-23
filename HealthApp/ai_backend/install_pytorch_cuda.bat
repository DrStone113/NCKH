@echo off
echo ========================================
echo CAI DAT PYTORCH VOI CUDA SUPPORT
echo ========================================
echo.

REM Kich hoat virtual environment neu co
if exist venv (
    call venv\Scripts\activate.bat
)

echo [INFO] Kiem tra GPU hien tai...
python check_gpu.py
echo.

echo [INFO] Gỡ cài đặt PyTorch cũ...
pip uninstall -y torch torchvision torchaudio
echo.

echo [INFO] Cài đặt PyTorch với CUDA 12.1...
echo (Qua trinh nay co the mat 5-10 phut)
echo.
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo.
echo [INFO] Kiem tra lai GPU sau khi cai dat...
python check_gpu.py

echo.
echo ========================================
echo HOAN TAT!
echo ========================================
echo.
echo Neu GPU van chua hoat dong:
echo 1. Kiem tra NVIDIA driver: nvidia-smi
echo 2. Kiem tra CUDA Toolkit da cai chua
echo 3. Khoi dong lai terminal va chay lai script
echo.
pause
