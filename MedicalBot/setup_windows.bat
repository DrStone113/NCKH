@echo off
:: ============================================================
:: setup_windows.bat — Cài đặt môi trường MedicalBot (Windows)
:: Yêu cầu: Python 3.10, pip
:: Lưu ý: TensorFlow GPU KHÔNG hỗ trợ trên Windows từ TF 2.11+
::         Dùng WSL2 để train GPU (xem SETUP_GUIDE.md)
:: ============================================================

echo ========================================
echo  MedicalBot Setup (Windows)
echo ========================================
echo.

:: Kiểm tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python chua duoc cai. Tai tai: https://www.python.org/downloads/release/python-31011/
    pause & exit /b 1
)

:: Tạo venv
if not exist "venv" (
    echo [INFO] Tao virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

:: Upgrade pip
echo [INFO] Upgrade pip...
python -m pip install --upgrade pip setuptools==67.8.0 wheel -q

:: Cài PyTorch CUDA
echo [INFO] Cai PyTorch CUDA 12.1...
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 --index-url https://download.pytorch.org/whl/cu121 -q

:: Cài TF (CPU only trên Windows)
echo [INFO] Cai TensorFlow (CPU - Windows khong ho tro GPU TF)...
pip install tensorflow==2.12.0 -q

:: Cài dependencies
echo [INFO] Cai dependencies...
pip install ^
    rasa==3.6.20 ^
    sentence-transformers==2.7.0 ^
    transformers==4.36.0 ^
    tokenizers==0.15.2 ^
    huggingface-hub==0.23.0 ^
    pandas==2.0.3 ^
    pyarrow==12.0.1 ^
    openpyxl==3.1.2 ^
    scikit-learn==1.1.3 ^
    deep-translator==1.11.4 ^
    requests==2.31.0 ^
    sentencepiece==0.1.99 ^
    sacremoses==0.1.1 ^
    -q

:: Fix conflict packages
echo [INFO] Fix conflict packages...
pip install "numpy>=1.19.2,<1.24" "networkx>=2.4,<2.7" "regex>=2020.6,<2022.11" --force-reinstall -q

:: Kiểm tra
echo.
echo [INFO] Kiem tra cai dat...
python -c "import torch; print('PyTorch CUDA:', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
python -c "import tensorflow as tf; print('TF GPUs:', tf.config.list_physical_devices('GPU'))"
python -c "import rasa; print('Rasa:', rasa.__version__)"

echo.
echo ========================================
echo  Setup hoan tat!
echo ========================================
echo.
echo Kich hoat moi truong : venv\Scripts\activate
echo Chuan bi du lieu     : python scripts\prepare_data.py --dataset-dir dataset/ --db-path knowledge_base/health_kb.db --output-dir data/
echo Build embeddings     : python scripts\build_embeddings.py --db-path knowledge_base\health_kb.db
echo Train Rasa           : rasa train
echo Chay Action Server   : rasa run actions
echo Chay Rasa Server     : rasa run --enable-api --cors "*" --port 5005
echo.
pause
