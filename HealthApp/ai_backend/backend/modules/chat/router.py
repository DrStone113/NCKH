from fastapi import APIRouter, WebSocket, Depends, Query
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from db.database import get_db

from services.agent.chat_gateway import ChatGateway
from services.agent.orchestrator import AgentOrchestrator
from services.agent.memory_service import MemoryService
from db.session_store import DbSessionStore
from services.agent.tool_dispatcher import ToolDispatcher

router = APIRouter(tags=["chat"])


@router.get("/chat/sessions")
async def list_chat_sessions(
    user_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List chat sessions with their title (first user message)."""
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
        WHERE (CAST(:user_id AS text) IS NULL OR s.user_id = :user_id OR s.user_id = 'anonymous')
        ORDER BY s.last_active DESC
        LIMIT :limit
        """
    )
    result = await db.execute(sql, {"user_id": user_id, "limit": limit})
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
) -> list[dict[str, Any]]:
    """Get all user & assistant messages for a session."""
    sql = text(
        """
        SELECT id, session_id, role, content, created_at
        FROM chat_messages
        WHERE session_id = :sid
          AND role IN ('user', 'assistant')
        ORDER BY created_at ASC, id ASC
        """
    )
    result = await db.execute(sql, {"sid": session_id})
    rows = result.fetchall()
    
    messages = []
    for r in rows:
        messages.append({
            "id": str(r.id),
            "session_id": str(r.session_id),
            "role": r.role,
            "content": r.content,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return messages


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a chat session and its history."""
    await db.execute(
        text("DELETE FROM chat_messages WHERE session_id = :sid"),
        {"sid": session_id},
    )
    await db.execute(
        text("DELETE FROM chat_sessions WHERE id = :sid"),
        {"sid": session_id},
    )
    await db.commit()
    return {"status": "ok", "message": "Session deleted"}


@router.websocket("/chat/stream")
async def chat_stream(websocket: WebSocket, db_session: AsyncSession = Depends(get_db)):
    await websocket.accept()
    import uuid
    session_id = websocket.query_params.get("session_id")
    try:
        if session_id:
            uuid.UUID(session_id)
        else:
            session_id = str(uuid.uuid4())
    except ValueError:
        session_id = str(uuid.uuid4())
    
    app = websocket.app
    memory = MemoryService(db_session, app.state.rag_service)
    session_store = DbSessionStore(db_session)
    dispatcher = ToolDispatcher(app.state.registry, db_session=db_session)
    
    orchestrator = AgentOrchestrator(
        llm=app.state.llm,
        heavy_llm=getattr(app.state, "heavy_llm", None),
        tools=app.state.registry,
        memory=memory,
        session_store=session_store,
        dispatcher=dispatcher,
        gateway=None
    )
    
    gateway = ChatGateway(websocket, orchestrator, session_id, db_session=db_session)
    if not await gateway.authenticate():
        return
    orchestrator.gateway = gateway
    if getattr(orchestrator, "dispatcher", None) is not None:
        orchestrator.dispatcher.gateway = gateway
        gateway.tool_dispatcher = orchestrator.dispatcher
    await gateway.run()