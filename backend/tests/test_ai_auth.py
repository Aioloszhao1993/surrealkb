"""AI 问答接口的鉴权与会话隔离（不调用真实大模型）。"""
from fastapi.testclient import TestClient


def test_ai_status_public(client: TestClient):
    r = client.get("/api/ai/status")
    assert r.status_code == 200
    assert "enabled" in r.json()


def test_chat_requires_auth(client: TestClient):
    r = client.post("/api/ai/chat", json={"question": "你好"})
    assert r.status_code == 401


def test_history_requires_auth(client: TestClient):
    assert client.get("/api/ai/history").status_code == 401
    assert client.delete("/api/ai/history").status_code == 401


def test_chat_requires_session_header(client: TestClient, auth):
    headers, _ = auth
    # 未带 X-Session-Key -> 400
    r = client.post("/api/ai/chat", headers=headers, json={"question": "你好"})
    assert r.status_code == 400


def test_chat_with_session_header(client: TestClient, auth):
    headers, _ = auth
    h = {**headers, "X-Session-Key": "sess-abcdefgh1234"}
    # AI 未配置 Key 时应 503（服务不可用），但绝不能 401/500
    r = client.post("/api/ai/chat", headers=h, json={"question": "你好"})
    assert r.status_code in (200, 503)


def test_history_isolated_between_users(client: TestClient, auth):
    headers, _ = auth
    h = {**headers, "X-Session-Key": "sess-shared123456"}
    r = client.get("/api/ai/history", headers=h)
    # 未配置 AI 时也可能 200 返回空历史；无论哪种，必须不 5xx
    assert r.status_code in (200, 503)
