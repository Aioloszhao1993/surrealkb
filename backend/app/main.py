"""SurrealKB 后端入口（知识库问答站）。

启动：uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import settings
from .database import Base, engine, SessionLocal
from .log import get_logger, setup_logging
from .ratelimit import rate_limit_middleware
from .routers import ai, auth, documents, tenants, users

setup_logging("DEBUG" if settings.debug else "INFO")
log = get_logger("app")

# 静态目录必须在挂载前存在（StaticFiles 在实例化时即校验路径）
settings.upload_path.mkdir(parents=True, exist_ok=True)
(settings.upload_path / "avatars").mkdir(parents=True, exist_ok=True)
(settings.upload_path / "docs").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 首次启动自动建表（生产建议改用 Alembic 迁移）
    Base.metadata.create_all(bind=engine)
    log.info("startup: app=%s debug=%s ai=%s", settings.app_name, settings.debug, settings.ai_enabled)
    # 启动时后台补齐分块向量索引（失败不影响服务启动）
    if settings.ai_enabled:
        def _warm():
            from .ai_service import refresh_embeddings
            db = SessionLocal()
            try:
                info = refresh_embeddings(db)
                log.info("embedding index ready: %s", info)
            except Exception as exc:  # noqa: BLE001
                log.warning("embedding warmup skipped: %s", exc)
            finally:
                db.close()
        threading.Thread(target=_warm, daemon=True).start()
    yield
    log.info("shutdown")


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)

# 简易限流：登录/注册/AI 问答等高频接口（进程内滑动窗口）。
# Starlette 中「后添加的中间件在最外层」。这里先注册限流、后添加 CORS，
# 使 CORS 处于最外层，限流返回 429 时也会带上 CORS 头（浏览器才能读到错误信息）。
app.middleware("http")(rate_limit_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    # 收敛为实际用到的方法与请求头（关闭原先的 "*" 全开放）
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-Key"],
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
def health() -> JSONResponse:
    """探活 + 数据库连通性。

    正常返回 200 {"status":"ok"}；DB 不通返回 503 {"status":"degraded"}，
    便于负载均衡 / 容器编排做健康检查。
    """
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        log.error("health: database unreachable: %s", exc)
    body = {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "version": app.version,
        "database": "up" if db_ok else "down",
        "ai": "on" if settings.ai_enabled else "off",
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)
