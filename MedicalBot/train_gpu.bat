@echo off
echo ========================================
echo Train Rasa voi GPU (RTX 4060)
echo ========================================

:: Bat buoc TensorFlow dung GPU
set TF_FORCE_GPU_ALLOW_GROWTH=true
set CUDA_VISIBLE_DEVICES=0

:: Tat warning khong can thiet
set TF_CPP_MIN_LOG_LEVEL=2
set SQLALCHEMY_SILENCE_UBER_WARNING=1

:: Kiem tra GPU
python -c "import tensorflow as tf; gpus = tf.config.list_physical_devices('GPU'); print('GPUs:', gpus)"

echo.
echo Bat dau train...
rasa train --config config.yml --domain domain.yml --data data/

echo.
echo Hoan tat! Nhan phim bat ky de dong...
pause
