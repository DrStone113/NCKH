#!/bin/bash
# ============================================================
# setup.sh — Tự động cài đặt môi trường MedicalBot (Linux/WSL2)
# Yêu cầu: Ubuntu 20.04/22.04, Python 3.10, GPU NVIDIA (tuỳ chọn)
# Sử dụng: bash setup.sh
# ============================================================

set -e  # Dừng nếu có lỗi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

info "=== MedicalBot Setup ==="
info "Project: $PROJECT_DIR"

# ── 1. Kiểm tra Python 3.10 ──────────────────────────────────
info "Kiểm tra Python..."
if ! command -v python3.10 &>/dev/null; then
    warn "Python 3.10 chưa cài. Đang cài..."
    sudo apt update -qq
    sudo apt install -y python3.10 python3.10-venv python3.10-dev python3-pip
fi
python3.10 --version

# ── 2. Tạo virtual environment ───────────────────────────────
info "Tạo virtual environment tại $VENV_DIR..."
if [ ! -d "$VENV_DIR" ]; then
    python3.10 -m venv "$VENV_DIR"
    info "Đã tạo venv."
else
    warn "venv đã tồn tại, bỏ qua."
fi
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel -q

# ── 3. Kiểm tra GPU ──────────────────────────────────────────
info "Kiểm tra GPU..."
HAS_GPU=false
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    HAS_GPU=true
    info "GPU phát hiện — sẽ cài TensorFlow GPU."
else
    warn "Không tìm thấy GPU — sẽ cài TensorFlow CPU."
fi

# ── 4. Cài PyTorch (luôn dùng CUDA nếu có GPU) ───────────────
info "Cài PyTorch..."
if [ "$HAS_GPU" = true ]; then
    pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 \
        --index-url https://download.pytorch.org/whl/cu121 -q
else
    pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 \
        --index-url https://download.pytorch.org/whl/cpu -q
fi

# ── 5. Cài TensorFlow ────────────────────────────────────────
info "Cài TensorFlow..."
if [ "$HAS_GPU" = true ]; then
    pip install "tensorflow[and-cuda]==2.12.0" -q
else
    pip install tensorflow-cpu==2.12.0 -q
fi

# ── 6. Cài các thư viện còn lại ──────────────────────────────
info "Cài dependencies..."
pip install \
    rasa==3.6.20 \
    sentence-transformers==2.7.0 \
    transformers==4.36.0 \
    tokenizers==0.15.2 \
    "huggingface-hub==0.23.0" \
    pandas==2.0.3 \
    pyarrow==12.0.1 \
    openpyxl==3.1.2 \
    "numpy>=1.19.2,<1.24" \
    "networkx>=2.4,<2.7" \
    "regex>=2020.6,<2022.11" \
    scikit-learn==1.1.3 \
    deep-translator==1.11.4 \
    requests==2.31.0 \
    sentencepiece==0.1.99 \
    sacremoses==0.1.1 \
    -q

# ── 7. Kiểm tra TF nhận GPU ──────────────────────────────────
info "Kiểm tra TensorFlow GPU..."
python -c "
import tensorflow as tf
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    print(f'  ✅ TF nhận {len(gpus)} GPU: {[g.name for g in gpus]}')
else:
    print('  ⚠️  TF không nhận GPU (sẽ dùng CPU)')
"

# ── 8. Kiểm tra PyTorch GPU ──────────────────────────────────
info "Kiểm tra PyTorch GPU..."
python -c "
import torch
if torch.cuda.is_available():
    print(f'  ✅ PyTorch CUDA: {torch.cuda.get_device_name(0)}')
else:
    print('  ⚠️  PyTorch không nhận GPU')
"

info "=== Setup hoàn tất! ==="
echo ""
echo "Kích hoạt môi trường:  source $VENV_DIR/bin/activate"
echo "Chuẩn bị dữ liệu:      python scripts/prepare_data.py --dataset-dir dataset/ --db-path knowledge_base/health_kb.db --output-dir data/"
echo "Build embeddings:      python scripts/build_embeddings.py --db-path knowledge_base/health_kb.db"
echo "Train Rasa:            rasa train"
echo "Chạy Action Server:    rasa run actions"
echo "Chạy Rasa Server:      rasa run --enable-api --cors \"*\" --port 5005"
