"""AI 问答路由：/api/ai/chat 等。

前端右下角悬浮的「AI 助手」会调这里的接口，检索范围 = 当前用户所属知识库。
安全说明：
- chat / history / clear 均 require 登录（避免匿名刷百炼额度）。
- 会话标识由前端通过 X-Session-Key 请求头携带，服务端不再从 query/body 取，
  避免「知道别人的 session_key 就能读/删其聊天记录」。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import ai_service, quota
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_current_user_optional, get_session_key
from ..models import Chunk, User
from ..schemas import ChatIn, ChatOut

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def ai_status(
    db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)
) -> dict:
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


def _check_ai_quota(db: Session, user: User) -> None:
    """每日配额校验（防刷百炼额度）：先查单用户，再查全站总闸。

    以「用户当天已发起的提问数」为准（msg 落库后计数），超出直接 429。
    """
    per_user = settings.ai_daily_quota_per_user
    if per_user:
        used = quota.user_ai_used_today(db, user.id)
        if used >= per_user:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"今日 AI 提问已达上限（{per_user} 次），请明天再试",
            )
    if settings.ai_daily_quota_global:
        # 全站计数：仅作最终保险，读时不自增（由 chat 成功后统一自增）
        exceeded = quota.global_peek("ai") >= settings.ai_daily_quota_global
        if exceeded:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "今日全站 AI 额度已用完，请明天再试",
            )


@router.post("/chat")
def ai_chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    session_key: str = Depends(get_session_key),
    stream: bool = False,
):
    if not ai_service.ai_ready():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI 未配置：请在 backend/.env 填写 DASHSCOPE_API_KEY",
        )
    _check_ai_quota(db, user)
    if stream:
        # SSE 流式：先 __sources__ 事件，再逐 token，最后 __done__
        def gen():
            import json as _json

            try:
                for event, data in ai_service.chat_stream(db, payload.question, session_key, user):
                    yield f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"
                    if event == "done":
                        quota.global_hit("ai")
            except Exception as exc:  # noqa: BLE001
                yield f"event: error\ndata: {_json.dumps({'detail': str(exc)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        result = ai_service.chat(db, payload.question, session_key, user)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 服务调用失败：{exc}") from exc
    quota.global_hit("ai")
    return ChatOut(**result)


@router.get("/history")
def ai_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    session_key: str = Depends(get_session_key),
    limit: int = 50,
) -> dict:
    rows = ai_service.get_history(db, session_key, limit, user_id=user.id)
    return {
        "items": [
            {"id": r.id, "role": r.role, "content": r.content, "created_at": r.created_at}
            for r in rows
        ]
    }


@router.delete("/history")
def ai_clear(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    session_key: str = Depends(get_session_key),
) -> dict:
    n = ai_service.clear_history(db, session_key, user_id=user.id)
    return {"deleted": n}


@router.post("/reindex")
def ai_reindex(
    force: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """重建/补齐当前知识库的分块向量索引。**需登录**，否则匿名可反复触发烧 embedding 额度。"""
    if not ai_service.ai_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI 未配置")
    tenant_id = user.tenant_id
    try:
        return ai_service.refresh_embeddings(db, force=force, tenant_id=tenant_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"重建索引失败：{exc}") from exc
