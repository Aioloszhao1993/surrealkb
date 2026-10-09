"""针对运行中的后端（真实 MySQL）做端到端验证。"""
import io
import json
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name)


def req(method, path, data=None, token=None, raw=False, ctype=None):
    url = BASE + path
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if raw:
        body = data
        headers["Content-Type"] = ctype
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            txt = resp.read().decode("utf-8")
            return resp.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


uname = "e2e_" + uuid.uuid4().hex[:8]

s, b = req("POST", "/api/auth/register", {"username": uname, "password": "secret123"})
check("register (real mysql)", s == 200 and "access_token" in b)
token = b["access_token"]
uid = b["user"]["id"]

s, b = req("GET", "/api/auth/me", token=token)
check("me", s == 200 and b["username"] == uname)

# multipart upload
boundary = "----sv" + uuid.uuid4().hex
fake = b"\x00\x00\x00\x18ftypmp42" + b"Z" * 2048
parts = []
def field(n, v):
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'.encode())
field("title", "MySQL 冒烟·超现实")
field("description", "真实数据库链路验证")
parts.append(
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="m.mp4"\r\n'
    f'Content-Type: video/mp4\r\n\r\n'.encode() + fake + b"\r\n"
)
parts.append(f"--{boundary}--\r\n".encode())
payload = b"".join(parts)
s, b = req("POST", "/api/videos", payload, token=token, raw=True,
           ctype=f"multipart/form-data; boundary={boundary}")
if s != 201:
    print("UPLOAD FAIL status=", s, "body=", b)
check("upload (multipart)", s == 201 and isinstance(b, dict) and b.get("title") == "MySQL 冒烟·超现实")
vid = b["id"] if isinstance(b, dict) else None

s, b = req("GET", "/api/videos")
check("list total>=1", s == 200 and b["total"] >= 1)

s, b = req("POST", f"/api/videos/{vid}/like", token=token)
check("like", s == 200 and b["active"] is True and b["count"] == 1)

s, b = req("POST", f"/api/videos/{vid}/favorite", token=token)
check("favorite", s == 200 and b["active"] is True)

s, b = req("GET", "/api/videos/favorites/me", token=token)
check("my favorites >=1", s == 200 and b["total"] >= 1)

s, b = req("POST", f"/api/videos/{vid}/share")
check("share", s == 200 and b.get("count", 0) >= 1)

s, b = req("DELETE", f"/api/videos/{vid}", token=token)
check("delete mine -> 204", s == 204)

print(f"\n==== {sum(ok)}/{len(ok)} passed (live MySQL) ====")
raise SystemExit(0 if all(ok) else 1)
