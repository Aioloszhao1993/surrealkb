"""微信扫码登录 + 头像 + 关注 功能的端到端冒烟测试（直连 Running 后端）。

前置：后端已在 8000 运行。
运行： backend\\.venv\\Scripts\\python.exe wx_smoke.py
"""
import io
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
ok = 0
fail = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    mark = "PASS" if cond else "FAIL"
    if cond:
        ok += 1
    else:
        fail += 1
    print(f"[{mark}] {name} {extra}")


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=15)

    # 0) 健康检查
    r = c.get("/api/health")
    check("health 200", r.status_code == 200)

    # 1) 虚拟扫码（一键生成微信用户）
    r = c.get("/api/auth/wx/virtual")
    check("wx/virtual 200", r.status_code == 200, f"-> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:300])
        return 1
    d = r.json()
    token = d["access_token"]
    u1 = d["user"]
    check("virtual 返回 token", bool(token))
    check("virtual 用户名非空", bool(u1.get("username")), f"name={u1.get('username')}")
    check("virtual 自带头像", bool(u1.get("avatar")), f"avatar={u1.get('avatar')}")
    H = {"Authorization": f"Bearer {token}"}

    # 头像文件可访问
    av = u1.get("avatar")
    if av:
        rr = c.get(f"/media/{av}")
        check("虚拟头像可下载", rr.status_code == 200 and len(rr.content) > 100, f"{len(rr.content)}B")

    # 2) 两次虚拟扫码应生成不同用户（随机名/头像）
    d2 = c.get("/api/auth/wx/virtual").json()
    u2 = d2["user"]
    check("两次虚拟扫码用户不同", u1["id"] != u2["id"], f"{u1['username']} vs {u2['username']}")
    check("两次头像不同", u1.get("avatar") != u2.get("avatar"))

    # 3) me 接口带出头像
    r = c.get("/api/auth/me", headers=H)
    check("me 200", r.status_code == 200)
    check("me 含 avatar 字段", "avatar" in r.json())

    # 4) 上传自定义头像
    png = _tiny_png()
    r = c.post(
        "/api/auth/avatar",
        headers=H,
        files={"file": ("a.png", png, "image/png")},
    )
    check("上传头像 200", r.status_code == 200, f"-> {r.status_code} {r.text[:120]}")
    if r.status_code == 200:
        av2 = r.json()["avatar"]
        check("头像路径为 avatars/*", str(av2).startswith("avatars/"), av2 or "")
        rr = c.get(f"/media/{av2}")
        check("上传头像可下载", rr.status_code == 200 and rr.content == png)

    # 5) 预设头像（data URL）
    preset = "data:image/svg+xml;base64,PHN2Zy8+"
    r = c.patch("/api/auth/avatar", headers=H, json={"avatar": preset})
    check("预设头像 200", r.status_code == 200 and r.json()["avatar"] == preset)

    # 6) 用户资料
    r = c.get(f"/api/users/{u1['id']}", headers=H)
    check("用户资料 200", r.status_code == 200)
    if r.status_code == 200:
        p = r.json()
        for k in ("followers", "following", "works", "likes_received", "total_views"):
            check(f"资料含 {k}", k in p, f"{k}={p.get(k)}")
        check("is_self=True", p["is_self"] is True)
        check("资料返回头像", "avatar" in p["user"])

    # 7) 关注 / 取关
    r = c.post(f"/api/users/{u2['id']}/follow", headers=H)
    check("关注 200", r.status_code == 200 and r.json()["following"] is True, str(r.json()))
    r = c.get(f"/api/users/{u2['id']}", headers=H)
    check("对方 followers=1", r.json()["followers"] == 1)
    check("is_following=True", r.json()["is_following"] is True)
    r = c.post(f"/api/users/{u2['id']}/follow", headers=H)
    check("取关 200", r.status_code == 200 and r.json()["following"] is False)
    r = c.post(f"/api/users/{u1['id']}/follow", headers=H)
    check("不能关注自己 400", r.status_code == 400)

    # 8) 作品 / 点赞 / 收藏 列表
    for path, label in (
        (f"/api/users/{u1['id']}/videos", "作品"),
        (f"/api/users/{u1['id']}/likes", "点赞"),
        (f"/api/users/{u1['id']}/favorites", "收藏"),
    ):
        r = c.get(path)
        check(f"用户{label}列表 200", r.status_code == 200, f"total={r.json().get('total') if r.status_code==200 else r.text[:80]}")

    # 9) 视频列表 owner 带 avatar
    r = c.get("/api/videos")
    check("视频列表 200", r.status_code == 200)
    if r.status_code == 200 and r.json()["items"]:
        ow = r.json()["items"][0]["owner"]
        check("视频 owner 含 avatar 字段", "avatar" in ow)

    # 10) 真实扫码链路（Mock 模式：qrcode + 模拟授权页 + 轮询）
    r = c.get("/api/auth/wx/qrcode")
    check("wx/qrcode 200", r.status_code == 200)
    q = r.json()
    check("qrcode 返回 data URL", str(q.get("qr", "")).startswith("data:image/png;base64,"))
    check("qrcode 模式标记", q.get("mode") in ("mock", "real"), f"mode={q.get('mode')}")
    st = q["state"]
    r = c.get("/api/auth/wx/poll", params={"state": st})
    check("poll 初始 pending", r.json()["status"] == "pending")
    if q.get("mode") == "mock":
        r = c.get("/api/auth/wx/mock", params={"state": st})
        check("mock 授权页 200", r.status_code == 200 and "确认登录" in r.text)
        r = c.get("/api/auth/wx/mock/confirm", params={"state": st})
        check("mock 确认登录 200", r.status_code == 200)
        r = c.get("/api/auth/wx/poll", params={"state": st})
        j = r.json()
        check("poll 变 confirmed", j["status"] == "confirmed")
        check("confirmed 带 token", bool(j.get("token")))
        r = c.get("/api/auth/wx/poll", params={"state": st})
        check("token 被消费后 consumed/expired", r.json()["status"] in ("consumed", "expired"))

    print(f"\n==== {ok} passed, {fail} failed ====")
    return 0 if fail == 0 else 2


def _tiny_png() -> bytes:
    # 1x1 透明 PNG
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )


if __name__ == "__main__":
    sys.exit(main())
