"""认证安全：密码强度、账号级登录失败锁定、修改密码。

（限流按 IP 计数，这里靠 conftest 的 _reset_limits 夹具在每个用例前清零。）
"""
import pytest
from fastapi.testclient import TestClient

GOOD_PWD = "secret-12345"


# ---------------------------------------------------------------- 密码强度
@pytest.mark.parametrize(
    "password, reason",
    [
        ("12345678", "全数字"),
        ("000000", "全数字"),
        ("password", "常见弱口令"),
        ("abc123", "常见弱口令"),
        ("admin123", "常见弱口令"),
    ],
)
def test_register_rejects_weak_password(client: TestClient, password: str, reason: str):
    r = client.post(
        "/api/auth/register",
        json={"username": "weakpwd_user", "password": password, "tenant_name": "库"},
    )
    assert r.status_code == 422, f"{reason} 的密码应被拒绝，实际 {r.status_code}"


def test_register_rejects_password_equal_to_username(client: TestClient):
    r = client.post(
        "/api/auth/register",
        json={"username": "samepwd123", "password": "samepwd123", "tenant_name": "库"},
    )
    assert r.status_code == 422


def test_register_rejects_short_password(client: TestClient):
    r = client.post(
        "/api/auth/register",
        json={"username": "shortpwd", "password": "ab1", "tenant_name": "库"},
    )
    assert r.status_code == 422


def test_register_accepts_reasonable_password(client: TestClient):
    r = client.post(
        "/api/auth/register",
        json={"username": "okpwd_user", "password": GOOD_PWD, "tenant_name": "库"},
    )
    assert r.status_code in (200, 201), r.text


# ---------------------------------------------------------------- 登录失败锁定
def _register(client: TestClient, username: str) -> None:
    r = client.post(
        "/api/auth/register",
        json={"username": username, "password": GOOD_PWD, "tenant_name": "库"},
    )
    assert r.status_code in (200, 201), r.text


def test_login_lockout_is_account_level_not_ip_level(client: TestClient):
    """换 IP（伪造 X-Forwarded-For）也锁得住 —— 这正是加这一层的原因。"""
    _register(client, "lockme_user")

    # 前 4 次给「还能试几次」的提示
    for i in range(1, 5):
        r = client.post(
            "/api/auth/login",
            json={"username": "lockme_user", "password": "wrong-pass"},
            headers={"X-Forwarded-For": f"203.0.113.{i}"},
        )
        assert r.status_code == 401, r.text
        assert "还可尝试" in r.json()["detail"]

    # 第 5 次触发锁定
    r = client.post(
        "/api/auth/login",
        json={"username": "lockme_user", "password": "wrong-pass"},
        headers={"X-Forwarded-For": "203.0.113.5"},
    )
    assert r.status_code == 401, r.text

    # 之后即使密码正确、即使又换 IP，也应被拒
    r = client.post(
        "/api/auth/login",
        json={"username": "lockme_user", "password": GOOD_PWD},
        headers={"X-Forwarded-For": "198.51.100.77"},
    )
    assert r.status_code == 429, r.text
    assert "锁定" in r.json()["detail"]


def test_login_success_clears_failure_counter(client: TestClient):
    _register(client, "clearable_user")

    for _ in range(2):
        client.post(
            "/api/auth/login",
            json={"username": "clearable_user", "password": "wrong-pass"},
        )

    r = client.post(
        "/api/auth/login",
        json={"username": "clearable_user", "password": GOOD_PWD},
    )
    assert r.status_code == 200, r.text

    # 计数已清零 → 再错一次，应重新显示「还可尝试 4 次」
    r = client.post(
        "/api/auth/login",
        json={"username": "clearable_user", "password": "wrong-pass"},
    )
    assert r.status_code == 401
    assert "还可尝试 4 次" in r.json()["detail"]


# ---------------------------------------------------------------- 修改密码
def test_change_password_requires_auth(client: TestClient):
    r = client.post(
        "/api/auth/password",
        json={"old_password": GOOD_PWD, "new_password": "new-secret-99"},
    )
    assert r.status_code == 401


def test_change_password_wrong_old(client: TestClient, auth):
    headers, _ = auth
    r = client.post(
        "/api/auth/password",
        json={"old_password": "not-my-password", "new_password": "new-secret-99"},
        headers=headers,
    )
    assert r.status_code == 401


def test_change_password_rejects_same_as_old(client: TestClient, auth):
    headers, _ = auth
    r = client.post(
        "/api/auth/password",
        json={"old_password": GOOD_PWD, "new_password": GOOD_PWD},
        headers=headers,
    )
    assert r.status_code == 400


def test_change_password_rejects_weak_new(client: TestClient, auth):
    headers, _ = auth
    r = client.post(
        "/api/auth/password",
        json={"old_password": GOOD_PWD, "new_password": "12345678"},
        headers=headers,
    )
    assert r.status_code == 422


def test_change_password_then_login_with_new(client: TestClient, auth):
    headers, me = auth
    username = me["username"]
    new_pwd = "new-secret-99"

    r = client.post(
        "/api/auth/password",
        json={"old_password": GOOD_PWD, "new_password": new_pwd},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # 新密码可登录
    assert (
        client.post("/api/auth/login", json={"username": username, "password": new_pwd}).status_code
        == 200
    )
    # 旧密码不再可用
    assert (
        client.post(
            "/api/auth/login", json={"username": username, "password": GOOD_PWD}
        ).status_code
        == 401
    )


def test_empty_old_password_rejected_when_password_exists(client: TestClient, auth):
    headers, _ = auth
    r = client.post(
        "/api/auth/password",
        json={"old_password": "", "new_password": "another-pass9"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert "原密码" in r.json()["detail"]


# ------------------------------------------------- 微信用户没有密码（哨兵值）
def test_login_with_wechat_user_does_not_500(client: TestClient):
    """微信用户的 hashed_password 是哨兵值 `!wx-no-password!`，不是合法 bcrypt 串。

    拿这种用户名去试密码，必须干净地回 401 —— 一旦抛异常就是 500，
    等于任何人都能稳定刷出错误日志。
    """
    r = client.get("/api/auth/wx/virtual")
    assert r.status_code == 200, r.text
    username = r.json()["user"]["username"]

    r2 = client.post("/api/auth/login", json={"username": username, "password": "whatever-123"})
    assert r2.status_code == 401, r2.text


def test_wechat_user_can_set_password_without_old(client: TestClient):
    """微信登录用户从没设过密码，应允许直接设置（已通过微信身份认证）。"""
    r = client.get("/api/auth/wx/virtual")
    data = r.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    username = data["user"]["username"]
    new_pwd = "brand-new-pass9"

    r2 = client.post(
        "/api/auth/password",
        json={"old_password": "", "new_password": new_pwd},
        headers=headers,
    )
    assert r2.status_code == 200, r2.text

    # 设置后即可用账号密码登录
    r3 = client.post("/api/auth/login", json={"username": username, "password": new_pwd})
    assert r3.status_code == 200, r3.text
