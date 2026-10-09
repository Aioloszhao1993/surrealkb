import httpx, sys
sys.stdout.reconfigure(encoding="utf-8")
base = "http://127.0.0.1:8000/api/ai"
def chat(q, sess):
    r = httpx.post(base + "/chat", json={"question": q, "session_key": sess}, timeout=90)
    d = r.json()
    print("Q:", q)
    print("A:", d["answer"])
    print("SOURCES:", [(s["id"], s["title"], s["score"]) for s in d["sources"]])
    print("-" * 60)
chat("站里有什么视频？", "sess_cn2")
chat("帮我找讲数据库的那个视频", "sess_cn2")
chat("随便聊两句，你叫什么？", "sess_cn2")
print("HISTORY len:", len(httpx.get(base + "/history/sess_cn2", timeout=30).json()["items"]))
