"""简易进程内限流（滑动窗口）。

说明：
- 单进程内存实现，适合单体部署；多 worker 场景下每个 worker 各限一份，
  如需全局精确限流请换 Redis（slowapi + limits 的 Redis storage）。
- key 默认按「客户端 IP + 路径」分桶。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

_HITS: dict[str, deque[float]] = defaultdict(deque)
_LOCK = Lock()

# 规则：路径前缀 -> (窗口秒数, 窗口内最大请求数)，仅对「写/贵」操作生效
# 结构说明：RULES 仅作用于 METHODS 中列出的 HTTP 方法（默认只限 POST/PUT/PATCH/DELETE），
# 避免把列表类 GET 也限掉。
METHODS = {"POST", "PUT", "PATCH", "DELETE"}
RULES: list[tuple[str, int, int]] = [
    ("/api/auth/login", 60, 10),      # 登录：每分钟 10 次
    ("/api/auth/token", 60, 10),      # 表单登录：同上
    ("/api/auth/register", 3600, 20),  # 注册：每小时 20 次（防批量小号）
    ("/api/ai/chat", 60, 30),         # AI 问答：每分钟 30 次（防刷额度）
    ("/api/ai/reindex", 300, 10),     # 重建索引：每 5 分钟 10 次
    ("/api/documents", 60, 30),       # 文档上传/操作：每分钟 30 次
]


def _client_ip(request: Request) -> str:
    # 反向代理场景下取 X-Forwarded-For 第一个地址
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _match(path: str) -> tuple[int, int] | None:
    for prefix, window, limit in RULES:
        if path.startswith(prefix):
            return window, limit
    return None


def _hit(key: str, window: int, limit: int) -> tuple[bool, int]:
    """记录一次访问，返回 (是否超限, 剩余可用次数)。"""
    now = time.monotonic()
    with _LOCK:
        q = _HITS[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return True, 0
        q.append(now)
        return False, limit - len(q)


async def rate_limit_middleware(request: Request, call_next):
    rule = _match(request.url.path)
    if rule and request.method in METHODS:
        window, limit = rule
        key = f"{_client_ip(request)}:{request.url.path}"
        exceeded, _remaining = _hit(key, window, limit)
        if exceeded:
            return JSONResponse(
                {"detail": "请求过于频繁，请稍后再试"},
                status_code=HTTP_429_TOO_MANY_REQUESTS,
            )
    return await call_next(request)


def reset_all() -> None:
    """清空进程内计数（测试/运维用）。"""
    with _LOCK:
        _HITS.clear()
