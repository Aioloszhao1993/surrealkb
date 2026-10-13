"""知识库（租户）：当前知识库信息 / 创建 / 加入 / 成员 / 邀请码。"""
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Document, Tenant, User
from ..schemas import TenantCreate, TenantJoin, TenantOut, UserOut, UserPublic

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "kb"


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)[:48]
    slug = base
    while db.scalar(select(Tenant).where(Tenant.slug == slug)):
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def _counts(db: Session, tenant_id: int) -> tuple[int, int]:
    members = db.scalar(
        select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
    ) or 0
    docs = db.scalar(
        select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
    ) or 0
    return members, docs


def _serialize(db: Session, tenant: Tenant) -> TenantOut:
    members, docs = _counts(db, tenant.id)
    out = TenantOut.model_validate(tenant)
    out.member_count = members
    out.document_count = docs
    return out


@router.get("/current", response_model=TenantOut)
def current_tenant(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TenantOut:
    if not user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "你还没有加入任何知识库")
    tenant = db.get(Tenant, user.tenant_id)
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    return _serialize(db, tenant)


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> TenantOut:
    """创建一个新知识库，并把当前用户设为 owner。"""
    if not settings.allow_new_tenant:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "当前未开放创建知识库")
    if user.tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你已经在一个知识库里，无法再创建")
    tenant = Tenant(
        name=payload.name,
        slug=_unique_slug(db, payload.name),
        description=payload.description,
        invite_code=secrets.token_hex(4),
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    user.tenant_id = tenant.id
    user.role = "owner"
    db.commit()
    db.refresh(tenant)
    return _serialize(db, tenant)


@router.post("/join", response_model=TenantOut)
def join_tenant(
    payload: TenantJoin, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> TenantOut:
    """凭邀请码加入一个已有知识库。"""
    if user.tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你已经在一个知识库里")
    tenant = db.scalar(select(Tenant).where(Tenant.invite_code == payload.invite_code))
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "邀请码无效")
    user.tenant_id = tenant.id
    user.role = "member"
    db.commit()
    db.refresh(tenant)
    return _serialize(db, tenant)


@router.get("/members", response_model=list[UserPublic])
def list_members(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[UserPublic]:
    if not user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "你还没有加入任何知识库")
    rows = db.scalars(
        select(User).where(User.tenant_id == user.tenant_id).order_by(User.id.asc())
    ).all()
    return [UserPublic.model_validate(r) for r in rows]


@router.get("/members/detail", response_model=list[UserOut])
def list_members_detail(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[UserOut]:
    if not user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "你还没有加入任何知识库")
    rows = db.scalars(
        select(User).where(User.tenant_id == user.tenant_id).order_by(User.id.asc())
    ).all()
    return [UserOut.model_validate(r) for r in rows]
