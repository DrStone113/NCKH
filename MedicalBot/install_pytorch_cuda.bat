@echo off
echo ========================================
echo Cai PyTorch voi CUDA cho RTX 4060
echo ========================================
echo.

echo Dang go cai dat PyTorch cu...
pip uninstall -y torch torchvision torchaudio

echo.
echo Dang cai PyTorch voi CUDA 12.1...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo.
echo Kiem tra CUDA...
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

echo.
echo Xong! Nhan phim bat ky de dong...
pause
