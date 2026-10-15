"""密码哈希与 JWT。"""
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 微信扫码登录的用户没有密码，库里存的是这个哨兵值（见 wechat_service/login_or_create_user）。
# 它不是合法的 bcrypt 串，绝不能直接丢给 passlib 校验。
NO_PASSWORD_PREFIX = "!wx-no-password"

MIN_PASSWORD_LEN = 6

# 常见弱口令（按小写比较）。只收最常见的一批，不做成黑名单工程。
_WEAK_PASSWORDS = {
    "123456", "1234567", "12345678", "123456789", "1234567890",
    "111111", "000000", "666666", "888888", "88888888",
    "password", "passw0rd", "qwerty", "abc123", "abcd1234",
    "admin", "admin123", "root123", "letmein", "iloveyou",
    "welcome", "monkey", "dragon", "master", "test123",
    "surreal", "surrealkb", "weixin", "woaini", "5201314",
}


def password_error(password: str, username: str | None = None) -> str | None:
    """校验密码强度：返回一句人话错误信息，通过则返回 None。

    规则刻意保持克制 —— 不强制「大小写 + 符号」混合。小范围自用场景下
    过严的规则只会让用户把密码写在便签上，反而更不安全；这里只挡掉
    真正的一击即破（短、纯数字、烂大街、等于用户名）。
    """
    pwd = password or ""
    if len(pwd) < MIN_PASSWORD_LEN:
        return f"密码至少 {MIN_PASSWORD_LEN} 位"
    if len(pwd) > 128:
        return "密码过长（最多 128 位）"
    if pwd.isdigit():
        return "密码不能全是数字"
    if pwd.lower() in _WEAK_PASSWORDS:
        return "这个密码太常见了，换一个吧"
    if username and pwd.strip().lower() == username.strip().lower():
        return "密码不能和用户名相同"
    return None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def has_password(hashed: str | None) -> bool:
    """该账号是否设置过密码（微信扫码登录的用户没有）。"""
    return bool(hashed) and not str(hashed).startswith(NO_PASSWORD_PREFIX)


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。

    对「必然失败」的输入一律返回 False，**不要抛异常**：
    1) 微信登录用户没设密码，库里是哨兵值 `!wx-no-password!`，不是合法 bcrypt 串；
    2) 历史脏数据 / 空值。
    之前没兜住会让 /api/auth/login 直接 500 —— 只要有人拿微信用户的用户名试密码
    就能稳定触发（既刷错误日志，也让正常用户看到莫名其妙的 500）。
    """
    if not plain or not hashed:
        return False
    if str(hashed).startswith(NO_PASSWORD_PREFIX):
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
