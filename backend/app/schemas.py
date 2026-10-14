"""Pydantic 请求/响应模型 -- 定义 API 的输入校验和输出形状。

知识库版：用户 / 知识库(租户) / 文档 / 分块 / AI 问答。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- 用户 ----------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = None
    avatar: str | None = Field(default=None, max_length=2048)
    # 注册时可选：创建自己的知识库（留空则只加入默认知识库）
    tenant_name: str | None = Field(default=None, max_length=100)
    invite_code: str | None = Field(default=None, max_length=16)


class UserLogin(BaseModel):
    username: str
    password: str


class AvatarUpdate(BaseModel):
    avatar: str | None = Field(default=None, max_length=2048)


class WechatPollOut(BaseModel):
    status: str  # pending / confirmed / consumed / expired
    token: str | None = None
    user: "UserOut | None" = None


class WxMpBindPayload(BaseModel):
    """小程序扫码回调：scene(票据) + wx.login 的 code。"""

    state: str = Field(min_length=8, max_length=64)
    code: str = Field(min_length=8, max_length=128)
    # 可选：小程序侧让用户填的昵称（可空，空则自动生成「微信用户」）
    nickname: str | None = Field(default=None, max_length=40)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str | None = None
    avatar: str | None = None
    bio: str | None = None
    role: str = "member"
    tenant_id: int | None = None
    created_at: datetime


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    description: str | None = None
    # 邀请码：仅 owner/admin 可见（普通成员为 None，避免任意成员拉人）
    invite_code: str | None = None
    # 当前用户是否有权管理（复制/重置邀请码、视为管理员）
    can_manage: bool = False
    created_at: datetime
    member_count: int = 0
    document_count: int = 0


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class TenantJoin(BaseModel):
    invite_code: str = Field(min_length=4, max_length=16)


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
    documents: int = 0
    is_self: bool = False
    is_following: bool = False


class FollowOut(BaseModel):
    following: bool
    followers: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- 文档 ----------
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    original_name: str | None = None
    doc_type: str = "txt"
    size: int = 0
    status: str = "pending"
    error: str | None = None
    chunk_count: int = 0
    char_count: int = 0
    tags: list[str] = []
    revision: int = 1
    edited_at: datetime | None = None
    tenant_id: int | None = None
    owner_id: int | None = None
    created_at: datetime
    owner: UserPublic | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def _split_tags(cls, v):
        """ORM 里 tags 是逗号分隔字符串，这里兼容解析为列表。"""
        if v is None:
            return []
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = None


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    seq: int
    content: str


class DocumentContent(BaseModel):
    """文档提取出的纯文本全文（供「原文」阅读视图）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    content: str
    char_count: int = 0
    revision: int = 1


class DocumentEdit(BaseModel):
    """在线编辑正文（可选同时改标题）。"""
    content: str = Field(max_length=2_000_000)
    title: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = None


class DocumentRevisionOut(BaseModel):
    """历史版本摘要（不含全文）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    revision_no: int
    title: str
    char_count: int = 0
    created_at: datetime


class DocumentConflict(BaseModel):
    """同名文档冲突：提示前端是否覆盖。"""
    conflict: bool = True
    document_id: int
    title: str
    message: str


# ---------- AI 问答 ----------
class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_key: str | None = Field(default=None, max_length=64)


class SourceOut(BaseModel):
    document_id: int
    title: str
    score: float
    snippet: str = ""
    # 出处定位：分块序号 / 分块 id / 原文锚点（用于前端精确回定位高亮）
    seq: int = 0
    chunk_id: int | None = None
    anchor: str = ""


class ChatOut(BaseModel):
    answer: str
    sources: list[SourceOut] = []
    session_key: str


WechatPollOut.model_rebuild()
