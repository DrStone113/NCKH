"""
api.py — FastAPI server cho RAGBot
Endpoints:
    POST /chat          — Hỏi đáp thông thường
    POST /chat/stream   — Stream câu trả lời
    GET  /health        — Kiểm tra trạng thái
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import uvicorn

from rag import RAGBot
from config import API_HOST, API_PORT

# Global bot instance
bot: RAGBot = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot
    bot = RAGBot()
    yield


app = FastAPI(
    title="RAGBot Medical API",
    description="Medical chatbot powered by LangChain + Ollama + ChromaDB",
    version="1.0.0",
    lifespan=lifespan
)


class ChatRequest(BaseModel):
    message: str
    stream: bool = False


class ChatResponse(BaseModel):
    question: str
    answer: str
    context_used: str = ""


@app.get("/health")
def health():
    return {
        "status": "ok",
        "records": bot._collection.count() if bot else 0
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not bot:
        raise HTTPException(503, "Bot chưa sẵn sàng")
    result = bot.ask(req.message)
    return ChatResponse(**result)


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    if not bot:
        raise HTTPException(503, "Bot chưa sẵn sàng")

    def generate():
        for chunk in bot.stream(req.message):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


if __name__ == "__main__":
    uvicorn.run("api:app", host=API_HOST, port=API_PORT, reload=False)
