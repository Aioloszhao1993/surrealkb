"""依赖项：当前用户解析。"""
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    sub = decode_token(token)
    if not sub:
        raise credentials_exc
    user = db.get(User, int(sub))
    if not user:
        raise credentials_exc
    return user


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User | None:
    if not token:
        return None
    sub = decode_token(token)
    if not sub:
        return None
    return db.get(User, int(sub))


def get_session_key(
    x_session_key: str | None = Header(None, alias="X-Session-Key")
) -> str:
    """AI 聊天会话标识。由前端生成（每个浏览器一个），用于隔离聊天历史。

    历史读写都要求携带，避免仅凭泄露的 session_key 就能读取/清空他人记录：
    服务端把会话看作「一段匿名对话」，不属于任何账号，也不允许匿名跨会话枚举。
    """
    key = (x_session_key or "").strip()
    if not (8 <= len(key) <= 64):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "缺少或非法的会话标识（请在前端生成 8-64 位随机串，并通过 X-Session-Key 请求头携带）",
        )
    return key
