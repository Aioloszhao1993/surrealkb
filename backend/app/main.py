"""SurrealKB 后端入口（知识库问答站）。

启动：uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine, SessionLocal
from .routers import ai, auth, documents, tenants, users

# 静态目录必须在挂载前存在（StaticFiles 在实例化时即校验路径）
settings.upload_path.mkdir(parents=True, exist_ok=True)
(settings.upload_path / "avatars").mkdir(parents=True, exist_ok=True)
(settings.upload_path / "docs").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 首次启动自动建表（生产建议改用 Alembic 迁移）
    Base.metadata.create_all(bind=engine)
    # 启动时后台补齐分块向量索引（失败不影响服务启动）
    if settings.ai_enabled:
        def _warm():
            from .ai_service import refresh_embeddings
            db = SessionLocal()
            try:
                info = refresh_embeddings(db)
                print(f"[AI] embedding index ready: {info}")
            except Exception as exc:  # noqa: BLE001
                print(f"[AI] embedding warmup skipped: {exc}")
            finally:
                db.close()
        threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # 暴露下载文件名给前端（跨域时默认读不到 Content-Disposition）
    expose_headers=["Content-Disposition"],
)

app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(ai.router)

# 静态资源：头像等（backend/uploads/avatars/x.png → /media/avatars/x.png）
app.mount("/media", StaticFiles(directory=str(settings.upload_path)), name="media")


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
