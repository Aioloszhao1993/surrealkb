"""认证：注册 / 登录 / 鉴权守卫。"""
from fastapi.testclient import TestClient


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["app"] == "SurrealKB"
    assert body["database"] == "up"


def test_register_and_login(client: TestClient):
    payload = {"username": "alice_test", "password": "secret-12345", "tenant_name": "Alice 库"}
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    assert token

    # 表单登录（OAuth2 password flow）
    r2 = client.post("/api/auth/token", data={"username": "alice_test", "password": "secret-12345"})
    assert r2.status_code == 200
    assert r2.json()["access_token"]


def test_login_wrong_password(client: TestClient):
    client.post("/api/auth/register", json={"username": "bob_test", "password": "secret-12345"})
    r = client.post("/api/auth/token", data={"username": "bob_test", "password": "wrong-pass"})
    assert r.status_code == 401


def test_me_requires_auth(client: TestClient):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_token(client: TestClient, auth):
    headers, me = auth
    assert me["username"].endswith("test")
    assert client.get("/api/auth/me", headers=headers).status_code == 200
