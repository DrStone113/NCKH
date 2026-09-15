import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from config import settings
from db.database import ScopedSession, apply_migrations, engine
from db.session_store import DbSessionStore
from services.agent.llm_client import LLMClient
from services.agent.memory_service import MemoryService
from services.agent.orchestrator import AgentOrchestrator
from services.agent.planner import PlannerAgent
from services.agent.rag_service import RAGService
from services.agent.tool_dispatcher import ToolDispatcher
from services.agent.tool_registry import ToolRegistry
from services.agent.tools import register_client_tools, register_server_tools
from services.agent.scope_guard import ScopeGuard, StrictJSONScopeClassifier
from services.agent.semantic_scope_classifier import SemanticPrototypeScopeClassifier
from services.security_logging import install_access_log_redaction
from services.backend_optimization import (
    AdaptiveAdmissionController,
    BackendCostMetrics,
    OwnerScopedSnapshotCache,
    PublicSingleFlightCache,
    ResilientHttpClient,
)
from services.catalog_http_cache import CatalogHttpCacheMiddleware

# Giảm log noise từ các thư viện bên ngoài
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
install_access_log_redaction()

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
    app.state.backend_cost_metrics = BackendCostMetrics()
    app.state.backend_cost_mode = settings.backend_cost_mode
    app.state.chat_admission = AdaptiveAdmissionController(
        minimum=settings.chat_admission_min_concurrency,
        initial=settings.chat_admission_initial_concurrency,
        maximum=settings.chat_admission_max_concurrency,
        timeout_seconds=settings.chat_admission_timeout_seconds,
        metrics=app.state.backend_cost_metrics,
        enforce=settings.backend_cost_mode == "enforce",
    )
    app.state.background_memory_semaphore = asyncio.Semaphore(
        settings.background_memory_concurrency
    )
    app.state.public_cache = PublicSingleFlightCache(
        max_entries=settings.public_cache_max_entries,
        ttl_seconds=settings.public_cache_ttl_seconds,
        metrics=app.state.backend_cost_metrics,
    )
    app.state.private_snapshot_cache = OwnerScopedSnapshotCache(
        ttl_seconds=settings.private_cache_ttl_seconds,
        metrics=app.state.backend_cost_metrics,
    )
    app.state.http_client = ResilientHttpClient(
        httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive_connections,
                keepalive_expiry=settings.http_keepalive_expiry_seconds,
            ),
            follow_redirects=True,
        ),
        failure_threshold=settings.http_circuit_failure_threshold,
        reset_seconds=settings.http_circuit_reset_seconds,
        metrics=app.state.backend_cost_metrics,
    )
    from modules.wger.router import configure_http_runtime

    configure_http_runtime(app.state.http_client, app.state.public_cache)
    app.state.db_session = ScopedSession(
        metrics=app.state.backend_cost_metrics,
        admission_controller=app.state.chat_admission,
    )
    app.state.rag_service = RAGService(metrics=app.state.backend_cost_metrics)
    app.state.registry = ToolRegistry()
    from services.agent.web_search import (
        DuckDuckGoProvider,
        PubMedProvider,
        WebKnowledgeService,
    )

    app.state.web_knowledge_service = WebKnowledgeService(
        PubMedProvider(app.state.http_client),
        DuckDuckGoProvider(app.state.http_client),
    )
    register_server_tools(
        app.state.registry,
        app.state.rag_service,
        app.state.db_session,
        web_service=app.state.web_knowledge_service,
    )
    register_client_tools(app.state.registry)
    app.state.llm = LLMClient(
        model=settings.llm_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        allow_model_fallback=settings.llm_cross_model_fallback,
        max_attempts_per_model=settings.llm_attempts_per_model,
    )
    app.state.heavy_llm = LLMClient(
        model=settings.heavy_llm_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        allow_model_fallback=settings.llm_cross_model_fallback,
        max_attempts_per_model=settings.llm_attempts_per_model,
    )
    app.state.scope_guard = None
    if settings.chat_scope_guard_mode == "strict":
        primary_scope_classifier = None
        if settings.scope_router_model:
            primary_scope_classifier = SemanticPrototypeScopeClassifier(
                settings.scope_router_model,
                device=settings.scope_router_device,
                temperature=settings.scope_router_temperature,
                full_confidence_similarity=(
                    settings.scope_router_full_confidence_similarity
                ),
            )
            try:
                await asyncio.wait_for(
                    primary_scope_classifier.prewarm(),
                    timeout=settings.scope_router_warmup_timeout_seconds,
                )
                logger.info(
                    "Scope intent model ready - model=%s",
                    settings.scope_router_model,
                )
            except Exception as exc:
                # The deterministic rules and isolated JSON judge remain
                # available. The loader thread may still finish after a
                # timeout, allowing later requests to recover automatically.
                logger.warning(
                    "Scope intent model warm-up failed (non-fatal): %s",
                    exc,
                )
        scope_classifier = None
        if settings.scope_classifier_model:
            app.state.scope_classifier_llm = LLMClient(
                model=settings.scope_classifier_model,
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
                request_timeout_s=settings.scope_classifier_timeout_seconds,
                allow_model_fallback=False,
                max_attempts_per_model=settings.llm_attempts_per_model,
            )
            scope_classifier = StrictJSONScopeClassifier(
                app.state.scope_classifier_llm,
                model_version=settings.scope_classifier_model,
                timeout_seconds=settings.scope_classifier_timeout_seconds,
            )
        app.state.scope_guard = ScopeGuard(
            scope_classifier,
            classifier_threshold=settings.scope_classifier_confidence,
            primary_classifier=primary_scope_classifier,
            primary_low_confidence=settings.scope_router_low_confidence,
            primary_high_confidence=settings.scope_router_high_confidence,
            primary_timeout_seconds=settings.scope_router_timeout_seconds,
        )
    app.state.memory = MemoryService(app.state.db_session, app.state.rag_service)
    app.state.session_store = DbSessionStore(app.state.db_session)
    app.state.dispatcher = ToolDispatcher(
        app.state.registry,
        db_session=app.state.db_session,
        snapshot_cache=app.state.private_snapshot_cache,
    )
    app.state.orchestrator = AgentOrchestrator(
        llm=app.state.llm,
        heavy_llm=app.state.heavy_llm,
        tools=app.state.registry,
        memory=app.state.memory,
        session_store=app.state.session_store,
        dispatcher=app.state.dispatcher,
        max_steps=settings.max_agent_steps,
        tool_timeout_ms=15000,
        scope_guard=app.state.scope_guard,
        metrics=app.state.backend_cost_metrics,
        memory_semaphore=app.state.background_memory_semaphore,
    )
    app.state.planner = PlannerAgent(app.state.registry, db_session=app.state.db_session)
    # N3.2 repository is an owner-scoped development/shadow store. It is not
    # wired into the authoritative suggest_dish production path.
    from modules.nutrition.adaptive.repository import AdaptiveRecipeRepository
    from modules.nutrition.adaptive.sql_store import AdaptiveShadowSqlStore
    app.state.adaptive_recipe_repository = AdaptiveRecipeRepository()
    if settings.adaptive_recommendation_shadow_enabled:
        from services.agent.tools.recipe_web import build_search_recipe_web_descriptor

        app.state.registry.register(
            build_search_recipe_web_descriptor(app.state.adaptive_recipe_repository)
        )
    # N3.2.1 feedback must cross a real transaction boundary before Flutter
    # receives a feedback-eligible card. This store is development/shadow only;
    # it has no canonical writer or production ranking control path.
    app.state.adaptive_feedback_store = AdaptiveShadowSqlStore()
    
    from services.proactive_service import ProactiveService
    app.state.proactive_service = ProactiveService(
        llm_client=(
            app.state.llm if settings.proactive_llm_personalization else None
        )
    )

    llm_ok = await app.state.llm.health_check()
    if not llm_ok:
        logger.warning(
            "LLM API is not available at %s - chatbot will stay inactive until LLM is ready.",
            settings.openai_base_url,
        )
    else:
        logger.info(
            "LLM endpoint reachable - completion quota remains unverified; model=%s",
            settings.llm_model,
        )

    # BGE-M3 is expensive in RAM/CPU. Production defaults to lazy loading and
    # the RAG path first checks that retrieval is actually required.
    async def _async_warmup():
        try:
            logger.info("Warming up embedding model in background...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, app.state.rag_service._get_model)
            logger.info("Embedding model ready")
        except Exception as e:
            logger.warning("Embedding model warm-up failed (non-fatal): %s", e)
    
    if settings.rag_warmup_mode == "startup":
        asyncio.create_task(_async_warmup())

    yield

    await app.state.http_client.aclose()
    await engine.dispose()
    logger.info("Shutting down AI Health Chatbot - cleanup complete")


app = FastAPI(title="AI Health Chatbot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CatalogHttpCacheMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.get("/health")
async def health_check():
    """Health check endpoint - Requirements: 8.4"""
    llm = getattr(app.state, "llm", None)
    llm_status = getattr(llm, "provider_status", "initializing")
    service_status = (
        "degraded"
        if llm_status in {"quota_exhausted", "authentication_failed", "unavailable"}
        else "ok"
    )
    return {
        "status": service_status,
        "model": settings.llm_model,
        "llm_status": llm_status,
    }


from modules.chat.router import router as chat_router
from modules.wger.router import router as wger_router
from modules.off.router import router as off_router
from modules.nutrition.router import router as nutrition_router
from modules.nutrition.adaptive_router import router as adaptive_nutrition_router
from modules.plans.router import router as plans_router
from modules.plans.v2_router import router as plan_v2_router
from modules.checkin.router import router as checkin_router
from modules.workouts.router import router as workouts_router
from modules.internal.router import router as internal_router
app.include_router(chat_router)
app.include_router(wger_router)
app.include_router(off_router)
app.include_router(nutrition_router)
app.include_router(adaptive_nutrition_router)
app.include_router(plans_router)
app.include_router(plan_v2_router)
app.include_router(checkin_router)
app.include_router(workouts_router)
app.include_router(internal_router)

