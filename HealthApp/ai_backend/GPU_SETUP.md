# Hướng Dẫn Cấu Hình GPU cho AI Backend

## Tổng Quan

Backend sử dụng embedding model (sentence-transformers) để tạo vector embeddings cho RAG (Retrieval-Augmented Generation). Model này có thể chạy trên CPU hoặc GPU.

**Lợi ích khi sử dụng GPU:**
- Tăng tốc độ embedding 5-10x so với CPU
- Giảm thời gian response của chatbot
- Xử lý batch lớn hiệu quả hơn

## Yêu Cầu Hệ Thống

1. **NVIDIA GPU** với CUDA support (GTX 1060 trở lên khuyến nghị)
2. **NVIDIA Driver** phiên bản mới nhất
3. **CUDA Toolkit** 12.1 hoặc cao hơn
4. **Python 3.10+**
5. **PyTorch với CUDA support**

## Kiểm Tra GPU

### Bước 1: Kiểm tra NVIDIA Driver

Mở Command Prompt và chạy:

```bash
nvidia-smi
```

Nếu lệnh này hiển thị thông tin GPU (tên GPU, driver version, CUDA version), bạn đã cài driver thành công.

**Ví dụ output:**
```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.xx       Driver Version: 535.xx       CUDA Version: 12.2   |
|-------------------------------+----------------------+----------------------+
| GPU  Name            TCC/WDDM | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA GeForce ... WDDM  | 00000000:01:00.0  On |                  N/A |
```

Nếu lệnh không tìm thấy, cài NVIDIA Driver từ: https://www.nvidia.com/Download/index.aspx

### Bước 2: Kiểm tra PyTorch CUDA

Chạy script kiểm tra GPU:

```bash
python check_gpu.py
```

**Output mong đợi nếu GPU hoạt động:**
```
============================================================
KIỂM TRA GPU VÀ PYTORCH CUDA SUPPORT
============================================================

✓ PyTorch version: 2.x.x+cu121
✓ PyTorch CUDA available: True
✓ CUDA version: 12.1
✓ Number of GPUs: 1
  - GPU 0: NVIDIA GeForce RTX 3060
    Memory: 12.00 GB

✓ sentence-transformers installed

Testing embedding model on GPU...
✓ Embedding test successful! Shape: (384,)
✓ Model is on device: cuda

============================================================
```

**Nếu CUDA not available:**
```
✓ PyTorch version: 2.x.x+cpu
✗ CUDA not available
```

## Cài Đặt PyTorch với CUDA Support

### Cách 1: Sử dụng Script Tự Động (Khuyến nghị)

Chạy script cài đặt:

```bash
install_pytorch_cuda.bat
```

Script này sẽ:
1. Kích hoạt virtual environment
2. Gỡ cài đặt PyTorch cũ (nếu có)
3. Cài đặt PyTorch với CUDA 12.1 support

### Cách 2: Cài Đặt Thủ Công

1. Kích hoạt virtual environment:
```bash
cd HealthApp/ai_backend
backend\venv\Scripts\activate
```

2. Gỡ PyTorch cũ:
```bash
pip uninstall torch torchvision torchaudio -y
```

3. Cài PyTorch với CUDA 12.1:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

4. Kiểm tra lại:
```bash
python check_gpu.py
```

## Khởi Động Backend với GPU

### Cách 1: Sử dụng start_backend.bat (Tự động)

```bash
start_backend.bat
```

Script này sẽ:
1. Kiểm tra Docker (nếu có sẽ dùng Docker)
2. Nếu không có Docker, chạy local với Python
3. **Tự động kiểm tra GPU** trước khi khởi động
4. Khởi động FastAPI server

Backend sẽ tự động phát hiện và sử dụng GPU nếu có.

### Cách 2: Sử dụng restart_backend.bat

Nếu backend đang chạy và bạn muốn khởi động lại:

```bash
restart_backend.bat
```

### Cách 3: Khởi động thủ công

```bash
cd HealthApp/ai_backend
backend\venv\Scripts\activate
python check_gpu.py
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Xác Nhận GPU Đang Được Sử Dụng

Khi backend khởi động, kiểm tra log:

**GPU được sử dụng:**
```
INFO:     Loading embedding model on device: cuda
INFO:     Embedding model ready on cuda.
```

**CPU được sử dụng:**
```
INFO:     Loading embedding model on device: cpu
INFO:     Embedding model ready.
```

## Các File Đã Được Cấu Hình GPU

Backend đã được cấu hình để tự động sử dụng GPU trong các file sau:

1. **rag_service.py** - RAG service cho chatbot
   ```python
   device = "cuda" if torch.cuda.is_available() else "cpu"
   model = SentenceTransformer(settings.embedding_model, device=device)
   ```

2. **sync_wger.py** - Script đồng bộ dữ liệu wger
   ```python
   device = "cuda" if torch.cuda.is_available() else "cpu"
   model = SentenceTransformer(settings.embedding_model, device=device)
   ```

3. **load_dataset.py** - Script load dataset
   ```python
   device = "cuda" if torch.cuda.is_available() else "cpu"
   model = SentenceTransformer(settings.embedding_model, device=device)
   ```

## Troubleshooting

### Vấn đề 1: CUDA not available sau khi cài PyTorch

**Nguyên nhân:** PyTorch CPU version được cài thay vì CUDA version

**Giải pháp:**
```bash
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
python check_gpu.py
```

### Vấn đề 2: nvidia-smi không tìm thấy

**Nguyên nhân:** NVIDIA Driver chưa được cài hoặc GPU không được hệ thống nhận diện

**Giải pháp:**
1. Cài NVIDIA Driver từ: https://www.nvidia.com/Download/index.aspx
2. Khởi động lại máy tính
3. Chạy lại `nvidia-smi`

### Vấn đề 3: CUDA version mismatch

**Nguyên nhân:** PyTorch CUDA version không khớp với CUDA Toolkit

**Giải pháp:**
- Kiểm tra CUDA version từ `nvidia-smi`
- Cài PyTorch với CUDA version tương ứng:
  - CUDA 11.8: `--index-url https://download.pytorch.org/whl/cu118`
  - CUDA 12.1: `--index-url https://download.pytorch.org/whl/cu121`

### Vấn đề 4: Out of Memory (OOM)

**Nguyên nhân:** GPU memory không đủ

**Giải pháp:**
1. Giảm batch size trong `sync_wger.py`:
   ```python
   EMBED_BATCH_SIZE = 32  # Giảm từ 64
   ```

2. Hoặc sử dụng model nhỏ hơn trong `.env`:
   ```
   EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
   ```

### Vấn đề 5: Backend vẫn dùng CPU dù GPU available

**Nguyên nhân:** Virtual environment không dùng PyTorch CUDA version

**Giải pháp:**
1. Đảm bảo đang ở trong venv:
   ```bash
   backend\venv\Scripts\activate
   ```

2. Kiểm tra PyTorch version:
   ```bash
   python -c "import torch; print(torch.__version__)"
   ```
   
   Phải có `+cu121` hoặc `+cu118` ở cuối version

3. Nếu không có, cài lại PyTorch trong venv:
   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cu121 --force-reinstall
   ```

## Hiệu Suất So Sánh

| Thao tác | CPU (i7-10700) | GPU (RTX 3060) | Tăng tốc |
|----------|----------------|----------------|----------|
| Embed 1 text | ~50ms | ~10ms | 5x |
| Embed 64 texts (batch) | ~2000ms | ~200ms | 10x |
| Sync 1000 exercises | ~120s | ~20s | 6x |
| Sync 10000 ingredients | ~1200s | ~180s | 6.7x |

## Tài Liệu Tham Khảo

- [PyTorch Installation Guide](https://pytorch.org/get-started/locally/)
- [NVIDIA CUDA Toolkit](https://developer.nvidia.com/cuda-downloads)
- [Sentence Transformers Documentation](https://www.sbert.net/)
- [NVIDIA Driver Download](https://www.nvidia.com/Download/index.aspx)
