"""视频序列化工具：把 ORM 对象转成带统计/状态的响应结构。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Favorite, Like, User, Video
from .schemas import UserPublic, VideoOut


def _counts(db: Session, video_id: int) -> tuple[int, int]:
    likes = db.scalar(select(func.count()).select_from(Like).where(Like.video_id == video_id)) or 0
    favs = db.scalar(
        select(func.count()).select_from(Favorite).where(Favorite.video_id == video_id)
    ) or 0
    return likes, favs


def serialize_video(db: Session, video: Video, current_user: User | None = None) -> VideoOut:
    likes, favs = _counts(db, video.id)
    liked = favorited = False
    if current_user:
        liked = (
            db.scalar(
                select(func.count()).select_from(Like).where(
                    Like.video_id == video.id, Like.user_id == current_user.id
                )
            )
            or 0
        ) > 0
        favorited = (
            db.scalar(
                select(func.count()).select_from(Favorite).where(
                    Favorite.video_id == video.id, Favorite.user_id == current_user.id
                )
            )
            or 0
        ) > 0
    return VideoOut(
        id=video.id,
        title=video.title,
        description=video.description,
        cover=video.cover,
        size=video.size,
        views=video.views,
        created_at=video.created_at,
        owner=UserPublic.model_validate(video.owner),
        likes=likes,
        favorites=favs,
        shares=video.views,  # 简化：转发/观看共用计数
        liked=liked,
        favorited=favorited,
        url=f"/media/{video.filename}",
    )
