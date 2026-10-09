"""AI 问答服务（方案二：手写轻量 RAG，不引入外部向量库）。

思路：
1. 每有一个新视频，就把「标题 + 作者 + 简介」拼成一段文本，调百炼 text-embedding-v3
   拿一个 1024 维向量，以 float32 原始字节存进 MySQL 的 video_embeddings 表。
2. 用户提问时，把问题也向量化，在进程内对所有视频向量算余弦相似度，取 Top-K。
3. 把 Top-K 的视频摘要拼进 system prompt，连同多轮历史一起交给 qwen-plus 生成答案。

这样即使以后视频涨到几千条，也不需要把全部内容塞进上下文，成本恒定。
"""
from __future__ import annotations

import hashlib
import math
import struct
import threading

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import ChatMessage, User, Video, VideoEmbedding

_EMBED_BATCH = 10  # text-embedding-v3 单次最多 10 条

# 索引刷新互斥锁：串行化「启动补索引 / 上传自动索引 / 手动重建」，
# 避免并发时对同一视频重复向量化，或撞 video_id 唯一键。
_INDEX_LOCK = threading.Lock()


# ---------------------------------------------------------------- HTTP 客户端
def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.dashscope_base,
        headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
        timeout=60.0,
    )


def ai_ready() -> bool:
    return settings.ai_enabled


# ---------------------------------------------------------------- 向量工具
def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(raw: bytes) -> list[float]:
    n = len(raw) // 4
    return list(struct.unpack(f"<{n}f", raw))


def _cos(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _fingerprint(video: Video) -> str:
    owner = video.owner.username if video.owner else "未知"
    text = f"{video.title}\n{owner}\n{video.description or ''}"
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _doc_text(video: Video) -> str:
    owner = video.owner.username if video.owner else "未知"
    desc = (video.description or "").strip() or "（无简介）"
    return f"视频标题：{video.title}\n作者：{owner}\n简介：{desc}"


def embed_texts(texts: list[str]) -> list[list[float]]:
    """调用百炼把一批文本转成向量。"""
    out: list[list[float]] = []
    with _client() as c:
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = texts[i : i + _EMBED_BATCH]
            resp = c.post(
                "/embeddings",
                json={"model": settings.ai_embed_model, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda d: d.get("index", 0))
            out.extend([d["embedding"] for d in data])
    return out


# ---------------------------------------------------------------- 索引维护
def refresh_embeddings(db: Session, force: bool = False) -> dict:
    """为新增/修改过的视频补齐向量。返回统计信息。"""
    if not ai_ready():
        return {"skipped": True, "reason": "no api key"}

    # 串行化：同一时刻只允许一个索引刷新在跑，后到者等前者结束后再扫一遍。
    with _INDEX_LOCK:
        videos = list(db.scalars(select(Video)))
        existing = {e.video_id: e for e in db.scalars(select(VideoEmbedding))}

        todo: list[Video] = []
        for v in videos:
            e = existing.get(v.id)
            if e is None or force or e.source_hash != _fingerprint(v):
                todo.append(v)

        if todo:
            vecs = embed_texts([_doc_text(v) for v in todo])
            for v, vec in zip(todo, vecs):
                e = existing.get(v.id)
                if e is None:
                    e = VideoEmbedding(video_id=v.id)
                    db.add(e)
                e.model = settings.ai_embed_model
                e.dim = len(vec)
                e.source_hash = _fingerprint(v)
                e.vector = _pack(vec)
            db.commit()

        total_embedded = db.scalar(select(func.count()).select_from(VideoEmbedding)) or 0
        return {"indexed": len(todo), "total_videos": len(videos), "embedded": total_embedded}


def index_new_video_bg() -> None:
    """上传新视频后，后台补齐向量索引（不阻塞上传响应）。"""
    if not ai_ready():
        return

    def _run() -> None:
        db = SessionLocal()
        try:
            refresh_embeddings(db)
        except Exception as exc:  # noqa: BLE001
            print(f"[AI] auto index skipped: {exc}")
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()


def search_videos(db: Session, query: str, top_k: int | None = None) -> list[tuple[Video, float]]:
    """向量检索：返回 (视频, 相似度) 列表，按相似度降序。"""
    top_k = top_k or settings.ai_top_k
    rows = db.execute(
        select(VideoEmbedding, Video).join(Video, Video.id == VideoEmbedding.video_id)
    ).all()
    if not rows:
        return []

    qvec = embed_texts([query])[0]
    scored = []
    for emb, video in rows:
        try:
            scored.append((video, _cos(qvec, _unpack(emb.vector))))
        except Exception:  # noqa: BLE001
            continue
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------- 提示词
def _system_prompt(db: Session, question: str, user: User | None) -> tuple[str, list[dict]]:
    """返回 (system_prompt, sources)。"""
    hits = search_videos(db, question)
    if hits:
        lines = []
        for i, (v, score) in enumerate(hits, 1):
            owner = v.owner.username if v.owner else "未知"
            desc = (v.description or "").strip() or "（无简介）"
            lines.append(
                f"[{i}] id={v.id} 标题《{v.title}》 作者{owner} 相似度{score:.3f}\n    简介：{desc[:200]}"
            )
        kb = "\n".join(lines)
    else:
        kb = "（站内目前没有相关视频）"

    who = f"当前登录用户：{user.username}" if user else "当前为游客"
    system = (
        "你是「SurrealVideo 梦境视频站」的 AI 助手 Friday，说话简洁友好、可以带一点赛博朋克气质。\n"
        "站点是一个极简版 B 站，用户可以上传视频、点赞、收藏、转发。\n"
        f"{who}\n\n"
        "下面是本站检索到的相关视频（按相关度排序），请优先依据它们回答：\n"
        f"{kb}\n\n"
        "要求：\n"
        "1. 如果用户问的是站内视频/找视频，就基于上面的清单回答，并自然地把视频标题带上；没有相关结果就直说没有。\n"
        "2. 其他问题（闲聊、通用知识）正常回答即可，不要硬扯站内视频。\n"
        "3. 回答用中文，控制在 200 字以内，不要输出 Markdown 表格。"
    )
    sources = [
        {"id": v.id, "title": v.title, "score": round(s, 4), "owner": v.owner.username if v.owner else "未知"}
        for v, s in hits
    ]
    return system, sources


# ---------------------------------------------------------------- 主入口
def chat(
    db: Session,
    question: str,
    session_key: str,
    user: User | None = None,
    history_limit: int = 6,
) -> dict:
    """一问一答，并落库。"""
    if not ai_ready():
        raise RuntimeError("AI 未配置：请在 backend/.env 里填 DASHSCOPE_API_KEY")

    history = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_key == session_key)
            .order_by(ChatMessage.id.desc())
            .limit(history_limit)
        )
    )
    history.reverse()

    system, sources = _system_prompt(db, question, user)
    messages = [{"role": "system", "content": system}]
    messages += [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": question})

    with _client() as c:
        resp = c.post(
            "/chat/completions",
            json={"model": settings.ai_chat_model, "messages": messages, "temperature": 0.6},
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()

    db.add(ChatMessage(session_key=session_key, user_id=user.id if user else None, role="user", content=question))
    db.add(ChatMessage(session_key=session_key, user_id=user.id if user else None, role="assistant", content=answer))
    db.commit()

    return {"answer": answer, "sources": sources, "session_key": session_key}


def get_history(db: Session, session_key: str, limit: int = 50) -> list[ChatMessage]:
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_key == session_key)
            .order_by(ChatMessage.id.asc())
            .limit(limit)
        )
    )
    return rows


def clear_history(db: Session, session_key: str) -> int:
    rows = list(db.scalars(select(ChatMessage).where(ChatMessage.session_key == session_key)))
    for r in rows:
        db.delete(r)
    db.commit()
    return len(rows)
