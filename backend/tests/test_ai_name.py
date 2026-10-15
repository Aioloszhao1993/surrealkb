"""AI 助手的自定义名字（users.ai_name）。

前端在「登录用户还没给 AI 起过名」时于首次打开 AI 面板引导起名，
判断依据就是 UserOut.ai_name 是否为 None，所以这里重点守住：
默认 None / 能改 / 改完被 trim / 非法值被拒 / 改名字不会把别的字段带坏。
"""
from fastapi.testclient import TestClient


def test_new_user_has_no_ai_name(client: TestClient, auth):
    """新注册用户没起过名 —— 前端靠这个 None 决定是否弹起名引导。"""
    _, me = auth
    assert "ai_name" in me
    assert me["ai_name"] is None


def test_set_ai_name(client: TestClient, auth):
    headers, _ = auth
    r = client.patch("/api/users/me", headers=headers, json={"ai_name": "小知"})
    assert r.status_code == 200, r.text
    assert r.json()["ai_name"] == "小知"
    # 重新拉一次确认真的落库了（不是只回显）
    assert client.get("/api/auth/me", headers=headers).json()["ai_name"] == "小知"


def test_ai_name_is_trimmed(client: TestClient, auth):
    headers, _ = auth
    r = client.patch("/api/users/me", headers=headers, json={"ai_name": "  Friday  "})
    assert r.status_code == 200, r.text
    assert r.json()["ai_name"] == "Friday"


def test_ai_name_rejects_blank(client: TestClient, auth):
    """空串 / 纯空白都算非法 —— 用空串"清空名字"没有意义，
    前端靠 ai_name is None 判断要不要引导，不能让它变成空串。"""
    headers, _ = auth
    for bad in ("", "   ", "\t\n"):
        r = client.patch("/api/users/me", headers=headers, json={"ai_name": bad})
        assert r.status_code == 400, f"{bad!r} -> {r.status_code} {r.text}"
    # 失败后不应留下任何痕迹
    assert client.get("/api/auth/me", headers=headers).json()["ai_name"] is None


def test_ai_name_max_length(client: TestClient, auth):
    headers, _ = auth
    ok = "一" * 12
    assert client.patch("/api/users/me", headers=headers, json={"ai_name": ok}).status_code == 200
    too_long = "一" * 13
    assert client.patch("/api/users/me", headers=headers, json={"ai_name": too_long}).status_code == 422


def test_rename_keeps_other_fields(client: TestClient, auth):
    """只传 ai_name 时，不该把 username / bio 顺手清掉。"""
    headers, me = auth
    client.patch("/api/users/me", headers=headers, json={"bio": "这是我的简介"})
    r = client.patch("/api/users/me", headers=headers, json={"ai_name": "Nova"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai_name"] == "Nova"
    assert body["username"] == me["username"]
    assert body["bio"] == "这是我的简介"


def test_ai_name_survives_relogin(client: TestClient):
    """换设备/重新登录后名字还在（登录返回的 user 里带着它）。"""
    client.post(
        "/api/auth/register",
        json={"username": "keepname_test", "password": "secret-12345"},
    )
    tok = client.post(
        "/api/auth/token", data={"username": "keepname_test", "password": "secret-12345"}
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    client.patch("/api/users/me", headers=h, json={"ai_name": "周五"})

    again = client.post(
        "/api/auth/token", data={"username": "keepname_test", "password": "secret-12345"}
    ).json()
    assert again["user"]["ai_name"] == "周五"


def test_ai_name_not_in_public_profile(client: TestClient, auth):
    """别人的资料页不该看到你的 AI 名字（其 schema 是 UserPublic）。"""
    headers, me = auth
    client.patch("/api/users/me", headers=headers, json={"ai_name": "私密名"})
    data = client.get(f"/api/users/{me['id']}", headers=headers).json()
    assert "ai_name" not in data["user"]


def test_ai_name_requires_auth(client: TestClient):
    assert client.patch("/api/users/me", json={"ai_name": "x"}).status_code == 401
