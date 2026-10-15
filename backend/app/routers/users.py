"""用户：资料更新 / 资料页 / 关注。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_current_user_optional
from ..models import Document, Follow, User
from ..schemas import FollowOut, UserOut, UserProfile, UserPublic, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


def _count(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    return user


# 注意：静态路径 /me 必须在 /{user_id} 之前
@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    if payload.username is not None:
        exist = db.scalar(
            select(User).where(User.username == payload.username, User.id != user.id)
        )
        if exist:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已被占用")
        user.username = payload.username
    if payload.bio is not None:
        user.bio = payload.bio
    if payload.ai_name is not None:
        # 前后空白去掉；纯空白 / 空串视为非法（用空串"清空名字"没有意义，
        # 前端靠 ai_name is None 判断是否需要引导起名）
        ai_name = payload.ai_name.strip()
        if not ai_name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "AI 名字不能为空")
        user.ai_name = ai_name
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserProfile)
def get_profile(
    user_id: int,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_current_user_optional),
) -> UserProfile:
    user = _get_user_or_404(db, user_id)
    followers = _count(
        db, select(func.count()).select_from(Follow).where(Follow.followee_id == user_id)
    )
    following = _count(
        db, select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)
    )
    docs = _count(
        db, select(func.count()).select_from(Document).where(Document.owner_id == user_id)
    )
    is_following = False
    if me:
        is_following = bool(
            db.scalar(
                select(Follow).where(Follow.follower_id == me.id, Follow.followee_id == user_id)
            )
        )
    return UserProfile(
        user=UserPublic.model_validate(user),
        followers=followers,
        following=following,
        documents=docs,
        is_self=bool(me and me.id == user_id),
        is_following=is_following,
    )


@router.post("/{user_id}/follow", response_model=FollowOut)
def toggle_follow(
    user_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)
) -> FollowOut:
    if user_id == me.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能关注自己")
    _get_user_or_404(db, user_id)
    existing = db.scalar(
        select(Follow).where(Follow.follower_id == me.id, Follow.followee_id == user_id)
    )
    if existing:
        db.delete(existing)
        following = False
    else:
        db.add(Follow(follower_id=me.id, followee_id=user_id))
        following = True
    db.commit()
    followers = _count(
        db, select(func.count()).select_from(Follow).where(Follow.followee_id == user_id)
    )
    return FollowOut(following=following, followers=followers)
