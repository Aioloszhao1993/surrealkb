"""视频：上传 / 列表 / 详情 / 修改 / 删除 / 点赞 / 收藏 / 转发。"""
import shutil
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_current_user_optional
from ..models import Favorite, Like, User, Video
from ..schemas import ActionOut, PageOut, VideoOut, VideoUpdate
from ..services import serialize_video

router = APIRouter(prefix="/api/videos", tags=["videos"])

ALLOWED_VIDEO = {"video/mp4", "video/webm", "video/quicktime", "video/x-matroska", "video/ogg"}
ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp"}


def _safe_ext(filename: str, fallback: str) -> str:
    ext = Path(filename or "").suffix.lower()
    return ext if ext and len(ext) <= 8 else fallback


@router.post("", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
def upload_video(
    title: str = Form(..., max_length=200),
    description: str | None = Form(None),
    file: UploadFile = File(...),
    cover: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VideoOut:
    if file.content_type not in ALLOWED_VIDEO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持 mp4/webm/mov/mkv/ogg 视频")

    upload_dir = settings.upload_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    covers_dir = upload_dir / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.max_video_mb * 1024 * 1024
    stored_name = f"{uuid.uuid4().hex}{_safe_ext(file.filename, '.mp4')}"
    dest = upload_dir / stored_name

    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"视频超过 {settings.max_video_mb}MB 限制",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"写入失败: {exc}") from exc

    cover_name = None
    if cover and cover.content_type in ALLOWED_IMAGE:
        cover_name = f"covers/{uuid.uuid4().hex}{_safe_ext(cover.filename, '.jpg')}"
        with (upload_dir / cover_name).open("wb") as out:
            shutil.copyfileobj(cover.file, out)

    video = Video(
        title=title,
        description=description,
        filename=stored_name,
        original_name=file.filename,
        cover=cover_name,
        size=size,
        mime_type=file.content_type,
        owner_id=user.id,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    # 新视频入向量索引（后台线程，不阻塞上传响应）
    from .. import ai_service

    ai_service.index_new_video_bg()

    return serialize_video(db, video, user)


# 注意：静态路径必须注册在 /{video_id} 之前，否则 "favorites" 会被当作 video_id
@router.get("/favorites/me", response_model=PageOut)
def my_favorites(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
) -> PageOut:
    base = (
        select(Video)
        .join(Favorite, Favorite.video_id == Video.id)
        .where(Favorite.user_id == user.id)
    )
    total = (
        db.scalar(select(func.count()).select_from(Favorite).where(Favorite.user_id == user.id)) or 0
    )
    videos = db.scalars(
        base.order_by(Favorite.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return PageOut(
        items=[serialize_video(db, v, user) for v in videos],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=PageOut)
def list_videos(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    q: str | None = Query(None, description="搜索标题/描述"),
    owner_id: int | None = Query(None),
    sort: str = Query("new", pattern="^(new|hot)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
) -> PageOut:
    stmt = select(Video)
    count_stmt = select(func.count()).select_from(Video)
    if q:
        cond = or_(Video.title.like(f"%{q}%"), Video.description.like(f"%{q}%"))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if owner_id:
        stmt = stmt.where(Video.owner_id == owner_id)
        count_stmt = count_stmt.where(Video.owner_id == owner_id)

    total = db.scalar(count_stmt) or 0
    stmt = stmt.order_by(Video.views.desc() if sort == "hot" else Video.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    videos = db.scalars(stmt).all()
    return PageOut(
        items=[serialize_video(db, v, user) for v in videos],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{video_id}", response_model=VideoOut)
def get_video(
    video_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> VideoOut:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "视频不存在")
    video.views += 1
    db.commit()
    db.refresh(video)
    return serialize_video(db, video, user)


@router.patch("/{video_id}", response_model=VideoOut)
def update_video(
    video_id: int,
    payload: VideoUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VideoOut:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "视频不存在")
    if video.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能修改自己的视频")
    if payload.title is not None:
        video.title = payload.title
    if payload.description is not None:
        video.description = payload.description
    db.commit()
    db.refresh(video)
    return serialize_video(db, video, user)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "视频不存在")
    if video.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能删除自己的视频")
    path = settings.upload_path / video.filename
    db.delete(video)
    db.commit()
    path.unlink(missing_ok=True)


@router.post("/{video_id}/like", response_model=ActionOut)
def toggle_like(
    video_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ActionOut:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "视频不存在")
    existing = db.scalar(select(Like).where(Like.video_id == video_id, Like.user_id == user.id))
    if existing:
        db.delete(existing)
        active = False
    else:
        db.add(Like(video_id=video_id, user_id=user.id))
        active = True
    db.commit()
    count = db.scalar(select(func.count()).select_from(Like).where(Like.video_id == video_id)) or 0
    return ActionOut(active=active, count=count)


@router.post("/{video_id}/favorite", response_model=ActionOut)
def toggle_favorite(
    video_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ActionOut:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "视频不存在")
    existing = db.scalar(
        select(Favorite).where(Favorite.video_id == video_id, Favorite.user_id == user.id)
    )
    if existing:
        db.delete(existing)
        active = False
    else:
        db.add(Favorite(video_id=video_id, user_id=user.id))
        active = True
    db.commit()
    count = (
        db.scalar(select(func.count()).select_from(Favorite).where(Favorite.video_id == video_id))
        or 0
    )
    return ActionOut(active=active, count=count)


@router.post("/{video_id}/share", response_model=ActionOut)
def share_video(video_id: int, db: Session = Depends(get_db)) -> ActionOut:
    """简化转发：计入观看/转发数。返回最新计数。"""
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "视频不存在")
    video.views += 1
    db.commit()
    return ActionOut(active=True, count=video.views)
