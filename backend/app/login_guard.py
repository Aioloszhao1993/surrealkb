"""账号级登录失败锁定（进程内实现）。

为什么需要这一层：
`ratelimit.py` 只按「IP + 路径」限流，攻击者换个 IP 就能继续对**同一个账号**
做定向密码爆破。这里按「用户名」再补一层计数，连续失败达阈值后短暂锁定。

已知取舍：
- 别人知道你的用户名时，可以故意连错若干次把你锁一段时间（拒绝服务）。
  相比「可以被无限次爆破」，小范围自用场景下选择锁定；因此阈值别设太小、
  锁定时长别设太长（默认 5 次 / 15 分钟），且登录成功立即清零。
- 进程内内存实现，重启即清零；单体单进程部署够用。多 worker / 多实例
  请换成 Redis（与 ratelimit.py 的说明一致）。
"""
from __future__ import annotations

import time
from threading import Lock

from .config import settings

_LOCK = Lock()
# 用户名（小写规范化） -> {"fails": int, "locked_until": float}
_STATE: dict[str, dict] = {}

# 状态表上限：超过就先清理已过期条目，避免被大量随机用户名撑爆内存
_MAX_ENTRIES = 5000


def _key(username: str | None) -> str:
    return (username or "").strip().lower()


def _enabled() -> bool:
    return bool(settings.login_max_failures and settings.login_lockout_seconds)


def _purge_expired(now: float) -> None:
    window = settings.login_lockout_seconds
    for k in [k for k, v in _STATE.items() if now - v.get("last", 0) > window * 2]:
        _STATE.pop(k, None)


def locked_seconds(username: str | None) -> int:
    """返回该账号还需锁定多少秒；未锁定返回 0。"""
    if not _enabled():
        return 0
    k = _key(username)
    now = time.monotonic()
    with _LOCK:
        st = _STATE.get(k)
        if not st:
            return 0
        left = st.get("locked_until", 0) - now
        return int(left) + 1 if left > 0 else 0


def record_failure(username: str | None) -> int:
    """记录一次密码错误。返回「还剩几次机会」，已锁定或关闭保护时返回 0。"""
    if not _enabled():
        return 0
    k = _key(username)
    now = time.monotonic()
    with _LOCK:
        if len(_STATE) >= _MAX_ENTRIES:
            _purge_expired(now)
        st = _STATE.setdefault(k, {"fails": 0, "locked_until": 0.0, "last": now})
        st["last"] = now
        st["fails"] = st.get("fails", 0) + 1
        max_failures = settings.login_max_failures
        if st["fails"] >= max_failures:
            st["locked_until"] = now + settings.login_lockout_seconds
            st["fails"] = 0
            return 0
        return max_failures - st["fails"]


def clear(username: str | None) -> None:
    """登录成功后清零。"""
    with _LOCK:
        _STATE.pop(_key(username), None)


def reset_all() -> None:
    """清空全部状态（测试/运维用）。"""
    with _LOCK:
        _STATE.clear()
