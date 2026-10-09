"""用户：资料页 / 关注 / 作品 / 点赞过的视频。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_current_user_optional
from ..models import Favorite, Follow, Like, User, Video
from ..schemas import (
    FollowOut,
    PageOut,
    UserOut,
    UserProfile,
    UserPublic,
    UserUpdate,
)
from ..services import serialize_video

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
    works = _count(db, select(func.count()).select_from(Video).where(Video.owner_id == user_id))
    likes_received = _count(
        db, select(func.count()).select_from(Like).join(Video, Like.video_id == Video.id)
        .where(Video.owner_id == user_id)
    )
    total_views = db.scalar(
        select(func.coalesce(func.sum(Video.views), 0)).where(Video.owner_id == user_id)
    ) or 0
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
        works=works,
        likes_received=likes_received,
        total_views=total_views,
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


@router.get("/{user_id}/videos", response_model=PageOut)
def user_videos(
    user_id: int,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_current_user_optional),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
) -> PageOut:
    _get_user_or_404(db, user_id)
    total = _count(
        db, select(func.count()).select_from(Video).where(Video.owner_id == user_id)
    )
    rows = db.scalars(
        select(Video)
        .where(Video.owner_id == user_id)
        .order_by(Video.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PageOut(
        items=[serialize_video(db, v, me) for v in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}/likes", response_model=PageOut)
def user_liked_videos(
    user_id: int,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_current_user_optional),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
) -> PageOut:
    _get_user_or_404(db, user_id)
    total = _count(db, select(func.count()).select_from(Like).where(Like.user_id == user_id))
    rows = db.scalars(
        select(Video)
        .join(Like, Like.video_id == Video.id)
        .where(Like.user_id == user_id)
        .order_by(Like.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PageOut(
        items=[serialize_video(db, v, me) for v in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}/favorites", response_model=PageOut)
def user_favorite_videos(
    user_id: int,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_current_user_optional),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
) -> PageOut:
    _get_user_or_404(db, user_id)
    total = _count(
        db, select(func.count()).select_from(Favorite).where(Favorite.user_id == user_id)
    )
    rows = db.scalars(
        select(Video)
        .join(Favorite, Favorite.video_id == Video.id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PageOut(
        items=[serialize_video(db, v, me) for v in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
