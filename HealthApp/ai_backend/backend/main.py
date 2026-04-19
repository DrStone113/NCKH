import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from services.llm_service import llm_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(
        "Starting AI Health Chatbot — model=%s, ollama=%s, db=%s",
        settings.llm_model,
        settings.ollama_url,
        settings.database_url,
    )
    ollama_ok = await llm_service.health_check()
    if not ollama_ok:
        logger.warning(
            "Ollama không khả dụng tại %s — chatbot sẽ không hoạt động cho đến khi Ollama sẵn sàng.",
            settings.ollama_url,
        )
    else:
        logger.info("Ollama health check OK — model=%s", settings.llm_model)
    yield
    # Shutdown
    logger.info("Shutting down AI Health Chatbot — cleanup complete")


app = FastAPI(title="AI Health Chatbot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint — Requirements: 8.4"""
    return {"status": "ok", "model": settings.llm_model}


from routers.chat import router as chat_router
from routers.wger import router as wger_router
from routers.off import router as off_router
app.include_router(chat_router)
app.include_router(wger_router)
app.include_router(off_router)
