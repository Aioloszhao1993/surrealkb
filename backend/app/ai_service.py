"""AI 问答服务（手写轻量 RAG，无外部向量库）——知识库版。

链路：
1. 文档上传后，doc_service 已把正文切成 Chunk（带 tenant_id）。
2. 这里负责把「还没有向量的 Chunk」批量调百炼 text-embedding-v3（1024 维），
   以 float32 原始字节存进 chunks.vector。
3. 提问时把问题向量化，只在「当前用户所属租户」的 Chunk 内算余弦相似度，取 Top-K。
4. 把命中的片段拼进 system prompt，连同多轮历史交给 qwen-plus 生成答案，并回带出处。
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
import threading

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import ChatMessage, Chunk, Document, User

_EMBED_BATCH = 10  # text-embedding-v3 单次最多 10 条

# 索引刷新互斥锁：串行化「启动补索引 / 上传后自动索引 / 手动重建」，
# 避免并发重复向量化。注意这是进程内锁，多 worker 部署需换 DB 层锁。
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


# ---------------------------------------------------------------- 关键词打分（BM25）
# 纯向量检索对「人名 / 编号 / 具体字段」这类关键词型查询不敏感，
# 这里加一套中文友好的 BM25（字符二元组 + 英文/数字词），与向量分数混合。
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    """极简分词：英文/数字词 + 中文连续字的二元组（单字查询回退单字）。"""
    low = text.lower()
    toks: list[str] = re.findall(r"[a-z0-9]+", low)
    cjk = _CJK.findall(low)
    if len(cjk) == 1:
        toks.append(cjk[0])
    else:
        toks.extend(cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1))
    return toks


def _bm25(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    q_terms = set(_tokens(query))
    n = len(docs)
    if not q_terms or n == 0:
        return [0.0] * n
    doc_tokens = [_tokens(d) for d in docs]
    avgdl = sum(len(t) for t in doc_tokens) / n or 1.0
    df: dict[str, int] = {}
    for t in doc_tokens:
        for w in set(t):
            df[w] = df.get(w, 0) + 1
    scores: list[float] = []
    for t in doc_tokens:
        tf: dict[str, int] = {}
        for w in t:
            tf[w] = tf.get(w, 0) + 1
        dl = len(t) or 1
        s = 0.0
        for w in q_terms:
            f = tf.get(w)
            if not f:
                continue
            idf = math.log(1 + (n - df.get(w, 0) + 0.5) / (df.get(w, 0) + 0.5))
            s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def _minmax(xs: list[float]) -> list[float]:
    if not xs:
        return []
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-9:
        return [0.5] * len(xs)
    return [(x - lo) / (hi - lo) for x in xs]


def _fingerprint(c: Chunk) -> str:
    return hashlib.sha1(c.content.encode("utf-8")).hexdigest()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """调用百炼把一批文本转成向量（每 10 条一批，按 index 排序保证顺序）。"""
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
def refresh_embeddings(db: Session, force: bool = False, tenant_id: int | None = None) -> dict:
    """为「尚无向量」或「内容变过」的分块补齐向量。可选只处理某个租户。"""
    if not ai_ready():
        return {"skipped": True, "reason": "no api key"}

    with _INDEX_LOCK:
        stmt = select(Chunk)
        if tenant_id is not None:
            stmt = stmt.where(Chunk.tenant_id == tenant_id)
        chunks = list(db.scalars(stmt))

        todo: list[Chunk] = []
        for c in chunks:
            if c.vector is None or force:
                todo.append(c)
            else:
                # 内容变过（重新解析过）才重建
                if len(c.vector) != c.dim * 4:
                    todo.append(c)

        if todo:
            # 向量化：分块已控制在 chunk_size 附近（约 800 字），
            # 远低于 text-embedding-v3 输入上限，无需再截断。
            vecs = embed_texts([c.content[:4000] for c in todo])
            for c, vec in zip(todo, vecs):
                c.vector = _pack(vec)
                c.dim = len(vec)
            db.commit()

        embedded = db.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.vector.isnot(None))
        ) or 0
        return {"indexed": len(todo), "total_chunks": len(chunks), "embedded": embedded}


def index_document_bg(document_id: int) -> None:
    """上传文档后，后台为该文档的分块补向量（不阻塞响应）。"""
    if not ai_ready():
        return

    def _run() -> None:
        db = SessionLocal()
        try:
            doc = db.get(Document, document_id)
            if doc:
                refresh_embeddings(db, tenant_id=doc.tenant_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[AI] auto index skipped: {exc}")
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------- 检索
def search_chunks(
    db: Session, query: str, tenant_id: int | None, top_k: int | None = None
) -> list[tuple[Chunk, Document, float]]:
    """向量检索：只在租户内的分块中找，返回 (分块, 文档, 相似度) 降序。"""
    top_k = top_k or settings.ai_top_k
    stmt = (
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.vector.isnot(None), Document.status == "ready")
    )
    if tenant_id is not None:
        stmt = stmt.where(Chunk.tenant_id == tenant_id)
    rows = db.execute(stmt).all()
    if not rows:
        return []

    qvec = embed_texts([query])[0]
    vec_scores: list[float] = []
    for chunk, _doc in rows:
        try:
            vec_scores.append(_cos(qvec, _unpack(chunk.vector)))
        except Exception:  # noqa: BLE001
            vec_scores.append(0.0)

    # 混合检索：向量（语义）+ BM25（关键词），各自 min-max 归一后加权融合。
    kw_scores = _bm25(query, [c.content for c, _d in rows])
    vn = _minmax(vec_scores)
    kn = _minmax(kw_scores)
    _VEC_W, _KW_W = 0.55, 0.45

    scored: list[tuple[Chunk, Document, float]] = []
    for idx, (chunk, doc) in enumerate(rows):
        final = _VEC_W * vn[idx] + _KW_W * kn[idx]
        scored.append((chunk, doc, final))
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------- 提示词
def _system_prompt(
    db: Session, question: str, user: User | None, tenant_id: int | None
) -> tuple[str, list[dict]]:
    hits = search_chunks(db, question, tenant_id)
    if hits:
        lines = []
        for i, (chunk, doc, score) in enumerate(hits, 1):
            snippet = chunk.content.strip().replace("\n", " ")
            # 完整注入命中片段（块本身约 chunk_size，不再截断，避免后半段内容缺失）
            lines.append(
                f"[{i}] 文档《{doc.title}》 第{chunk.seq + 1}段 相似度{score:.3f}\n    {snippet}"
            )
        kb = "\n".join(lines)
    else:
        kb = "（知识库中没有检索到相关内容）"

    who = f"当前登录用户：{user.username}" if user else "当前为游客（未登录）"
    system = (
        "你是「SurrealKB 知识库」的 AI 助手 Friday，回答专业、简洁、可靠。\n"
        "用户会基于自己知识库里的文档提问，你要严格依据下面的『检索片段』作答。\n"
        f"{who}\n\n"
        f"检索片段（来自本知识库，按相关度排序）：\n{kb}\n\n"
        "回答要求：\n"
        "1. 只依据上面的片段回答；片段不足以回答时，明确说「知识库中未找到相关信息」，不要编造。\n"
        "2. 引用信息时在句末标注来源编号，如 [1]、[2]。\n"
        "3. 用中文回答，条理清晰，控制在 300 字以内，不要输出 Markdown 表格。"
    )
    sources = [
        {
            "document_id": doc.id,
            "title": doc.title,
            "score": round(score, 4),
            "snippet": chunk.content.strip().replace("\n", " ")[:160],
            "seq": chunk.seq,
            "chunk_id": chunk.id,
            "anchor": _make_anchor(doc, chunk),
        }
        for chunk, doc, score in hits
    ]
    return system, sources


def _make_anchor(doc: Document, chunk: Chunk) -> str:
    """生成用于前端『精确回定位』的锚点：分块在正文里真实存在的连续片段。

    难点：分块正文经过 normalize()（把换行/重复空白压成空格），与 document.content
    里的原文（保留换行）不完全一致。所以不能直接 find，也不能按空白拆 token——
    因原文的换行可能落在 token 中间。做法：把分块开头的非空白字符逐个取出，
    用「字符间允许任意空白(\\s*)」的正则在原文里定位，返回原文中的真实文本。
    前端同样按「去空白后逐字匹配」定位，两侧一致。
    """
    try:
        content = doc.content or ""
        if not content or not chunk.content:
            return ""
        chars = [ch for ch in chunk.content if not ch.isspace()]
        if not chars:
            return ""
        for n in (40, 24, 16, 10, 6):
            if n > len(chars):
                continue
            pat = r"\s*".join(re.escape(ch) for ch in chars[:n])
            m = re.search(pat, content)
            if m:
                return m.group(0)
        return ""
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- 主入口
def _build_messages(
    db: Session, question: str, session_key: str, user: User | None, history_limit: int
) -> tuple[list[dict], list[dict], int | None]:
    """组装多轮消息（含检索片段），返回 (messages, sources, tenant_id)。"""
    history = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_key == session_key)
            .where(ChatMessage.user_id == (user.id if user else None))
            .order_by(ChatMessage.id.desc())
            .limit(history_limit)
        )
    )
    history.reverse()

    tenant_id = user.tenant_id if user else None
    system, sources = _system_prompt(db, question, user, tenant_id)
    messages = [{"role": "system", "content": system}]
    messages += [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": question})
    return messages, sources, tenant_id


def _persist_exchange(
    db: Session, question: str, answer: str, session_key: str, user: User | None, tenant_id: int | None
) -> None:
    db.add(
        ChatMessage(
            session_key=session_key,
            user_id=user.id if user else None,
            tenant_id=tenant_id,
            role="user",
            content=question,
        )
    )
    db.add(
        ChatMessage(
            session_key=session_key,
            user_id=user.id if user else None,
            tenant_id=tenant_id,
            role="assistant",
            content=answer,
        )
    )
    db.commit()


def chat(
    db: Session,
    question: str,
    session_key: str,
    user: User | None = None,
    history_limit: int = 6,
) -> dict:
    if not ai_ready():
        raise RuntimeError("AI 未配置：请在 backend/.env 里填 DASHSCOPE_API_KEY")

    messages, sources, tenant_id = _build_messages(db, question, session_key, user, history_limit)

    with _client() as c:
        resp = c.post(
            "/chat/completions",
            json={"model": settings.ai_chat_model, "messages": messages, "temperature": 0.3},
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()

    _persist_exchange(db, question, answer, session_key, user, tenant_id)
    return {"answer": answer, "sources": sources, "session_key": session_key}


def chat_stream(
    db: Session,
    question: str,
    session_key: str,
    user: User | None = None,
    history_limit: int = 6,
):
    """流式问答：先产出 sources，再逐步产出回答增量，最后入库。

    yield 的每个元素为 (event, data) 二元组：
      ("sources", {"sources": [...]}) → ("delta", "文字片段")* → ("done", {...})
    调用方（路由层）负责把它转成 SSE。
    """
    if not ai_ready():
        raise RuntimeError("AI 未配置：请在 backend/.env 里填 DASHSCOPE_API_KEY")

    messages, sources, tenant_id = _build_messages(db, question, session_key, user, history_limit)
    yield "sources", {"sources": sources}

    answer_parts: list[str] = []
    with _client() as c:
        with c.stream(
            "POST",
            "/chat/completions",
            json={
                "model": settings.ai_chat_model,
                "messages": messages,
                "temperature": 0.3,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", "ignore")
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    import json as _json

                    obj = _json.loads(payload)
                except Exception:  # noqa: BLE001
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    answer_parts.append(delta)
                    yield "delta", delta

    answer = "".join(answer_parts).strip()
    _persist_exchange(db, question, answer, session_key, user, tenant_id)
    yield "done", {"answer": answer, "sources": sources, "session_key": session_key}


def get_history(
    db: Session, session_key: str, limit: int = 50, user_id: int | None = None
) -> list[ChatMessage]:
    stmt = select(ChatMessage).where(ChatMessage.session_key == session_key)
    if user_id is not None:
        stmt = stmt.where(ChatMessage.user_id == user_id)
    return list(db.scalars(stmt.order_by(ChatMessage.id.asc()).limit(limit)))


def clear_history(db: Session, session_key: str, user_id: int | None = None) -> int:
    stmt = select(ChatMessage).where(ChatMessage.session_key == session_key)
    if user_id is not None:
        stmt = stmt.where(ChatMessage.user_id == user_id)
    rows = list(db.scalars(stmt))
    for r in rows:
        db.delete(r)
    db.commit()
    return len(rows)
