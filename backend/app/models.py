"""ORM 模型：用户 / 视频 / 点赞 / 收藏。"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 可移植的 BigInteger：MySQL 用 BIGINT，SQLite 回退为 INTEGER 以支持自增主键
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(200), nullable=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    videos: Mapped[list["Video"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)   # 存储文件名
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cover: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 可选封面
    size: Mapped[int] = mapped_column(BigInteger, default=0)               # 字节
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    owner: Mapped["User"] = relationship(back_populates="videos")
    likes: Mapped[list["Like"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "video_id", name="uq_like_user_video"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="likes")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "video_id", name="uq_fav_user_video"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="favorites")


Index("ix_videos_owner_created", Video.owner_id, Video.created_at.desc())


# ---------- AI：视频向量索引（手写轻量 RAG，不引入外部向量库）----------
class VideoEmbedding(Base):
    __tablename__ = "video_embeddings"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True, index=True
    )
    model: Mapped[str] = mapped_column(String(64), default="text-embedding-v3")
    dim: Mapped[int] = mapped_column(Integer, default=1024)
    # 源文本指纹：视频标题/简介变了就重新向量化
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    # float32 向量的原始字节（MySQL BLOB / SQLite BLOB），检索时在进程内算余弦相似度
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ---------- 关注关系（B 站式关注/粉丝）----------
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


# ---------- 微信扫码登录：临时 state 会话 ----------
class WxLoginState(Base):
    __tablename__ = "wx_login_states"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(8), default="mock")  # mock / real
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending/confirmed/consumed
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------- AI：会话消息（保留历史）----------
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_key: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
