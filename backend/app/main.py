"""SurrealVideo 后端入口。

启动：uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine, SessionLocal
from .routers import ai, auth, users, videos

# 静态目录必须在挂载前存在（StaticFiles 在实例化时即校验路径）
settings.upload_path.mkdir(parents=True, exist_ok=True)
(settings.upload_path / "covers").mkdir(parents=True, exist_ok=True)
(settings.upload_path / "avatars").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 首次启动自动建表（生产建议改用 Alembic 迁移）
    Base.metadata.create_all(bind=engine)
    # 启动时在后台补齐视频向量索引（失败不影响服务启动）
    if settings.ai_enabled:
        def _warm():
            from .ai_service import refresh_embeddings
            # 线程里不能复用请求的db session，必须自己创建
            db = SessionLocal()
            try:
                info = refresh_embeddings(db)
                print(f"[AI] embedding index ready: {info}")
            except Exception as exc:  # noqa: BLE001
                print(f"[AI] embedding warmup skipped: {exc}")
            finally:
                # 保证一定归还连接，避免连接泄露
                db.close()
        # 开一个守护线程后台补齐视频向量，embedding 可能需要几分钟，不能阻塞服务启动，daemon=True 让线程随主进程退出而退出
        threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(videos.router)
app.include_router(ai.router)

# 媒体文件静态服务：把 backend/uploads 目录挂载成一个 URL 前缀：磁盘上的 backend/uploads/xxx.mp4 → 对外访问 http://localhost:8000/media/xxx.mp4
app.mount("/media", StaticFiles(directory=str(settings.upload_path)), name="media")


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
