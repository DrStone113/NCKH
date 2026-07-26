# 🔍 pgvector - Vector Database Guide

## Tổng quan

**pgvector** là PostgreSQL extension cho phép lưu trữ và tìm kiếm vector embeddings hiệu quả. Trong HealthApp, pgvector được sử dụng để:

- Lưu trữ embeddings của món ăn Việt Nam (1000+ món)
- Lưu trữ embeddings của bài tập thể dục (500+ bài)
- Tìm kiếm semantic (tìm theo nghĩa, không chỉ từ khóa)
- Hỗ trợ RAG (Retrieval-Augmented Generation) cho AI

---

## Cách hoạt động

### 1. Embedding Model

```
Embedding Model: paraphrase-multilingual-MiniLM-L12-v2
Vector Dimension: 384
Language Support: Vietnamese, English, và 50+ ngôn ngữ khác
```

### 2. Quy trình RAG

```
User Query: "Món nào giàu protein và ít calo?"
     ↓
[Embedding Model] → Vector 384 chiều
     ↓
[pgvector Search] → Cosine Similarity
     ↓
Top 5 món ăn phù hợp nhất
     ↓
[LLM] → Tạo câu trả lời tự nhiên
```

### 3. Database Schema

```sql
-- Bảng lưu nội dung
CREATE TABLE knowledge_chunks (
    id          UUID PRIMARY KEY,
    category    TEXT,  -- 'food', 'exercise', 'wger_exercise', 'wger_ingredient'
    title       TEXT,
    content     TEXT,
    metadata    JSONB
);

-- Bảng lưu vector embeddings
CREATE TABLE chunk_embeddings (
    chunk_id    UUID PRIMARY KEY,
    embedding   vector(384)  -- pgvector type
);

-- Index cho tìm kiếm nhanh
CREATE INDEX chunk_embeddings_embedding_idx
    ON chunk_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

---

## Sử dụng trong Docker

### Kiểm tra pgvector đã được cài đặt

```bash
# Vào PostgreSQL container
docker exec -it health_postgres psql -U health -d health_db

# Kiểm tra extension
\dx

# Kết quả mong đợi:
#   Name   | Version |   Schema   |         Description
# ---------+---------+------------+------------------------------
#  vector  | 0.7.0   | public     | vector data type and ivfflat access method
```

### Kiểm tra số lượng embeddings

```sql
-- Tổng số embeddings
SELECT COUNT(*) FROM chunk_embeddings;

-- Embeddings theo category
SELECT k.category, COUNT(*) 
FROM knowledge_chunks k
JOIN chunk_embeddings e ON k.id = e.chunk_id
GROUP BY k.category;
```

### Test tìm kiếm semantic

```sql
-- Tìm món ăn giàu protein (giả sử đã có embedding)
SELECT 
    k.title,
    k.content,
    1 - (e.embedding <=> '[0.1, 0.2, ...]'::vector) AS similarity
FROM knowledge_chunks k
JOIN chunk_embeddings e ON k.id = e.chunk_id
WHERE k.category = 'food'
ORDER BY e.embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;
```

---

## Performance

### IVFFlat Index

pgvector sử dụng **IVFFlat** (Inverted File with Flat compression) index:

- **lists = 100**: Chia vector space thành 100 clusters
- **Tốc độ**: ~10-100x nhanh hơn sequential scan
- **Trade-off**: Độ chính xác ~95-99% (approximate nearest neighbor)

### Benchmark

```
Dataset: 1000 món ăn Việt Nam
Vector dimension: 384
Index: IVFFlat (lists=100)

Sequential Scan: ~500ms
IVFFlat Index:   ~5-10ms
Speedup:         50-100x
```

### Tối ưu hóa

```sql
-- Tăng số lists cho dataset lớn hơn
DROP INDEX chunk_embeddings_embedding_idx;
CREATE INDEX chunk_embeddings_embedding_idx
    ON chunk_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 200);  -- Tăng từ 100 lên 200

-- Vacuum để tối ưu
VACUUM ANALYZE chunk_embeddings;
```

---

## Similarity Metrics

pgvector hỗ trợ 3 loại distance:

### 1. Cosine Distance (Đang dùng)

```sql
-- Operator: <=>
-- Range: 0 (giống nhất) đến 2 (khác nhất)
SELECT embedding <=> '[0.1, 0.2, ...]'::vector AS distance
FROM chunk_embeddings;

-- Chuyển sang similarity (0-1)
SELECT 1 - (embedding <=> '[0.1, 0.2, ...]'::vector) AS similarity
FROM chunk_embeddings;
```

### 2. L2 Distance (Euclidean)

```sql
-- Operator: <->
SELECT embedding <-> '[0.1, 0.2, ...]'::vector AS l2_distance
FROM chunk_embeddings;
```

### 3. Inner Product

```sql
-- Operator: <#>
SELECT embedding <#> '[0.1, 0.2, ...]'::vector AS inner_product
FROM chunk_embeddings;
```

**Lý do chọn Cosine**: Phù hợp với sentence embeddings vì normalize về cùng scale.

---

## Troubleshooting

### Lỗi: "extension vector does not exist"

```bash
# Vào container và cài extension
docker exec -it health_postgres psql -U health -d health_db -c "CREATE EXTENSION vector;"
```

### Lỗi: "index method ivfflat does not exist"

```bash
# Kiểm tra version pgvector
docker exec -it health_postgres psql -U health -d health_db -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

# Nếu version < 0.5.0, cần update image
docker compose down
docker compose pull postgres
docker compose up -d postgres
```

### Query chậm

```sql
-- Kiểm tra index có được sử dụng không
EXPLAIN ANALYZE
SELECT k.title
FROM knowledge_chunks k
JOIN chunk_embeddings e ON k.id = e.chunk_id
ORDER BY e.embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;

-- Nếu không dùng index, rebuild:
REINDEX INDEX chunk_embeddings_embedding_idx;
```

### Embeddings không chính xác

```python
# Kiểm tra embedding model trong backend
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
embedding = model.encode("Phở bò")
print(f"Dimension: {len(embedding)}")  # Phải là 384
print(f"Sample: {embedding[:5]}")
```

---

## Monitoring

### Xem kích thước database

```sql
-- Kích thước bảng
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Xem index usage

```sql
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE indexname = 'chunk_embeddings_embedding_idx';
```

---

## Best Practices

### 1. Batch Insert

```python
# ❌ Chậm - Insert từng row
for chunk in chunks:
    embedding = model.encode(chunk.content)
    db.execute("INSERT INTO chunk_embeddings VALUES (%s, %s)", 
               (chunk.id, embedding))

# ✅ Nhanh - Batch insert
embeddings = model.encode([c.content for c in chunks])
db.executemany("INSERT INTO chunk_embeddings VALUES (%s, %s)",
               [(c.id, e) for c, e in zip(chunks, embeddings)])
```

### 2. Normalize Embeddings

```python
import numpy as np

# Normalize về unit vector (cho cosine similarity)
embedding = model.encode(text)
embedding = embedding / np.linalg.norm(embedding)
```

### 3. Cache Embeddings

```python
# Không tạo embedding mỗi lần query
# Cache embedding của user query trong session
```

---

## Resources

- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [pgvector Documentation](https://github.com/pgvector/pgvector#readme)
- [Sentence Transformers](https://www.sbert.net/)
- [Vector Search Best Practices](https://www.pinecone.io/learn/vector-search/)

---

## Tóm tắt

✅ **pgvector** = PostgreSQL + Vector Search  
✅ **384 dimensions** = Embedding size  
✅ **IVFFlat index** = Fast approximate search  
✅ **Cosine similarity** = Measure semantic similarity  
✅ **RAG** = Retrieval-Augmented Generation  

pgvector giúp AI trả lời chính xác hơn bằng cách tìm kiếm thông tin liên quan từ database thay vì chỉ dựa vào kiến thức được train.
