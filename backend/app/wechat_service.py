"""微信扫码登录服务（含本地 Mock 模式）。

真实模式：微信开放平台「网站应用」扫码登录（snsapi_login）。
Mock 模式：未配置 AppID 时启用，二维码指向本机的一个模拟授权页，
         点击即完成"扫码"，用于本地无公众号时演示完整登录链路。

两种模式共用同一套 state 轮询机制：
    前端 create → 轮询 poll → 得到 token。
"""
from __future__ import annotations

import base64
import io
import random
import secrets
import string
from datetime import datetime, timedelta

import httpx
import qrcode
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import User, WxLoginState

WX_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
WX_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
WX_USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"

# Mock 头像用的超现实霓虹渐变
_GRADIENTS = [
    ((155, 89, 255), (0, 229, 255)),
    ((255, 92, 168), (255, 205, 96)),
    ((0, 229, 255), (52, 255, 171)),
    ((255, 111, 145), (155, 89, 255)),
    ((96, 165, 250), (192, 132, 252)),
]


# ---------------------------------------------------------------- state 管理
def new_state() -> str:
    return secrets.token_urlsafe(24)


def create_login_state(db: Session, mode: str) -> WxLoginState:
    row = WxLoginState(state=new_state(), mode=mode, status="pending")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_login_state(db: Session, state: str) -> WxLoginState | None:
    return db.scalar(select(WxLoginState).where(WxLoginState.state == state))


def _is_expired(row: WxLoginState) -> bool:
    if not row.created_at:
        return False
    return datetime.now() - row.created_at > timedelta(seconds=settings.wx_state_ttl_seconds)


def confirm_login_state(db: Session, state: str, user_id: int) -> None:
    row = get_login_state(db, state)
    if not row:
        return
    row.status = "confirmed"
    row.user_id = user_id
    row.confirmed_at = datetime.now()
    db.commit()


def consume_login_state(db: Session, row: WxLoginState) -> None:
    row.status = "consumed"
    db.commit()


# ---------------------------------------------------------------- 二维码
def make_qr_data_url(content: str) -> str:
    img = qrcode.make(content)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def build_authorize_url(state: str) -> str:
    redirect = httpx.URL(settings.wechat_redirect_uri)
    return (
        f"{WX_AUTHORIZE_URL}?appid={settings.wechat_app_id}"
        f"&redirect_uri={redirect}"
        f"&response_type=code&scope=snsapi_login&state={state}"
        f"#wechat_redirect"
    )


def build_mock_scan_url(state: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/api/auth/wx/mock?state={state}"


# ---------------------------------------------------------------- 头像生成
# 头像字体候选：优先中文字体，保证「微信用户」首字母（中/英）都能正常渲染
_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/msyhbd.ttc", 0),  # 微软雅黑 Bold
    ("C:/Windows/Fonts/msyh.ttc", 0),    # 微软雅黑
    ("C:/Windows/Fonts/simhei.ttf", 0),  # 黑体
    ("C:/Windows/Fonts/Deng.ttf", 0),    # 等线
    ("C:/Windows/Fonts/simsun.ttc", 0),  # 宋体
    ("arial.ttf", 0),                     # 拉丁兜底
]


def _load_font(size: int):
    from PIL import ImageFont

    for path, idx in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def generate_avatar_png(letter: str, seed: str | None = None) -> bytes:
    """本地生成一张 128x128 的渐变头像（Mock 模式用，无需外网）。"""
    from PIL import Image, ImageDraw

    size = 128
    c1, c2 = _GRADIENTS[random.Random(seed or letter).randrange(len(_GRADIENTS))]
    img = Image.new("RGB", (size, size), c1)
    draw = ImageDraw.Draw(img)
    for y in range(size):  # 竖向渐变
        t = y / (size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=(
                int(c1[0] + (c2[0] - c1[0]) * t),
                int(c1[1] + (c2[1] - c1[1]) * t),
                int(c1[2] + (c2[2] - c1[2]) * t),
            ),
        )
    text = (letter or "?").upper()
    font = _load_font(64)
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text, fill="#ffffff", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _save_avatar_bytes(db: Session, user: User, data: bytes) -> None:  # noqa: ARG001
    from .config import settings as _s

    avatars = _s.upload_path / "avatars"
    avatars.mkdir(parents=True, exist_ok=True)
    name = f"avatars/wx_{secrets.token_hex(8)}.png"
    (_s.upload_path / name).write_bytes(data)
    user.avatar = name


# ---------------------------------------------------------------- 用户 upsert
def _random_suffix(n: int = 4) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def login_or_create_user(
    db: Session, openid: str, nickname: str | None = None, avatar_bytes: bytes | None = None
) -> User:
    user = db.scalar(select(User).where(User.wechat_openid == openid))
    if user:
        return user

    name = (nickname or "微信用户").strip()[:40] or "微信用户"
    candidate = name
    while db.scalar(select(User).where(User.username == candidate)):
        candidate = f"{name}_{_random_suffix()}"

    # 每个微信新用户自动开一个个人知识库（owner）
    from .models import Tenant

    tenant = Tenant(
        name=f"{candidate} 的知识库",
        slug=f"wx-{secrets.token_hex(4)}",
        invite_code=secrets.token_hex(4),
    )
    db.add(tenant)
    db.flush()

    user = User(
        username=candidate,
        wechat_openid=openid,
        hashed_password="!wx-no-password!",
        tenant_id=tenant.id,
        role="owner",
    )
    if avatar_bytes:
        _save_avatar_bytes(db, user, avatar_bytes)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_mock_user(db: Session, nickname: str | None = None) -> User:
    """Mock 扫码：生成一个随机的微信风格用户（名字与头像各不相同）。"""
    suffix = _random_suffix(4)
    name = (nickname or f"微信用户_{suffix}")[:40]
    openid = f"mock_openid_{secrets.token_hex(8)}"
    avatar = generate_avatar_png(name[0], seed=openid)
    return login_or_create_user(db, openid, nickname=name, avatar_bytes=avatar)


# ---------------------------------------------------------------- 真实模式网络调用
def exchange_code_for_openid(code: str) -> dict:
    params = {
        "appid": settings.wechat_app_id,
        "secret": settings.wechat_app_secret,
        "code": code,
        "grant_type": "authorization_code",
    }
    r = httpx.get(WX_TOKEN_URL, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_wx_userinfo(access_token: str, openid: str) -> dict:
    params = {"access_token": access_token, "openid": openid, "lang": "zh_CN"}
    r = httpx.get(WX_USERINFO_URL, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def download_image(url: str) -> bytes | None:
    try:
        r = httpx.get(url, timeout=10)
        r.raise_for_status()
        return r.content
    except Exception:  # noqa: BLE001
        return None
