"""AI 助手链路自测：直接打后端接口，验证 登录鉴权 + 向量检索 + 多轮对话 + 历史落库。

运行（后端已在 8000 运行）：
    cd D:\\surreal_kb\\backend
    .\\.venv\\Scripts\\python.exe ai_smoke.py

用的是终端直接打 127.0.0.1:8000，不经过 vite 代理。
注意：/api/ai/chat 现已要求登录，且会话标识通过 X-Session-Key 请求头携带。
"""
import random

import sys

import httpx

API = "http://127.0.0.1:8000/api"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    ok = True

    def check(name: str, resp: httpx.Response) -> dict:
        nonlocal ok
        tag = "OK " if resp.status_code < 400 else "ERR"
        print(f"[{tag}] {name} -> HTTP {resp.status_code}")
        if resp.status_code >= 400:
            ok = False
            print("      body:", resp.text[:200])
            return {}
        return resp.json()

    # 登录：注册一个独立知识库用户（自带一个空知识库）
    sfx = str(random.randint(100000, 999999))
    reg = httpx.post(
        f"{API}/auth/register",
        json={"username": f"aismoke{sfx}", "password": "pass123456", "tenant_name": f"smoke{sfx}"},
        timeout=30,
    )
    if reg.status_code != 200:
        print("[ERR] register ->", reg.status_code, reg.text[:200])
        return 1
    tok = reg.json()["access_token"]
    auth = {"Authorization": f"Bearer {tok}"}
    sess = "ai_smoke"
    hdr = {**auth, "X-Session-Key": sess}

    st = check("status", httpx.get(f"{API}/ai/status", headers=auth, timeout=20))
    print("      enabled=%s indexed=%s" % (st.get("enabled"), st.get("indexed_chunks")))
    if not st.get("enabled"):
        print("AI 未启用：检查 backend/.env 的 DASHSCOPE_API_KEY")
        return 1

    # 未登录必须 401
    anon = httpx.post(f"{API}/ai/chat", json={"question": "hi"}, timeout=20)
    if anon.status_code == 401:
        print("[OK ] 未登录 chat 被拒 401")
    else:
        ok = False
        print("[ERR] 未登录 chat 应 401，实际", anon.status_code)

    r1 = check(
        "chat / 空知识库提问",
        httpx.post(
            f"{API}/ai/chat",
            headers=hdr,
            json={"question": "你好，你能做什么？"},
            timeout=90,
        ),
    )
    print("      A:", (r1.get("answer") or "")[:120].replace("\n", " "))

    r2 = check(
        "chat / 多轮追问",
        httpx.post(
            f"{API}/ai/chat",
            headers=hdr,
            json={"question": "再简单说一句"},
            timeout=90,
        ),
    )
    print("      sources:", [s["title"] for s in r2.get("sources", [])])

    h = check("history", httpx.get(f"{API}/ai/history", headers=hdr, timeout=20))
    print("      turns:", len(h.get("items", [])))

    c = check("clear", httpx.delete(f"{API}/ai/history", headers=hdr, timeout=20))
    print("      deleted:", c.get("deleted"))

    rx = check("reindex", httpx.post(f"{API}/ai/reindex", headers=auth, timeout=120))
    print("      ", rx)

    print("\n=== AI SMOKE %s ===" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
