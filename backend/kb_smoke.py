"""知识库版端到端冒烟测试（真实 MySQL + 真实百炼 API）。

用法： backend\.venv\Scripts\python.exe kb_smoke.py
覆盖：注册(建库) -> 登录 -> 上传 txt/md -> 分块 -> 向量索引 -> 检索问答(带出处)
      -> 文档列表/详情/分块 -> 租户信息 -> 邀请码加入 -> 越权隔离 -> 删除。
"""
from __future__ import annotations

import io
import sys
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PASSED = 0
FAILED = 0


def check(cond: bool, label: str) -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  [PASS] {label}")
    else:
        FAILED += 1
        print(f"  [FAIL] {label}")


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def main() -> int:
    sfx = uuid.uuid4().hex[:6]
    uname = f"kb_{sfx}"

    print("\n=== 1. 注册（自动创建知识库）===")
    r = client.post(
        "/api/auth/register",
        json={"username": uname, "password": "pass123456", "tenant_name": f"测试知识库{sfx}"},
    )
    check(r.status_code == 200, f"register 200 ({r.status_code})")
    tok = r.json()["access_token"]
    me = r.json()["user"]
    check(me.get("role") == "owner", f"新用户角色 owner ({me.get('role')})")
    check(bool(me.get("tenant_id")), f"已绑定知识库 ({me.get('tenant_id')})")

    print("\n=== 2. 当前知识库 ===")
    r = client.get("/api/tenants/current", headers=auth(tok))
    check(r.status_code == 200, "tenants/current 200")
    tenant = r.json()
    check(tenant["invite_code"], f"邀请码 {tenant.get('invite_code')}")
    check(tenant["member_count"] == 1, f"成员数=1 ({tenant.get('member_count')})")
    check(tenant.get("can_manage") is True, "owner 可管理 (can_manage=True)")

    print("\n=== 3. 上传 TXT 文档 ===")
    content = (
        "青岛公司差旅报销制度\n\n"
        "第一条 目的：规范公司员工出差期间的交通、住宿、餐饮等费用的报销标准与流程。\n\n"
        "第二条 交通费：市内交通据实报销，跨城出行优先高铁二等座；"
        "乘坐飞机须为经济舱，且需提前三天申请审批。\n\n"
        "第三条 住宿费：一线城市每晚不超过 600 元，二线城市不超过 400 元，"
        "其余城市不超过 300 元，凭发票报销。\n\n"
        "第四条 餐饮补贴：出差期间每人每天补贴 100 元，"
        "含业务招待的需单独填写招待申请单。\n\n"
        "第五条 报销流程：出差结束后 7 个工作日内，将发票与审批单提交至财务部，"
        "经部门负责人签字后走线上报销系统。\n"
    ).encode("utf-8")
    r = client.post(
        "/api/documents",
        headers=auth(tok),
        data={"title": "差旅报销制度"},
        files={"file": ("reimburse.txt", io.BytesIO(content), "text/plain")},
    )
    check(r.status_code == 201, f"上传 201 ({r.status_code}) {r.text[:120]}")
    doc = r.json()
    doc_id = doc["id"]
    check(doc["status"] == "ready", f"解析状态 ready ({doc['status']})")
    check(doc["chunk_count"] > 0, f"分块数 > 0 ({doc['chunk_count']})")
    check(doc["char_count"] > 100, f"字符数记录 ({doc['char_count']})")

    print("\n=== 4. 文档列表 / 详情 / 分块 ===")
    r = client.get("/api/documents", headers=auth(tok))
    check(r.status_code == 200 and r.json()["total"] >= 1, f"列表 total={r.json().get('total')}")
    r = client.get(f"/api/documents/{doc_id}/chunks", headers=auth(tok))
    check(r.status_code == 200 and len(r.json()) >= 1, f"分块接口 {len(r.json())} 块")

    print("\n=== 5. 向量索引（真实百炼）===")
    r = client.post("/api/ai/reindex", headers=auth(tok))
    check(r.status_code == 200, "reindex 200")
    info = r.json()
    print(f"    reindex -> {info}")
    check(info.get("embedded", 0) >= doc["chunk_count"], f"已向量化 {info.get('embedded')}")

    print("\n=== 6. 知识库问答（带出处）===")
    r = client.post(
        "/api/ai/chat",
        headers=auth(tok),
        json={"question": "出差住宿费一晚最多能报销多少？", "session_key": f"s_{sfx}"},
    )
    check(r.status_code == 200, f"chat 200 ({r.status_code}) {r.text[:160]}")
    if r.status_code == 200:
        ans = r.json()["answer"]
        srcs = r.json()["sources"]
        print(f"    A: {ans[:120]}")
        check(len(srcs) > 0, f"返回出处 {len(srcs)} 条")
        check(any("住宿" in (s.get("snippet") or "") or "报销" in (s.get("snippet") or "") for s in srcs),
              "出处片段命中相关内容")

    print("\n=== 7. 上传 Markdown + 检索 ===")
    md = (
        "# 员工入职指南\n\n"
        "## 试用期\n新员工试用期为 3 个月，表现优秀者可提前转正。\n\n"
        "## 年假\n入职满一年享有 5 天年假，每满一年增加一天，最多 15 天。\n\n"
        "## 办公时间\n标准工作时间 9:30 - 18:30，弹性一小时。\n"
    ).encode("utf-8")
    r = client.post(
        "/api/documents",
        headers=auth(tok),
        data={"title": "入职指南"},
        files={"file": ("onboard.md", io.BytesIO(md), "text/markdown")},
    )
    check(r.status_code == 201 and r.json()["status"] == "ready", "上传 md 并解析")
    r = client.post("/api/ai/reindex", headers=auth(tok))
    check(r.status_code == 200, "再次 reindex")
    r = client.post(
        "/api/ai/chat",
        headers=auth(tok),
        json={"question": "入职多久可以享受年假？", "session_key": f"s2_{sfx}"},
    )
    if r.status_code == 200:
        ans = r.json()["answer"]
        print(f"    A: {ans[:120]}")
        check("年假" in ans or "一年" in ans, "回答命中入职指南内容")

    print("\n=== 8. 越权隔离（另一个用户/知识库查不到）===")
    uname2 = f"kb2_{sfx}"
    r2 = client.post(
        "/api/auth/register",
        json={"username": uname2, "password": "pass123456", "tenant_name": f"别人的库{sfx}"},
    )
    tok2 = r2.json()["access_token"]
    r = client.get(f"/api/documents/{doc_id}", headers=auth(tok2))
    check(r.status_code == 404, f"跨租户访问文档被拒 ({r.status_code})")
    r = client.get("/api/documents", headers=auth(tok2))
    check(r.json()["total"] == 0, f"跨租户列表为空 ({r.json().get('total')})")
    r = client.post(
        "/api/ai/chat",
        headers=auth(tok2),
        json={"question": "住宿费报销多少？", "session_key": f"o_{sfx}"},
    )
    if r.status_code == 200:
        check(len(r.json()["sources"]) == 0, "跨租户检索无结果")

    print("\n=== 9. 邀请码加入 ===")
    invite = tenant["invite_code"]
    uname3 = f"kb3_{sfx}"
    client.post("/api/auth/register", json={"username": uname3, "password": "pass123456"})
    r = client.post("/api/auth/login", json={"username": uname3, "password": "pass123456"})
    tok3 = r.json()["access_token"]
    r = client.post("/api/tenants/join", headers=auth(tok3), json={"invite_code": invite})
    check(r.status_code == 200, f"加入知识库 200 ({r.status_code}) {r.text[:100]}")
    r = client.get("/api/documents", headers=auth(tok3))
    check(r.json()["total"] >= 2, f"新成员可见库内文档 total={r.json().get('total')}")

    print("\n=== 9b. 邀请码权限（仅 owner/admin 可见与管理）===")
    # 普通成员看 current：invite_code 应为 None，can_manage=False
    r = client.get("/api/tenants/current", headers=auth(tok3))
    check(r.status_code == 200, "成员 tenants/current 200")
    mt = r.json()
    check(mt.get("invite_code") is None, f"成员看不到邀请码 ({mt.get('invite_code')})")
    check(mt.get("can_manage") is False, "成员 can_manage=False")
    # 成员重置邀请码 -> 403
    r = client.post("/api/tenants/invite/reset", headers=auth(tok3))
    check(r.status_code == 403, f"成员重置被拒 ({r.status_code})")
    # owner 重置 -> 200，新码与旧码不同，旧码失效
    r = client.post("/api/tenants/invite/reset", headers=auth(tok))
    check(r.status_code == 200, f"owner 重置 200 ({r.status_code})")
    new_code = r.json().get("invite_code")
    check(new_code and new_code != invite, f"新码已变 ({invite} -> {new_code})")
    r2 = client.post("/api/auth/register", json={"username": f"kb4_{sfx}", "password": "pass123456"})
    tok4 = client.post("/api/auth/login", json={"username": f"kb4_{sfx}", "password": "pass123456"}).json()["access_token"]
    r = client.post("/api/tenants/join", headers=auth(tok4), json={"invite_code": invite})
    check(r.status_code == 404, f"旧码已失效 ({r.status_code})")
    r = client.post("/api/tenants/join", headers=auth(tok4), json={"invite_code": new_code})
    check(r.status_code == 200, f"新码可用 ({r.status_code})")

    print("\n=== 9c. 同名查重 / 在线编辑 / 版本历史 ===")
    # 同名再传（不覆盖）应 409
    r = client.post(
        "/api/documents",
        headers=auth(tok),
        data={"title": "差旅报销制度"},
        files={"file": ("dup.txt", io.BytesIO(b"x"), "text/plain")},
    )
    check(r.status_code == 409, f"同名上传 409 ({r.status_code})")
    check(r.json().get("detail", {}).get("conflict") is True, "返回冲突标记")
    # 在线编辑正文（改成住宿 500）
    r = client.put(
        f"/api/documents/{doc_id}",
        headers=auth(tok),
        json={"content": "差旅报销制度\n第一条 住宿费：一线城市每晚不超过 500 元。\n"},
    )
    check(r.status_code == 200, f"在线编辑 200 ({r.status_code}) {r.text[:120]}")
    ed = r.json()
    check(ed["revision"] == 2, f"版本号 +1 ({ed['revision']})")
    # 等后台补向量后检索，应命中新内容（500）而非旧内容（600）
    client.post("/api/ai/reindex", headers=auth(tok))
    r = client.post(
        "/api/ai/chat",
        headers=auth(tok),
        json={"question": "一线城市住宿费一晚最多报销多少？", "session_key": f"s3_{sfx}"},
    )
    if r.status_code == 200:
        ans = r.json()["answer"]
        print(f"    A: {ans[:120]}")
        check("500" in ans, "编辑后检索命中新内容 500")
    # 版本历史：应有 1 个历史版本（编辑前的 600 版）
    r = client.get(f"/api/documents/{doc_id}/revisions", headers=auth(tok))
    check(r.status_code == 200 and len(r.json()) >= 1, f"历史版本 {len(r.json()) if r.status_code==200 else '-'} 个")
    rev_id = r.json()[0]["id"]
    # 查看历史版本全文 -> 应为旧内容（600）
    r = client.get(f"/api/documents/{doc_id}/revisions/{rev_id}", headers=auth(tok))
    check(r.status_code == 200 and "600" in r.json()["content"], "历史版本仍可查看旧内容")
    # 回滚到历史版本 -> 内容回到 600
    r = client.post(f"/api/documents/{doc_id}/revisions/{rev_id}/restore", headers=auth(tok))
    check(r.status_code == 200, f"回滚 200 ({r.status_code})")
    r = client.get(f"/api/documents/{doc_id}/content", headers=auth(tok))
    check("600" in r.json()["content"], "回滚后正文为旧内容 600")

    print("\n=== 10. 删除文档 ===")
    r = client.delete(f"/api/documents/{doc_id}", headers=auth(tok))
    check(r.status_code == 204, f"删除 204 ({r.status_code})")
    r = client.get(f"/api/documents/{doc_id}", headers=auth(tok))
    check(r.status_code == 404, "删除后 404")

    print(f"\n===== 结果：{PASSED} passed, {FAILED} failed =====")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
