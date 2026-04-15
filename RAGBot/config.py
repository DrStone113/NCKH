import os
from dotenv import load_dotenv

load_dotenv()

# Model Ollama chạy local (thay đổi tuỳ máy)
# Các model gợi ý: llama3, mistral, gemma2, phi3
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Embedding model (dùng chung với MedicalBot)
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# ChromaDB
CHROMA_DIR      = os.getenv("CHROMA_DIR", os.path.join(os.path.dirname(__file__), "chroma_db"))
CHROMA_COLLECTION = "medical_qa"

# SQLite từ MedicalBot (dùng lại embeddings đã build)
SQLITE_PATH = os.getenv(
    "SQLITE_PATH",
    os.path.join(os.path.dirname(__file__), "../MedicalBot/knowledge_base/health_kb.db")
)

# RAG settings
TOP_K          = int(os.getenv("TOP_K", "5"))       # Số kết quả tìm kiếm
MAX_TOKENS     = int(os.getenv("MAX_TOKENS", "512")) # Độ dài câu trả lời
TEMPERATURE    = float(os.getenv("TEMPERATURE", "0.3"))

# API Server
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
