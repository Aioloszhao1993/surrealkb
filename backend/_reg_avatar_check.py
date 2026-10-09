import json, random, urllib.request, urllib.error

BASE = "http://127.0.0.1:8000"
preset = "data:image/svg+xml," + urllib.parse.quote(
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96'>"
    "<rect width='96' height='96' rx='48' fill='%239b59ff'/>"
    "<text x='48' y='63' font-size='46' text-anchor='middle' fill='#fff'>A</text></svg>",
    safe="",
)
u = f"avatar_reg_{random.randint(10000,99999)}"
body = json.dumps({"username": u, "password": "secret123", "email": None, "avatar": preset}).encode()

req = urllib.request.Request(f"{BASE}/api/auth/register", data=body, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    av = data["user"].get("avatar")
    print("username:", data["user"]["username"])
    print("avatar len:", len(av) if av else None)
    print("avatar head:", (av or "")[:40])
    tok = data["access_token"]
    req2 = urllib.request.Request(f"{BASE}/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req2, timeout=10) as r2:
        me = json.load(r2)
    print("me.avatar len:", len(me.get("avatar") or ""))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:400])
except Exception as e:
    print("ERR", type(e).__name__, e)
