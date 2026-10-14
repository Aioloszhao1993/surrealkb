"""微信扫码登录服务（真实网站应用 / 小程序码中转 / 本地 Mock）。

三种模式，优先级 real > mp > mock：
- real：微信开放平台「网站应用」扫码（snsapi_login）。**需企业主体 + 300 元认证 + 已备案域名**。
- mp  ：小程序码中转。个人主体可用、零成本——网页展示带参小程序码，
        用户扫码进小程序，小程序把 wx.login 的 code + 票据回传后端换 openid。
- mock：未配置任何凭据时的本地模拟，二维码指向本机模拟授权页。

三种模式共用同一套 state 轮询机制：
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
from .models import User, WxLoginState, WxMpToken

WX_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
WX_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
WX_USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"

# 小程序相关接口
WX_MP_STABLE_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/stable_token"
WX_MP_QRCODE_URL = "https://api.weixin.qq.com/wxa/getwxacodeunlimit"
WX_MP_SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"

# access_token 提前 5 分钟视为过期，避免边界上刚好失效
_TOKEN_SAFETY_WINDOW = timedelta(seconds=300)

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


def create_login_state(db: Session, mode: str, state: str | None = None) -> WxLoginState:
    """新建登录会话。小程序模式传入 ticket 作为 state（scene 与 state 合一）。

    注意 created_at 显式用 Python 时间写入，而不是交给数据库 server_default：
    过期判断 `_is_expired` 用的是 Python 的 datetime.now()，若两者时钟/时区不一致
    （例如 SQLite 存 UTC、应用跑在 UTC+8），新会话会被立刻误判为「已过期」。
    """
    row = WxLoginState(
        state=state or new_state(),
        mode=mode,
        status="pending",
        created_at=datetime.now(),
    )
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


# ================================================================ 小程序码中转方案
# 适用：个人主体（无法申请开放平台「网站应用」）
#
# 流程：
#   1. 网页请求 /wx/qrcode → 后端生成 ticket（= scene）并调用微信生成带参小程序码
#   2. 用户用微信扫这张码 → 打开我们的小程序 pages/login/index
#   3. 小程序从 scene 取出 ticket，调 wx.login() 拿到 code，一起 POST 回 /wx/mp/bind
#   4. 后端用 code 换 openid → 复用 login_or_create_user() 建档 → 标记该 state 已确认
#   5. 网页轮询 /wx/poll 拿到 token，登录完成
#
# 设计要点：
#   - ticket 用 token_hex(16) = 32 字符，正好卡在微信 scene 32 字符上限
#   - scene 必须全局唯一：重复会导致「两个用户登录进同一个账号」
#   - access_token 必须缓存复用：微信对获取频率有限制


def new_mp_ticket() -> str:
    """生成登录票据。长度受微信 scene 32 字符上限约束，勿随意加大。"""
    return secrets.token_hex(settings.wx_mp_ticket_bytes)


def _wx_api_error(payload: dict) -> str | None:
    """微信接口统一用 errcode!=0 表示失败。"""
    errcode = payload.get("errcode")
    if errcode:
        return f"errcode={errcode} errmsg={payload.get('errmsg', '')}"
    return None


def get_mp_access_token(db: Session, force_refresh: bool = False) -> str:
    """取小程序 access_token（优先复用库里的缓存）。

    微信规定 access_token 有效期 7200 秒，且获取接口有频率限制；
    频繁获取会把上一个挤掉，导致小程序码接口随机失败。所以必须缓存。
    """
    appid = settings.wx_mp_app_id
    if not force_refresh:
        row = db.scalar(select(WxMpToken).where(WxMpToken.appid == appid))
        if row and row.expires_at and row.expires_at - datetime.now() > _TOKEN_SAFETY_WINDOW:
            return row.access_token

    # stable_token 是官方推荐的获取方式，WeChat 侧自带缓存，比 cgi-bin/token 更稳
    r = httpx.post(
        WX_MP_STABLE_TOKEN_URL,
        json={
            "grant_type": "client_credential",
            "appid": appid,
            "secret": settings.wx_mp_app_secret,
            "force_refresh": bool(force_refresh),
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    err = _wx_api_error(data)
    if err:
        raise RuntimeError(f"获取小程序 access_token 失败：{err}")
    token = data["access_token"]
    expires_in = int(data.get("expires_in", 7200))

    row = db.scalar(select(WxMpToken).where(WxMpToken.appid == appid))
    if row:
        row.access_token = token
        row.expires_at = datetime.now() + timedelta(seconds=expires_in)
    else:
        db.add(
            WxMpToken(
                appid=appid,
                access_token=token,
                expires_at=datetime.now() + timedelta(seconds=expires_in),
            )
        )
    db.commit()
    return token


def fetch_mp_qrcode_png(db: Session, scene: str) -> bytes:
    """调用微信生成「带参小程序码」，返回 PNG 字节。

    注意：小程序码指向的是**正式版**小程序（env_version 可切体验版/开发版）。
    页面未发布时会返回 41030（invalid page），开发期可设 WX_MP_CHECK_PATH=false。
    """
    body = {
        "scene": scene,
        "page": settings.wx_mp_page,
        "check_path": bool(settings.wx_mp_check_path),
        "env_version": settings.wx_mp_env_version,
        # 码本身留一点边距，线宽默认即可
        "width": 430,
    }

    def _call(token: str):
        return httpx.post(
            WX_MP_QRCODE_URL,
            params={"access_token": token},
            json=body,
            timeout=15,
        )

    r = _call(get_mp_access_token(db))
    # access_token 可能刚好失效（40001）——强制刷新后重试一次
    if r.headers.get("content-type", "").startswith("application/json"):
        payload = r.json()
        if payload.get("errcode") in (40001, 40014, 42001):
            r = _call(get_mp_access_token(db, force_refresh=True))
    if r.headers.get("content-type", "").startswith("application/json"):
        raise RuntimeError(f"生成小程序码失败：{_wx_api_error(r.json())}")
    return r.content


def exchange_code_for_openid_mp(code: str) -> dict:
    """小程序 wx.login() 的 code → openid（jscode2session）。

    注意：小程序 openid 与网站应用的 openid **不是同一个**，
    它只在「同一个小程序 AppID」内唯一。
    """
    params = {
        "appid": settings.wx_mp_app_id,
        "secret": settings.wx_mp_app_secret,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    r = httpx.get(WX_MP_SESSION_URL, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def create_mp_user(
    db: Session, openid: str, nickname: str | None = None
) -> User:
    """小程序扫码用户建档。头像用本地渐变生成（jscode2session 不含头像）。"""
    name = (nickname or "").strip()[:40] or "微信用户"
    avatar = generate_avatar_png(name[0], seed=openid)
    return login_or_create_user(db, openid, nickname=name, avatar_bytes=avatar)
