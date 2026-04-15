# MedicalBot — Hướng dẫn cài đặt

## Yêu cầu hệ thống
- Python 3.10 (bắt buộc — Rasa 3.6.20 không hỗ trợ 3.11+)
- RAM: 8GB+ (khuyến nghị 16GB)
- GPU: NVIDIA (tuỳ chọn, xem bên dưới)
- Disk: ~10GB (model + dataset)

---

## Cách 1: Linux / WSL2 (khuyến nghị — hỗ trợ GPU)

### Cài WSL2 trên Windows (bỏ qua nếu đã có Linux)
```powershell
# PowerShell Admin
wsl --install
# Restart máy, sau đó cài Ubuntu 22.04 từ Microsoft Store
```

### Chạy script tự động
```bash
cd /mnt/c/NCKH/NCKH/MedicalBot   # hoặc đường dẫn project
bash setup.sh
source venv/bin/activate
```

### Kiểm tra GPU
```bash
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
# Kết quả mong đợi: [PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU')]
```

---

## Cách 2: Windows (CPU only — TF không hỗ trợ GPU từ v2.11+)

```bat
setup_windows.bat
venv\Scripts\activate
```

---

## Các bước chạy (sau khi setup)

```bash
# Bước 1: Chuẩn bị dữ liệu (chỉ chạy lần đầu hoặc khi dataset thay đổi)
python scripts/prepare_data.py \
    --dataset-dir dataset/ \
    --db-path knowledge_base/health_kb.db \
    --output-dir data/

# Bước 2: Build embeddings (chỉ chạy lần đầu — mất ~13 phút với GPU)
python scripts/build_embeddings.py \
    --db-path knowledge_base/health_kb.db

# Bước 3: Train Rasa
rasa train

# Bước 4: Chạy bot (2 terminal riêng)
rasa run actions                                    # Terminal 1
rasa run --enable-api --cors "*" --port 5005        # Terminal 2
```

---

## Lưu ý quan trọng

### Conflict packages (Windows)
Sau khi cài Rasa, một số package bị downgrade. Fix bằng:
```bash
pip install "numpy>=1.19.2,<1.24" "networkx>=2.4,<2.7" \
    "regex>=2020.6,<2022.11" --force-reinstall
```

### PyTorch CUDA (cho build_embeddings.py)
```bash
# Linux/WSL2
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 \
    --index-url https://download.pytorch.org/whl/cu121

# Windows
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 \
    --index-url https://download.pytorch.org/whl/cu121
```

### TensorFlow GPU (chỉ Linux/WSL2)
```bash
pip install "tensorflow[and-cuda]==2.12.0"
```

### Train với GPU (Linux/WSL2)
```bash
export TF_FORCE_GPU_ALLOW_GROWTH=true
export CUDA_VISIBLE_DEVICES=0
rasa train
```

---

## Phiên bản đã kiểm tra
| Package | Version |
|---------|---------|
| Python | 3.10.x |
| Rasa | 3.6.20 |
| TensorFlow | 2.12.0 |
| PyTorch | 2.1.0+cu121 |
| sentence-transformers | 2.7.0 |
| transformers | 4.36.0 |
| numpy | 1.23.5 |
| pandas | 2.0.3 |
