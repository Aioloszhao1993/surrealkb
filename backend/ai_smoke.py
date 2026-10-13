"""AI 助手链路自测：直接打后端接口，验证 向量检索 + 多轮对话 + 历史落库。

运行（后端已在 8000 运行）：
    cd D:\\surreal_kb\\backend
    .\\.venv\\Scripts\\python.exe ai_smoke.py

用的是终端直接打 127.0.0.1:8000，不经过 vite 代理。
"""
import sys

import httpx

BASE = "http://127.0.0.1:8000/api/ai"


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

    st = check("status", httpx.get(f"{BASE}/status", timeout=20))
    print("      enabled=%s indexed=%s" % (st.get("enabled"), st.get("indexed_videos")))
    if not st.get("enabled"):
        print("AI 未启用：检查 backend/.env 的 DASHSCOPE_API_KEY")
        return 1

    sess = "ai_smoke"
    r1 = check(
        "chat / 站内找视频",
        httpx.post(
            f"{BASE}/chat",
            json={"question": "站里有什么视频？", "session_key": sess},
            timeout=90,
        ),
    )
    print("      A:", (r1.get("answer") or "")[:120].replace("\n", " "))
    print("      sources:", [s["title"] for s in r1.get("sources", [])])

    r2 = check(
        "chat / 语义检索",
        httpx.post(
            f"{BASE}/chat",
            json={"question": "帮我找跟数据库有关的那个视频", "session_key": sess},
            timeout=90,
        ),
    )
    print("      sources:", [s["title"] for s in r2.get("sources", [])])

    h = check("history", httpx.get(f"{BASE}/history/{sess}", timeout=20))
    print("      turns:", len(h.get("items", [])))

    c = check("clear", httpx.delete(f"{BASE}/history/{sess}", timeout=20))
    print("      deleted:", c.get("deleted"))

    rx = check("reindex", httpx.post(f"{BASE}/reindex", timeout=120))
    print("      ", rx)

    print("\n=== AI SMOKE %s ===" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
