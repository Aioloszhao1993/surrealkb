"""pytest 共享夹具：用临时 SQLite 库启动应用，无需真实 MySQL 与百炼 Key。

必须在 import app 之前设置环境变量（config 在导入时读 .env / 环境变量）。
"""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="surrealkb_test_"))
os.environ["DATABASE_URL_OVERRIDE"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["SECRET_KEY"] = "unit-test-secret-key-0123456789"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["ENABLE_VIRTUAL_LOGIN"] = "true"
os.environ["DASHSCOPE_API_KEY"] = ""  # 关闭 AI，问答类仅测鉴权

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    """每个用例前后清空限流与登录失败计数。

    限流是按「客户端 IP + 路径」的内存计数（ratelimit.py），登录失败锁定
    是按账号的内存计数（login_guard.py）。测试里登录/注册调用较多，
    不清零会被上一个用例的计数影响，出现莫名其妙的 429。
    """
    from app import login_guard, ratelimit

    ratelimit.reset_all()
    login_guard.reset_all()
    yield
    ratelimit.reset_all()
    login_guard.reset_all()


_counter = {"n": 0}


def _unique_user() -> dict:
    _counter["n"] += 1
    n = _counter["n"]
    return {"username": f"u{n:04d}test", "password": "secret-12345", "tenant_name": f"库{n}"}


@pytest.fixture
def auth(client: TestClient):
    """返回 (headers, user_json)。自动注册并登录。"""
    payload = _unique_user()
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/auth/me", headers=headers).json()
    return headers, me
