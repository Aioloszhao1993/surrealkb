"""Pydantic 请求/响应模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- 用户 ----------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = None
    # 注册时可直接选一个预设头像（data URL，最长 2048）
    avatar: str | None = Field(default=None, max_length=2048)


class UserLogin(BaseModel):
    username: str
    password: str


class AvatarUpdate(BaseModel):
    avatar: str | None = Field(default=None, max_length=2048)


class WechatPollOut(BaseModel):
    status: str  # pending / confirmed / consumed / expired
    token: str | None = None
    user: "UserOut | None" = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str | None = None
    avatar: str | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    bio: str | None = Field(default=None, max_length=200)
    username: str | None = Field(default=None, min_length=3, max_length=50)


class UserPublic(BaseModel):
    """对外展示的用户信息（含头像，不含邮箱）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    avatar: str | None = None
    bio: str | None = None


class UserProfile(BaseModel):
    user: UserPublic
    followers: int = 0
    following: int = 0
    works: int = 0
    likes_received: int = 0
    total_views: int = 0
    is_self: bool = False
    is_following: bool = False


class FollowOut(BaseModel):
    following: bool
    followers: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- 视频 ----------
class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str | None = None
    cover: str | None = None
    size: int = 0
    views: int = 0
    created_at: datetime
    owner: UserPublic
    likes: int = 0
    favorites: int = 0
    shares: int = 0
    liked: bool = False
    favorited: bool = False
    url: str = ""


class VideoUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None


class PageOut(BaseModel):
    items: list[VideoOut]
    total: int
    page: int
    page_size: int


class ActionOut(BaseModel):
    active: bool
    count: int


# ---------- AI 问答 ----------
class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_key: str | None = Field(default=None, max_length=64)


class SourceOut(BaseModel):
    id: int
    title: str
    score: float
    owner: str = ""


class ChatOut(BaseModel):
    answer: str
    sources: list[SourceOut] = []
    session_key: str


WechatPollOut.model_rebuild()
