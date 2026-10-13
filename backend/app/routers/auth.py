"""认证：注册 / 登录 / 当前用户 / 头像 / 微信扫码登录。"""
import secrets
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import wechat_service
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Tenant, User
from ..schemas import (
    AvatarUpdate,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
    WechatPollOut,
)
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

ALLOWED_AVATAR = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _slugify(name: str) -> str:
    import re

    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "kb"


def _ensure_unique(db: Session, username: str, email: str | None) -> None:
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已被注册")
    if email and db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邮箱已被注册")


def _resolve_tenant(db: Session, payload: UserCreate) -> tuple[int | None, str]:
    """决定新用户归属的知识库：邀请码优先 > 创建新库 > 无。返回 (tenant_id, role)。"""
    if payload.invite_code:
        tenant = db.scalar(select(Tenant).where(Tenant.invite_code == payload.invite_code))
        if not tenant:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "邀请码无效")
        return tenant.id, "member"
    if payload.tenant_name:
        if not settings.allow_new_tenant:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "当前未开放创建知识库")
        slug = _slugify(payload.tenant_name)[:48]
        while db.scalar(select(Tenant).where(Tenant.slug == slug)):
            slug = f"{_slugify(payload.tenant_name)[:44]}-{secrets.token_hex(2)}"
        tenant = Tenant(
            name=payload.tenant_name,
            slug=slug,
            invite_code=secrets.token_hex(4),
        )
        db.add(tenant)
        db.flush()
        return tenant.id, "owner"
    return None, "member"


@router.post("/register", response_model=Token)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    _ensure_unique(db, payload.username, payload.email)
    tenant_id, role = _resolve_tenant(db, payload)
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        avatar=payload.avatar or None,
        tenant_id=tenant_id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    """前端 JSON 登录。"""
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    return Token(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/token", response_model=Token)
def login_form(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    """供 Swagger 调试使用的表单登录。"""
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    return Token(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


# ---------------------------------------------------------------- 头像
@router.patch("/avatar", response_model=UserOut)
def update_avatar(
    payload: AvatarUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    """预设头像：传预设 key 或 data URL 均存库。"""
    user.avatar = payload.avatar
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/avatar", response_model=UserOut)
def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    """上传自定义头像（本地文件，≤ max_avatar_mb）。"""
    if file.content_type not in ALLOWED_AVATAR:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持 jpg/png/webp/gif 图片")
    data = file.file.read(settings.max_avatar_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_avatar_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"头像超过 {settings.max_avatar_mb}MB",
        )
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = ".png"
    avatars = settings.upload_path / "avatars"
    avatars.mkdir(parents=True, exist_ok=True)
    name = f"avatars/{uuid.uuid4().hex}{ext}"
    (settings.upload_path / name).write_bytes(data)
    user.avatar = name
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


# ---------------------------------------------------------------- 微信扫码登录
@router.get("/wx/qrcode")
def wx_qrcode(db: Session = Depends(get_db)) -> dict:
    """创建一次扫码会话，返回二维码（data URL）与 state。"""
    real = settings.wechat_enabled
    row = wechat_service.create_login_state(db, "real" if real else "mock")
    if real:
        content = wechat_service.build_authorize_url(row.state)
    else:
        content = wechat_service.build_mock_scan_url(row.state)
    return {
        "state": row.state,
        "mode": "real" if real else "mock",
        "qr": wechat_service.make_qr_data_url(content),
        "expires_in": settings.wx_state_ttl_seconds,
    }


@router.get("/wx/poll", response_model=WechatPollOut)
def wx_poll(state: str = Query(...), db: Session = Depends(get_db)) -> WechatPollOut:
    """前端轮询：pending → confirmed（返回 token）→ consumed。"""
    row = wechat_service.get_login_state(db, state)
    if not row or wechat_service._is_expired(row):
        return WechatPollOut(status="expired")
    if row.status == "confirmed" and row.user_id:
        user = db.get(User, row.user_id)
        if not user:
            return WechatPollOut(status="expired")
        wechat_service.consume_login_state(db, row)
        return WechatPollOut(
            status="confirmed",
            token=create_access_token(user.id),
            user=UserOut.model_validate(user),
        )
    return WechatPollOut(status=row.status)


def _finish_login(db: Session, state: str, user: User) -> None:
    wechat_service.confirm_login_state(db, state, user.id)


_MOCK_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>模拟微信扫码 · SurrealKB</title>
<style>
 body{{margin:0;min-height:100vh;display:grid;place-items:center;font-family:system-ui,-apple-system,"Microsoft YaHei";
 background:radial-gradient(circle at 20% 20%,#2a1055,#0a0618 60%,#05030d);color:#eae6ff}}
 .card{{width:360px;padding:32px;border-radius:22px;text-align:center;background:rgba(255,255,255,.06);
 border:1px solid rgba(155,89,255,.35);box-shadow:0 0 60px rgba(155,89,255,.25)}}
 h2{{margin:0 0 6px;font-size:18px}} p{{color:#a99fd0;font-size:13px;line-height:1.7}}
 a.btn{{display:inline-block;margin-top:18px;padding:12px 22px;border-radius:12px;text-decoration:none;color:#fff;
 font-weight:700;background:linear-gradient(135deg,#9b59ff,#00e5ff)}}
</style></head><body><div class="card">
 <h2>模拟微信扫码</h2>
 <p>这是本地开发用的<b>模拟授权页</b>。<br>点下面的按钮 = 手机点了「确认登录」。</p>
 <a class="btn" href="/api/auth/wx/mock/confirm?state={state}">✓ 确认登录</a>
</div></body></html>"""

_MOCK_DONE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>登录成功</title><style>
 body{{margin:0;min-height:100vh;display:grid;place-items:center;font-family:system-ui,"Microsoft YaHei";
 background:radial-gradient(circle at 80% 20%,#0b3b4a,#0a0618 60%,#05030d);color:#eae6ff}}
 .card{{padding:36px;border-radius:22px;text-align:center;background:rgba(255,255,255,.06);
 border:1px solid rgba(0,229,255,.35);box-shadow:0 0 60px rgba(0,229,255,.25)}}
 h2{{margin:0 0 8px}} p{{color:#9fd6e0}}
</style></head><body><div class="card">
 <h2>✓ 登录成功</h2><p>可以关掉此页面，回到应用继续操作。</p>
</div><script>setTimeout(()=>window.close(),1200)</script></body></html>"""


@router.get("/wx/mock", response_class=HTMLResponse)
def wx_mock_scan(state: str = Query(...), db: Session = Depends(get_db)) -> HTMLResponse:
    """Mock 模式：二维码打开的就是这个页面（模拟手机端）。"""
    if not wechat_service.get_login_state(db, state):
        return HTMLResponse("<h3>二维码已失效，请刷新页面重试</h3>", status_code=400)
    return HTMLResponse(_MOCK_PAGE.format(state=state))


@router.get("/wx/mock/confirm", response_class=HTMLResponse)
def wx_mock_confirm(state: str = Query(...), db: Session = Depends(get_db)) -> HTMLResponse:
    row = wechat_service.get_login_state(db, state)
    if not row or row.mode != "mock":
        return HTMLResponse("<h3>二维码已失效</h3>", status_code=400)
    user = wechat_service.create_mock_user(db)
    _finish_login(db, state, user)
    return HTMLResponse(_MOCK_DONE)


@router.get("/wx/callback")
def wx_callback(code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)):
    """真实模式：微信授权回调。"""
    row = wechat_service.get_login_state(db, state)
    if not row:
        return HTMLResponse("<h3>登录会话不存在或已过期</h3>", status_code=400)
    try:
        tok = wechat_service.exchange_code_for_openid(code)
        if "openid" not in tok:
            return HTMLResponse(f"<h3>微信授权失败：{tok}</h3>", status_code=400)
        openid = tok["openid"]
        info = wechat_service.fetch_wx_userinfo(tok.get("access_token", ""), openid)
        nickname = info.get("nickname")
        avatar_bytes = None
        if info.get("headimgurl"):
            avatar_bytes = wechat_service.download_image(info["headimgurl"])
        user = wechat_service.login_or_create_user(db, openid, nickname, avatar_bytes)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(f"<h3>微信登录异常：{exc}</h3>", status_code=500)
    _finish_login(db, state, user)
    return HTMLResponse(_MOCK_DONE)


@router.get("/wx/virtual")
def wx_virtual(nickname: str | None = Query(None), db: Session = Depends(get_db)) -> dict:
    """虚拟扫码：开发者/演示一键生成微信用户（不需要扫码）。"""
    user = wechat_service.create_mock_user(db, nickname)
    suffix = secrets.token_hex(3)
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "virtual": True,
        "nonce": suffix,
    }
