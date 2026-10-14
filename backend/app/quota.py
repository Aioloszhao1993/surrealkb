"""每日配额与反滥用。

设计取舍：
- **单用户配额**直接从数据库统计（chat_messages / documents 按当天 created_at 计数），
  重启进程不丢、多 worker 也准确 —— 这是真正兜住「某个用户刷爆额度」的关键。
- **全站总闸**用进程内计数器即可（单 worker 部署下够用），仅作最终保险。
- 进程内计数器每天按本地日期自动翻篇。
"""
from __future__ import annotations

from datetime import date, datetime, time
from threading import Lock

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import ChatMessage, Document

_lock = Lock()
_global: dict[str, int] = {}   # key -> 当天累计次数
_day: str = ""                 # 当前计数所属日期（本地）


def _roll() -> None:
    """跨天则清零（调用方需持有 _lock）。"""
    global _day
    today = date.today().isoformat()
    if today != _day:
        _day = today
        _global.clear()


def global_hit(name: str) -> tuple[bool, int]:
    """全站当日计数 +1，返回 (是否已超限, 当前值)。超限时不计数。"""
    with _lock:
        _roll()
        limit = {
            "ai": settings.ai_daily_quota_global,
            "upload": 0,
        }.get(name, 0)
        cur = _global.get(name, 0)
        if limit and cur >= limit:
            return True, cur
        cur += 1
        _global[name] = cur
        return False, cur


def global_peek(name: str) -> int:
    """查看全站当日累计（不自增）。"""
    with _lock:
        _roll()
        return _global.get(name, 0)


def _day_start() -> datetime:
    return datetime.combine(date.today(), time.min)


def user_ai_used_today(db: Session, user_id: int) -> int:
    """该用户今天已发起的 AI 提问数（以 chat_messages 中 role=user 计）。"""
    stmt = (
        select(func.count())
        .select_from(ChatMessage)
        .where(
            ChatMessage.user_id == user_id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= _day_start(),
        )
    )
    return db.scalar(stmt) or 0


def user_upload_used_today(db: Session, user_id: int) -> int:
    """该用户今天已上传的文档数。"""
    stmt = (
        select(func.count())
        .select_from(Document)
        .where(Document.owner_id == user_id, Document.created_at >= _day_start())
    )
    return db.scalar(stmt) or 0


def tenant_doc_count(db: Session, tenant_id: int) -> int:
    """该知识库现有文档总数。"""
    stmt = (
        select(func.count())
        .select_from(Document)
        .where(Document.tenant_id == tenant_id)
    )
    return db.scalar(stmt) or 0
