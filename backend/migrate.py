"""轻量迁移：为已有库补齐本次新增的列/表（幂等，可重复执行）。

用法： backend\\.venv\\Scripts\\python.exe migrate.py
说明： create_all 只会建缺失的「表」，不会给已存在的表加「列」，
      所以这里用 information_schema 探测后按需 ALTER。
"""
from sqlalchemy import inspect, text

from app import models  # noqa: F401  必须在 create_all 前导入，否则 Base.metadata 为空、一张表都不会建
from app.database import Base, engine

# 需要补齐的列： table -> [(列名, DDL片段)]
ADD_COLUMNS = {
    "users": [
        ("bio", "VARCHAR(200) NULL"),
        ("ai_name", "VARCHAR(24) NULL"),
        ("wechat_openid", "VARCHAR(64) NULL"),
        ("tenant_id", "INT NULL"),
        ("role", "VARCHAR(16) NOT NULL DEFAULT 'member'"),
    ],
    "chat_messages": [
        ("tenant_id", "INT NULL"),
    ],
    "documents": [
        ("content", "LONGTEXT NULL"),
        ("revision", "INT NOT NULL DEFAULT 1"),
        ("edited_at", "DATETIME NULL"),
        ("tags", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ],
}


def main() -> None:
    # 1) 建缺失的表（follows / wx_login_states 等）
    Base.metadata.create_all(bind=engine)
    print("[migrate] create_all done")

    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in ADD_COLUMNS.items():
            if not insp.has_table(table):
                print(f"[migrate] skip {table} (表不存在)")
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name in existing:
                    print(f"[migrate] {table}.{name} 已存在，跳过")
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                print(f"[migrate] + {table}.{name}")

        # users.avatar 需要容纳预设头像的内联 SVG data URL（最长 2048）
        if insp.has_table("users"):
            avatar_col = next(
                (c for c in insp.get_columns("users") if c["name"] == "avatar"), None
            )
            length = getattr(avatar_col["type"], "length", None) if avatar_col else None
            if length is not None and length < 2048:
                conn.execute(text("ALTER TABLE users MODIFY avatar VARCHAR(2048) NULL"))
                print(f"[migrate] ~ users.avatar {length} -> 2048")
            else:
                print(f"[migrate] users.avatar 已是 {length}，跳过")
        # 唯一索引（微信 openid / 关注对 / 租户 slug 等）——存在则忽略
        for stmt in (
            "CREATE UNIQUE INDEX uq_users_openid ON users (wechat_openid)",
            "CREATE UNIQUE INDEX uq_follow_pair ON follows (follower_id, followee_id)",
        ):
            try:
                conn.execute(text(stmt))
                print(f"[migrate] + index: {stmt.split(' ON ')[0]}")
            except Exception as exc:  # noqa: BLE001
                print(f"[migrate] index skip ({exc.__class__.__name__})")

        # 给存量用户兜底：没有 tenant 的，各建一个默认知识库并设为 owner
        if insp.has_table("users") and insp.has_table("tenants"):
            import secrets as _sec

            rows = conn.execute(
                text("SELECT id, username FROM users WHERE tenant_id IS NULL")
            ).fetchall()
            for uid, uname in rows:
                slug = f"u{uid}-{_sec.token_hex(3)}"
                conn.execute(
                    text(
                        "INSERT INTO tenants (name, slug, description, invite_code, created_at) "
                        "VALUES (:n, :s, NULL, :c, NOW())"
                    ),
                    {"n": f"{uname} 的知识库", "s": slug, "c": _sec.token_hex(4)},
                )
                tid = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                conn.execute(
                    text("UPDATE users SET tenant_id=:t, role='owner' WHERE id=:i"),
                    {"t": tid, "i": uid},
                )
                print(f"[migrate] user {uname} -> tenant #{tid}")
            if not rows:
                print("[migrate] 所有用户都有知识库，跳过")

    # 回填历史文档的全文（新增 documents.content 列后，旧数据为 NULL）
    _backfill_document_content()
    print("[migrate] done OK")


def _backfill_document_content() -> None:
    """为 content 为空的已就绪文档，从原始文件重新提取全文。"""
    from sqlalchemy.orm import Session as _Session

    from app import doc_service
    from app.config import settings
    from app.models import Document

    db = _Session(bind=engine)
    try:
        docs = (
            db.query(Document)
            .filter(Document.content.is_(None))
            .filter(Document.status == "ready")
            .all()
        )
        fixed = 0
        for doc in docs:
            path = settings.upload_path / doc.filename
            if not path.exists():
                print(f"[migrate] doc#{doc.id} 原文件缺失，跳过回填")
                continue
            try:
                text = doc_service.normalize(
                    doc_service.extract_text(path, doc.doc_type)
                )
                doc.content = text or ""
                fixed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[migrate] doc#{doc.id} 回填失败: {exc}")
        db.commit()
        print(f"[migrate] 回填文档全文 {fixed}/{len(docs)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
