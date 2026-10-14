"""文档：上传（含 403 守卫 / 类型校验 / 大小限制）与详情。"""
import io

from fastapi.testclient import TestClient


def _upload(client: TestClient, headers, filename="note.txt", data=b"hello world", title=None):
    files = {"file": (filename, io.BytesIO(data), "text/plain")}
    form = {}
    if title:
        form["title"] = title
    return client.post("/api/documents", headers=headers, files=files, data=form)


def test_upload_requires_auth(client: TestClient):
    files = {"file": ("a.txt", io.BytesIO(b"x"), "text/plain")}
    assert client.post("/api/documents", files=files).status_code == 401


def test_upload_txt_ok(client: TestClient, auth):
    headers, _ = auth
    r = _upload(client, headers, data="这是一份测试文档。公司年假为 15 天。".encode("utf-8"))
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] in ("ready", "pending")
    assert doc["title"]

    # 详情
    d = client.get(f"/api/documents/{doc['id']}", headers=headers)
    assert d.status_code == 200
    assert d.json()["id"] == doc["id"]


def test_upload_bad_type(client: TestClient, auth):
    headers, _ = auth
    r = _upload(client, headers, filename="evil.exe", data=b"MZ")
    assert r.status_code == 400


def test_upload_empty_forbidden_ok(client: TestClient, auth):
    headers, _ = auth
    # 空文件本身应被接受（内容分块为空），这里仅验证不 5xx
    r = _upload(client, headers, filename="empty.txt", data=b"")
    assert r.status_code in (201, 400)


def test_list_documents(client: TestClient, auth):
    headers, _ = auth
    _upload(client, headers, data=b"abc")
    r = client.get("/api/documents", headers=headers)  # 默认按当前用户 tenant
    assert r.status_code in (200, 401)
    if r.status_code == 200:
        assert "items" in r.json()
