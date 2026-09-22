from fastapi import APIRouter, WebSocket, Depends, Query, HTTPException
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from config import settings
from db.database import ScopedSession, get_db

from services.agent.chat_gateway import ChatGateway
from services.agent.orchestrator import AgentOrchestrator
from services.agent.memory_service import MemoryService
from db.session_store import DbSessionStore
from services.agent.tool_dispatcher import ToolDispatcher
from services.auth import AuthenticatedPrincipal, require_authenticated_principal, require_owner

router = APIRouter(tags=["chat"])


@router.get("/chat/sessions")
async def list_chat_sessions(
    user_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> list[dict[str, Any]]:
    """List chat sessions with their title (first user message)."""
    if user_id is not None:
        require_owner(principal, user_id)
    sql = text(
        """
        SELECT 
            s.id,
            s.user_id,
            s.created_at,
            s.last_active,
            (
                SELECT m.content 
                FROM chat_messages m 
                WHERE m.session_id = s.id AND m.role = 'user' 
                ORDER BY m.created_at ASC 
                LIMIT 1
            ) AS title
        FROM chat_sessions s
        WHERE s.user_id = :user_id
        ORDER BY s.last_active DESC
        LIMIT :limit
        """
    )
    result = await db.execute(sql, {"user_id": principal.user_id, "limit": limit})
    rows = result.fetchall()
    
    sessions = []
    for r in rows:
        title = r.title if r.title else "Cuộc trò chuyện mới"
        if len(title) > 60:
            title = title[:57] + "..."
        sessions.append({
            "id": str(r.id),
            "user_id": r.user_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_active": r.last_active.isoformat() if r.last_active else None,
            "title": title,
        })
    return sessions


@router.get("/chat/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> list[dict[str, Any]]:
    """Get all user & assistant messages for a session."""
    sql = text(
        """
        SELECT m.id, m.session_id, m.role, m.content, m.structured_data, m.public_trace, m.created_at
        FROM chat_messages m
        JOIN chat_sessions s ON s.id = m.session_id
        WHERE m.session_id = :sid
          AND s.user_id = :owner
          AND m.role IN ('user', 'assistant')
        ORDER BY m.created_at ASC, m.id ASC
        """
    )
    result = await db.execute(sql, {"sid": session_id, "owner": principal.user_id})
    rows = result.fetchall()
    
    messages = []
    for r in rows:
        messages.append({
            "id": str(r.id),
            "session_id": str(r.session_id),
            "role": r.role,
            "content": r.content,
            "structured": r.structured_data,
            "public_trace": r.public_trace,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return messages


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> dict[str, str]:
    """Delete a chat session and its history."""
    await db.execute(
        text(
            "DELETE FROM chat_messages WHERE session_id = :sid "
            "AND EXISTS (SELECT 1 FROM chat_sessions s WHERE s.id = :sid AND s.user_id = :owner)"
        ),
        {"sid": session_id, "owner": principal.user_id},
    )
    deleted = await db.execute(
        text("DELETE FROM chat_sessions WHERE id = :sid AND user_id = :owner"),
        {"sid": session_id, "owner": principal.user_id},
    )
    if deleted.rowcount == 0:
        await db.rollback()
        raise HTTPException(status_code=404, detail="CHAT_SESSION_NOT_FOUND")
    await db.commit()
    return {"status": "ok", "message": "Session deleted"}


@router.websocket("/chat/stream")
async def chat_stream(websocket: WebSocket):
    requested_protocols = {
        item.strip()
        for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if item.strip()
    }
    await websocket.accept(
        subprotocol="health-auth-v1"
        if "health-auth-v1" in requested_protocols
        else None
    )
    import uuid
    session_id = websocket.query_params.get("session_id")
    try:
        if session_id:
            uuid.UUID(session_id)
        else:
            session_id = str(uuid.uuid4())
    except ValueError:
        session_id = str(uuid.uuid4())

    # A WebSocket outlives many overlapping DB operations: one task per incoming
    # message plus background memory updates. Holding a single request-scoped
    # AsyncSession for all of them corrupts it on the first overlap (asyncpg:
    # "another operation is in progress") and it never recovers, which wiped
    # chat history mid-conversation. ScopedSession hands out a fresh session per
    # statement instead.
    app = websocket.app
    db_session = ScopedSession(
        metrics=getattr(app.state, "backend_cost_metrics", None),
        admission_controller=getattr(app.state, "chat_admission", None),
    )
    memory = MemoryService(db_session, app.state.rag_service)
    session_store = DbSessionStore(db_session)
    dispatcher = ToolDispatcher(
        app.state.registry,
        db_session=db_session,
        snapshot_cache=getattr(app.state, "private_snapshot_cache", None),
    )
    
    orchestrator = AgentOrchestrator(
        llm=app.state.llm,
        heavy_llm=getattr(app.state, "heavy_llm", None),
        tools=app.state.registry,
        memory=memory,
        session_store=session_store,
        dispatcher=dispatcher,
        gateway=None,
        scope_guard=getattr(app.state, "scope_guard", None),
        semantic_router=getattr(app.state, "server_semantic_router", None),
        metrics=getattr(app.state, "backend_cost_metrics", None),
        memory_semaphore=getattr(app.state, "background_memory_semaphore", None),
    )
    
    gateway = ChatGateway(
        websocket,
        orchestrator,
        session_id,
        db_session=db_session,
        admission=getattr(app.state, "chat_admission", None),
        metrics=getattr(app.state, "backend_cost_metrics", None),
        queue_size=settings.chat_queue_size,
        enforce_backpressure=settings.backend_cost_mode == "enforce",
        retry_after_ms=settings.chat_admission_retry_after_ms,
    )
    if not await gateway.authenticate():
        return
    orchestrator.gateway = gateway
    if getattr(orchestrator, "dispatcher", None) is not None:
        orchestrator.dispatcher.gateway = gateway
        gateway.tool_dispatcher = orchestrator.dispatcher
    await gateway.run()
