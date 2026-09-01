import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.database import ScopedSession, apply_migrations
from db.session_store import DbSessionStore
from services.agent.llm_client import LLMClient
from services.agent.memory_service import MemoryService
from services.agent.orchestrator import AgentOrchestrator
from services.agent.planner import PlannerAgent
from services.agent.rag_service import RAGService
from services.agent.tool_dispatcher import ToolDispatcher
from services.agent.tool_registry import ToolRegistry
from services.agent.tools import register_client_tools, register_server_tools

# Giảm log noise từ các thư viện bên ngoài
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(
        "Starting AI Health Chatbot - model=%s, openai_base_url=%s, db=%s",
        settings.llm_model,
        settings.openai_base_url,
        settings.database_url,
    )

    # Apply DB migrations cho schema mới (chatbot-redesign §10) — Requirements: 7.3, 7.5
    try:
        applied = await apply_migrations()
        if applied:
            logger.info("Applied DB migrations: %s", applied)
        else:
            logger.info("DB migrations: nothing to apply")
    except Exception as e:
        logger.warning("DB connection unavailable (%s) - running in standalone mode.", e)


    # Every DB consumer gets a facade that opens (and releases) its own session
    # per statement. A single shared AsyncSession cannot survive the overlapping
    # awaits this app produces — background memory updates, per-message chat
    # tasks, and parallel tool dispatch — and once it breaks it stays broken,
    # which silently emptied chat history. See db.database.ScopedSession.
    app.state.db_session = ScopedSession()
    app.state.rag_service = RAGService()
    app.state.registry = ToolRegistry()
    register_server_tools(app.state.registry, app.state.rag_service, app.state.db_session)
    register_client_tools(app.state.registry)
    app.state.llm = LLMClient(
        model=settings.llm_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key
    )
    app.state.heavy_llm = LLMClient(
        model=settings.heavy_llm_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key
    )
    app.state.memory = MemoryService(app.state.db_session, app.state.rag_service)
    app.state.session_store = DbSessionStore(app.state.db_session)
    app.state.dispatcher = ToolDispatcher(app.state.registry, db_session=app.state.db_session)
    app.state.orchestrator = AgentOrchestrator(
        llm=app.state.llm,
        heavy_llm=app.state.heavy_llm,
        tools=app.state.registry,
        memory=app.state.memory,
        session_store=app.state.session_store,
        dispatcher=app.state.dispatcher,
        max_steps=6,
        tool_timeout_ms=15000,
    )
    app.state.planner = PlannerAgent(app.state.registry, db_session=app.state.db_session)
    
    from services.proactive_service import ProactiveService
    app.state.proactive_service = ProactiveService(llm_client=app.state.llm)

    llm_ok = await app.state.llm.health_check()
    if not llm_ok:
        logger.warning(
            "LLM API is not available at %s - chatbot will stay inactive until LLM is ready.",
            settings.openai_base_url,
        )
    else:
        logger.info("LLM health check OK - model=%s", settings.llm_model)

    # Warm up embedding model in background so server opens port 8080 immediately
    import asyncio
    async def _async_warmup():
        try:
            logger.info("Warming up embedding model in background...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, app.state.rag_service._get_model)
            logger.info("Embedding model ready")
        except Exception as e:
            logger.warning("Embedding model warm-up failed (non-fatal): %s", e)
    
    asyncio.create_task(_async_warmup())

    yield

    # Shutdown — ScopedSession owns no long-lived connection, so there is
    # nothing to close here; the engine's pool is torn down by SQLAlchemy.
    logger.info("Shutting down AI Health Chatbot - cleanup complete")


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
    """Health check endpoint - Requirements: 8.4"""
    return {"status": "ok", "model": settings.llm_model}


from modules.chat.router import router as chat_router
from modules.wger.router import router as wger_router
from modules.off.router import router as off_router
from modules.nutrition.router import router as nutrition_router
from modules.plans.router import router as plans_router
from modules.checkin.router import router as checkin_router
from modules.workouts.router import router as workouts_router
app.include_router(chat_router)
app.include_router(wger_router)
app.include_router(off_router)
app.include_router(nutrition_router)
app.include_router(plans_router)
app.include_router(checkin_router)
app.include_router(workouts_router)

