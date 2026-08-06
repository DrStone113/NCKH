# 🐳 HealthApp Docker Deployment

Hướng dẫn deploy HealthApp bằng Docker - Đơn giản, nhanh chóng, và nhất quán trên mọi môi trường.

## 📋 Yêu cầu

- **Docker Desktop** (Windows/Mac) hoặc **Docker Engine** (Linux)
- **Docker Compose** v2.0+
- **GPU** (tùy chọn, cho Ollama): NVIDIA GPU với CUDA support
- **RAM**: Tối thiểu 8GB, khuyến nghị 16GB+
- **Disk**: Tối thiểu 20GB trống

## 🚀 Khởi động nhanh

### Windows:

```bash
# Chạy script tự động
docker-start.bat
```

### Linux/Mac:

```bash
# 1. Khởi động lần đầu (pull model + load data)
docker compose build
docker compose up -d postgres
sleep 10
docker compose --profile init up data_loader wger_sync
docker compose up -d ollama
docker exec health_ollama ollama pull llama3.2
docker compose up -d fastapi_backend

# 2. Khởi động bình thường (lần sau)
docker compose up -d

# 3. Xem logs
docker compose logs -f fastapi_backend

# 4. Dừng tất cả
docker compose down
```

## 📦 Các service

| Service | Port | Mô tả |
|---------|------|-------|
| **fastapi_backend** | 8080 | FastAPI backend - AI chatbot với RAG |
| **ollama** | 11434 | Ollama LLM server (Llama 3.2) |
| **postgres** | 5432 | PostgreSQL + **pgvector** (vector embeddings) |

### Chi tiết về pgvector

PostgreSQL được cài đặt với extension **pgvector** để hỗ trợ:
- **Vector embeddings** (384 dimensions) cho semantic search
- **IVFFlat index** cho tìm kiếm cosine similarity nhanh
- **RAG (Retrieval-Augmented Generation)** - AI tìm kiếm thông tin chính xác từ database
- Lưu trữ embeddings cho:
  - 1000+ món ăn Việt Nam
  - 500+ bài tập thể dục
  - Thông tin dinh dưỡng

**Cách hoạt động:**
1. User hỏi: "Món nào giàu protein?"
2. Backend tạo embedding từ câu hỏi (384 chiều)
3. pgvector tìm các món ăn có embedding tương tự (cosine similarity)
4. AI trả lời dựa trên kết quả tìm kiếm chính xác

## 🔧 Cấu hình

### 1. Environment Variables

Tạo file `.env` trong thư mục `ai_backend/`:

```env
# Ollama
OLLAMA_URL=http://ollama:11434
LLM_MODEL=llama3.2

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://health:secret@postgres:5432/health_db

# Embedding
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# RAG (Retrieval-Augmented Generation with pgvector)
MAX_HISTORY_TURNS=10
RAG_TOP_K=5  # Số lượng kết quả tìm kiếm từ vector database
RAG_SIMILARITY_THRESHOLD=0.5  # Ngưỡng cosine similarity (0-1)

# Cloudflare Tunnel (optional)
CLOUDFLARE_TUNNEL_TOKEN=your_token_here
```

### 2. GPU Support

Nếu có NVIDIA GPU, Docker sẽ tự động sử dụng. Kiểm tra:

```bash
# Kiểm tra GPU trong container
docker exec health_ollama nvidia-smi
```

Nếu không có GPU, Ollama sẽ chạy trên CPU (chậm hơn).

### 3. Thay đổi model

Sửa trong `docker-compose.yml`:

```yaml
environment:
  - LLM_MODEL=llama3.2  # Đổi thành model khác
```

Sau đó pull model mới:

```bash
docker exec health_ollama ollama pull <model_name>
```

## 📊 Quản lý

### Xem logs

```bash
# Tất cả services
docker compose logs -f

# Chỉ backend
docker compose logs -f fastapi_backend

# Chỉ ollama
docker compose logs -f ollama
```

### Restart service

```bash
# Restart backend
docker compose restart fastapi_backend

# Restart tất cả
docker compose restart
```

### Xem trạng thái

```bash
docker compose ps
```

### Vào container

```bash
# Vào backend container
docker exec -it health_backend bash

# Vào postgres container và kiểm tra pgvector
docker exec -it health_postgres psql -U health -d health_db

# Trong psql, kiểm tra pgvector extension:
# \dx                          -- Xem extensions
# SELECT * FROM pg_extension WHERE extname = 'vector';
# SELECT COUNT(*) FROM chunk_embeddings;  -- Xem số lượng embeddings
```

## 🔄 Update code

```bash
# 1. Dừng services
docker compose down

# 2. Rebuild image
docker compose build fastapi_backend

# 3. Khởi động lại
docker compose up -d
```

## 🗄️ Backup & Restore

### Backup database

```bash
# Backup (bao gồm cả vector embeddings)
docker exec health_postgres pg_dump -U health health_db > backup.sql

# Restore
cat backup.sql | docker exec -i health_postgres psql -U health -d health_db

# Kiểm tra pgvector sau khi restore
docker exec -it health_postgres psql -U health -d health_db -c "\dx vector"
docker exec -it health_postgres psql -U health -d health_db -c "SELECT COUNT(*) FROM chunk_embeddings;"
```

### Backup Ollama models

```bash
# Models được lưu trong volume: ollama_data
docker run --rm -v ollama_data:/data -v $(pwd):/backup alpine tar czf /backup/ollama_backup.tar.gz /data
```

## 🌐 Production Deployment

### Với Cloudflare Tunnel

```bash
# 1. Tạo tunnel tại: https://dash.cloudflare.com
# 2. Copy token
# 3. Set environment variable
export CLOUDFLARE_TUNNEL_TOKEN=your_token

# 4. Khởi động với profile production
docker compose --profile production up -d
```

### Với reverse proxy (Nginx/Traefik)

Thêm vào `docker-compose.yml`:

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - fastapi_backend
    networks:
      - ai_net
```

## 🐛 Troubleshooting

### Backend không khởi động

```bash
# Xem logs
docker compose logs fastapi_backend

# Kiểm tra health
curl http://localhost:8080/health
```

### Ollama không pull được model

```bash
# Kiểm tra kết nối internet
docker exec health_ollama ping -c 3 ollama.com

# Pull thủ công
docker exec health_ollama ollama pull llama3.2
```

### Database connection error

```bash
# Kiểm tra postgres đang chạy
docker compose ps postgres

# Kiểm tra logs
docker compose logs postgres

# Restart postgres
docker compose restart postgres
```

### Out of memory

```bash
# Tăng memory limit trong docker-compose.yml
services:
  fastapi_backend:
    deploy:
      resources:
        limits:
          memory: 4G
```

## 📈 Performance Tuning

### 1. Tăng workers

```yaml
services:
  fastapi_backend:
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 2. Tối ưu Ollama

```yaml
services:
  ollama:
    environment:
      - OLLAMA_NUM_PARALLEL=4  # Số request song song
      - OLLAMA_MAX_LOADED_MODELS=2  # Số model load cùng lúc
```

### 3. Tối ưu PostgreSQL

```yaml
services:
  postgres:
    command: postgres -c shared_buffers=256MB -c max_connections=200
```

## 🔒 Security

### 1. Đổi password database

```yaml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: your_strong_password_here
```

### 2. Không expose ports ra ngoài

```yaml
services:
  postgres:
    # Xóa dòng này để không expose
    # ports:
    #   - "5432:5432"
```

### 3. Sử dụng secrets

```yaml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

## 📚 Tài liệu thêm

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Ollama Docker](https://hub.docker.com/r/ollama/ollama)
- [pgvector](https://github.com/pgvector/pgvector)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/docker/)

## 🆘 Hỗ trợ

Nếu gặp vấn đề:

1. Xem logs: `docker compose logs -f`
2. Kiểm tra health: `curl http://localhost:8080/health`
3. Restart: `docker compose restart`
4. Reset: `docker compose down -v && docker compose up -d`
