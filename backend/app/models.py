"""ORM 模型：知识库(租户) / 用户 / 文档 / 分块 / 关注 / 微信登录 / 会话消息。

从「视频站」改造为「企业知识库问答站」：
- Tenant  = 一个知识库（团队/企业），租户隔离的边界
- User    = 属于某个租户的成员
- Document= 上传的文档（pdf/docx/txt/md）
- Chunk   = 文档切分后的片段 + 向量（RAG 检索单元）
- ChatMessage = AI 问答历史

旧的 videos / likes / favorites / video_embeddings 表已不再映射（保留在库中未删除，可回滚）。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 可移植的 BigInteger：MySQL 用 BIGINT，SQLite 回退为 INTEGER 以支持自增主键
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


# ---------------------------------------------------------------- 知识库（租户）
class Tenant(Base):
    """一个知识库 = 一个租户（团队 / 企业）。所有文档、分块、问答都按它隔离。"""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)      # 知识库名称
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # 唯一标识
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # 邀请成员用的码
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    members: Mapped[list["User"]] = relationship(back_populates="tenant")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------- 用户
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(200), nullable=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    # 所属知识库 + 角色（owner 建库者 / admin 管理员 / member 普通成员）
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped["Tenant | None"] = relationship(back_populates="members")


# ---------------------------------------------------------------- 文档
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)          # 存储文件名
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(16), default="txt")            # pdf/docx/txt/md
    size: Mapped[int] = mapped_column(BigInteger, default=0)                    # 字节
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending/ready/failed
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # 标签（英文逗号分隔，用于分类/筛选），如 "合同,劳动,制度"
    tags: Mapped[str] = mapped_column(String(200), default="")
    # 提取出的全文（供「原文」阅读视图）；MySQL 用 LONGTEXT，其他方言回退 TEXT
    # deferred=True：列表/详情查询默认不加载，避免把大字段全拖回来
    content: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT, "mysql"), nullable=True, deferred=True
    )
    # 编辑版本号（首次上传=1，每次正文编辑 +1）
    revision: Mapped[int] = mapped_column(Integer, default=1)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="documents")
    # 上传者（用于前端展示「由谁上传」）
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_id])
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["DocumentRevision"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------- 分块（RAG 检索单元）
class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer, default=0)          # 第几块
    content: Mapped[str] = mapped_column(Text, nullable=False)    # 分块文本
    # float32 向量原始字节（MySQL BLOB），检索时进程内算余弦
    vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dim: Mapped[int] = mapped_column(Integer, default=1024)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="chunks")


# ---------------------------------------------------------------- 文档历史版本（编辑前快照）
class DocumentRevision(Base):
    """正文被编辑时，保存编辑前的旧内容（可回滚）。"""

    __tablename__ = "document_revisions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    revision_no: Mapped[int] = mapped_column(Integer, default=1)   # 这是第几版
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT, "mysql"), nullable=True, deferred=True
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    document: Mapped["Document"] = relationship(back_populates="revisions")


# ---------------------------------------------------------------- 关注（保留）
class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "followee_id", name="uq_follow_pair"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    follower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    followee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------- 微信扫码登录
class WxLoginState(Base):
    __tablename__ = "wx_login_states"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(8), default="mock")  # mock / real
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------- AI 会话消息
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_key: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


Index("ix_documents_tenant_created", Document.tenant_id, Document.created_at.desc())
Index("ix_chunks_tenant_doc", Chunk.tenant_id, Chunk.document_id)
