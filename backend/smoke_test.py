"""端到端冒烟测试（使用 SQLite 临时库，无需 MySQL）。

运行：python smoke_test.py
"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="sv_smoke_"))
os.environ["DATABASE_URL_OVERRIDE"] = f"sqlite:///{tmp.as_posix()}/test.db"
os.environ["SECRET_KEY"] = "smoke-secret"
os.environ["UPLOAD_DIR"] = str(tmp / "uploads")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


with TestClient(app) as c:
    # 健康检查
    r = c.get("/api/health")
    check("health", r.status_code == 200 and r.json()["status"] == "ok")

    # 注册
    r = c.post("/api/auth/register", json={"username": "dreamer", "password": "secret123"})
    check("register", r.status_code == 200 and "access_token" in r.json())
    token = r.json()["access_token"]
    uid = r.json()["user"]["id"]

    # 重复注册
    r = c.post("/api/auth/register", json={"username": "dreamer", "password": "secret123"})
    check("register duplicate -> 400", r.status_code == 400)

    # 登录
    r = c.post("/api/auth/login", json={"username": "dreamer", "password": "secret123"})
    check("login", r.status_code == 200)
    # 错误密码
    r = c.post("/api/auth/login", json={"username": "dreamer", "password": "wrong"})
    check("login wrong -> 401", r.status_code == 401)

    h = {"Authorization": f"Bearer {token}"}
    r = c.get("/api/auth/me", headers=h)
    check("me", r.status_code == 200 and r.json()["username"] == "dreamer")
    check("me no token -> 401", c.get("/api/auth/me").status_code == 401)

    # 上传（伪 mp4）
    fake = b"\x00\x00\x00\x18ftypmp42" + b"x" * 4096
    r = c.post(
        "/api/videos",
        headers=h,
        data={"title": "梦境一号", "description": "超现实的浪"},
        files={"file": ("clip.mp4", fake, "video/mp4")},
    )
    check("upload", r.status_code == 201)
    vid = r.json()["id"]
    check("upload owner", r.json()["owner"]["username"] == "dreamer")

    # 非法类型
    r = c.post(
        "/api/videos",
        headers=h,
        data={"title": "bad"},
        files={"file": ("a.txt", b"nope", "text/plain")},
    )
    check("upload bad type -> 400", r.status_code == 400)

    # 未登录上传
    r = c.post(
        "/api/videos",
        data={"title": "x"},
        files={"file": ("clip.mp4", fake, "video/mp4")},
    )
    check("upload no token -> 401", r.status_code == 401)

    # 列表 / 搜索 / 分页
    r = c.get("/api/videos")
    check("list", r.status_code == 200 and r.json()["total"] == 1)
    check("search hit", c.get("/api/videos", params={"q": "梦境"}).json()["total"] == 1)
    check("search miss", c.get("/api/videos", params={"q": "zzz"}).json()["total"] == 0)
    check("owner filter", c.get("/api/videos", params={"owner_id": uid}).json()["total"] == 1)

    # 详情 + 播放数
    r = c.get(f"/api/videos/{vid}")
    check("detail", r.status_code == 200 and r.json()["views"] == 1)
    check("detail 404", c.get("/api/videos/99999").status_code == 404)

    # 点赞（幂等切换）
    r = c.post(f"/api/videos/{vid}/like", headers=h)
    check("like on", r.json() == {"active": True, "count": 1})
    r = c.post(f"/api/videos/{vid}/like", headers=h)
    check("like off", r.json() == {"active": False, "count": 0})
    check("like no token -> 401", c.post(f"/api/videos/{vid}/like").status_code == 401)

    # 收藏
    r = c.post(f"/api/videos/{vid}/favorite", headers=h)
    check("favorite on", r.json() == {"active": True, "count": 1})
    r = c.get("/api/videos/favorites/me", headers=h)
    check("my favorites", r.status_code == 200 and r.json()["total"] == 1)

    # 转发
    before = c.get(f"/api/videos/{vid}").json()["views"]
    r = c.post(f"/api/videos/{vid}/share")
    check("share", r.status_code == 200 and r.json()["count"] == before + 1)

    # 静态媒体可达
    r = c.get(f"/media/{vid}", follow_redirects=True)
    fn = c.get("/api/videos")  # 拿文件名
    # 上传返回的 url 形如 /media/xxx.mp4
    url = c.get(f"/api/videos/{vid}").json()["url"]
    check("media served", c.get(url).status_code == 200)

    # 权限：他人不能改/删
    r = c.post(
        "/api/auth/register", json={"username": "intruder", "password": "secret123"}
    )
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    check("update other -> 403", c.patch(f"/api/videos/{vid}", headers=h2, json={"title": "x"}).status_code == 403)
    check("delete other -> 403", c.delete(f"/api/videos/{vid}", headers=h2).status_code == 403)

    # 作者可改
    r = c.patch(f"/api/videos/{vid}", headers=h, json={"title": "梦境一号·改"})
    check("update mine", r.status_code == 200 and r.json()["title"] == "梦境一号·改")

    # 作者可删
    check("delete mine", c.delete(f"/api/videos/{vid}", headers=h).status_code == 204)
    check("list after delete", c.get("/api/videos").json()["total"] == 0)

passed = sum(1 for _, v in ok if v)
print(f"\n==== {passed}/{len(ok)} passed ====")
raise SystemExit(0 if passed == len(ok) else 1)
