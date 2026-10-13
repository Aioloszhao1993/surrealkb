"""AI 问答路由：/api/ai/chat 等。

前端右下角悬浮的「AI 助手」会调这里的接口，检索范围 = 当前用户所属知识库。
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import ai_service
from ..database import get_db
from ..deps import get_current_user_optional
from ..models import Chunk, User
from ..schemas import ChatIn, ChatOut

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def ai_status(db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)) -> dict:
    """前端用它判断要不要展示 AI 入口。"""
    stmt = select(func.count()).select_from(Chunk).where(Chunk.vector.isnot(None))
    if user and user.tenant_id:
        stmt = stmt.where(Chunk.tenant_id == user.tenant_id)
    indexed = db.scalar(stmt) or 0
    return {
        "enabled": ai_service.ai_ready(),
        "model": "qwen-plus" if ai_service.ai_ready() else None,
        "indexed_chunks": indexed,
    }


@router.post("/chat", response_model=ChatOut)
def ai_chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> ChatOut:
    if not ai_service.ai_ready():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI 未配置：请在 backend/.env 填写 DASHSCOPE_API_KEY",
        )
    session_key = payload.session_key or uuid.uuid4().hex
    try:
        result = ai_service.chat(db, payload.question, session_key, user)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 服务调用失败：{exc}") from exc
    return ChatOut(**result)


@router.get("/history/{session_key}")
def ai_history(
    session_key: str,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict:
    rows = ai_service.get_history(db, session_key, limit)
    return {
        "items": [
            {"id": r.id, "role": r.role, "content": r.content, "created_at": r.created_at}
            for r in rows
        ]
    }


@router.delete("/history/{session_key}")
def ai_clear(session_key: str, db: Session = Depends(get_db)) -> dict:
    n = ai_service.clear_history(db, session_key)
    return {"deleted": n}


@router.post("/reindex")
def ai_reindex(
    force: bool = False,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> dict:
    """重建/补齐当前知识库的分块向量索引。"""
    if not ai_service.ai_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI 未配置")
    tenant_id = user.tenant_id if user else None
    try:
        return ai_service.refresh_embeddings(db, force=force, tenant_id=tenant_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"重建索引失败：{exc}") from exc
