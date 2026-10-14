"""微信扫码登录：三种模式（real / mp / mock）的路由与状态机测试。

不依赖真实微信凭据——mp 分支用 monkeypatch 替掉微信网络调用，
只验证「分支判定正确 + 状态机正确 + 错误可读」。
"""
from datetime import datetime, timedelta

from app.config import settings
from app.database import SessionLocal
from app.models import WxLoginState


def _as_mock(monkeypatch):
    monkeypatch.setattr(settings, "wechat_app_id", "")
    monkeypatch.setattr(settings, "wechat_app_secret", "")
    monkeypatch.setattr(settings, "wx_mp_app_id", "")
    monkeypatch.setattr(settings, "wx_mp_app_secret", "")


def _as_mp(monkeypatch, qr_bytes=b"\x89PNG\r\n\x1a\nfake", openid="o_mp_test_0001"):
    monkeypatch.setattr(settings, "wechat_app_id", "")
    monkeypatch.setattr(settings, "wechat_app_secret", "")
    monkeypatch.setattr(settings, "wx_mp_app_id", "wx_test_appid")
    monkeypatch.setattr(settings, "wx_mp_app_secret", "test_secret")

    from app import wechat_service

    monkeypatch.setattr(wechat_service, "fetch_mp_qrcode_png", lambda db, scene: qr_bytes)
    monkeypatch.setattr(
        wechat_service, "exchange_code_for_openid_mp", lambda code: {"openid": openid}
    )


# ---------------------------------------------------------------- 模式判定
def test_mode_priority(monkeypatch):
    """优先级必须是 real > mp > mock。"""
    _as_mock(monkeypatch)
    assert settings.wechat_mode == "mock"

    monkeypatch.setattr(settings, "wx_mp_app_id", "wx_a")
    monkeypatch.setattr(settings, "wx_mp_app_secret", "s")
    assert settings.wechat_mode == "mp"

    monkeypatch.setattr(settings, "wechat_app_id", "wx_b")
    monkeypatch.setattr(settings, "wechat_app_secret", "s")
    assert settings.wechat_mode == "real"


# ---------------------------------------------------------------- 未配置：零回归
def test_qrcode_stays_mock_when_unconfigured(client, monkeypatch):
    """没配任何凭据时必须仍走 Mock，不能因为本次改动把老功能弄坏。"""
    _as_mock(monkeypatch)
    r = client.get("/api/auth/wx/qrcode")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "mock"
    assert body["qr"].startswith("data:image/png;base64,")
    assert body["state"]


def test_mp_bind_404_when_unconfigured(client, monkeypatch):
    """没配小程序时，绑定接口必须 404，不能被外人当免费接口打。"""
    _as_mock(monkeypatch)
    r = client.post("/api/auth/wx/mp/bind", json={"state": "a" * 32, "code": "b" * 16})
    assert r.status_code == 404


# ---------------------------------------------------------------- Mock 全链路
def test_mock_login_flow(client, monkeypatch):
    _as_mock(monkeypatch)
    state = client.get("/api/auth/wx/qrcode").json()["state"]

    assert client.get("/api/auth/wx/mock/confirm", params={"state": state}).status_code == 200

    polled = client.get("/api/auth/wx/poll", params={"state": state}).json()
    assert polled["status"] == "confirmed"
    assert polled["token"]
    assert polled["user"]["username"]

    # 票据一次性消费，防重放
    again = client.get("/api/auth/wx/poll", params={"state": state}).json()
    assert not again.get("token")


def test_poll_unknown_state_is_expired(client):
    r = client.get("/api/auth/wx/poll", params={"state": "nope" * 10}).json()
    assert r["status"] == "expired"


# ---------------------------------------------------------------- 小程序 mp 分支
def test_mp_qrcode_returns_data_url(client, monkeypatch):
    _as_mp(monkeypatch)
    r = client.get("/api/auth/wx/qrcode")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "mp"
    assert body["qr"].startswith("data:image/png;base64,")
    # ticket 直接作为 state，且长度必须卡在微信 scene 的 32 字符上限内
    assert body["state"]
    assert len(body["state"]) <= 32


def test_mp_ticket_is_unique(client, monkeypatch):
    """scene 重复会导致两个用户登录到同一个账号，必须保证唯一。"""
    _as_mp(monkeypatch)
    states = {client.get("/api/auth/wx/qrcode").json()["state"] for _ in range(20)}
    assert len(states) == 20


def test_mp_bind_completes_login(client, monkeypatch):
    """小程序回传 ticket + code → 网页轮询应拿到 token。"""
    _as_mp(monkeypatch, openid="o_mp_flow_test")
    state = client.get("/api/auth/wx/qrcode").json()["state"]

    r = client.post("/api/auth/wx/mp/bind", json={"state": state, "code": "c" * 20})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    polled = client.get("/api/auth/wx/poll", params={"state": state}).json()
    assert polled["status"] == "confirmed"
    assert polled["token"]
    assert polled["user"]["username"]

    # 同一 openid 再登录一次，不应新建用户
    state2 = client.get("/api/auth/wx/qrcode").json()["state"]
    first = client.post("/api/auth/wx/mp/bind", json={"state": state2, "code": "c" * 20})
    assert first.status_code == 200
    uid1 = client.get("/api/auth/wx/poll", params={"state": state2}).json()["user"]["id"]

    state3 = client.get("/api/auth/wx/qrcode").json()["state"]
    client.post("/api/auth/wx/mp/bind", json={"state": state3, "code": "c" * 20})
    uid2 = client.get("/api/auth/wx/poll", params={"state": state3}).json()["user"]["id"]
    assert uid1 == uid2, "同一个微信 openid 必须映射到同一个账号"


def test_mp_bind_is_idempotent(client, monkeypatch):
    """小程序端因网络抖动重试同一次请求，不应报错、也不应重复建档。"""
    _as_mp(monkeypatch, openid="o_mp_idem")
    state = client.get("/api/auth/wx/qrcode").json()["state"]
    body = {"state": state, "code": "c" * 20}

    assert client.post("/api/auth/wx/mp/bind", json=body).status_code == 200
    r2 = client.post("/api/auth/wx/mp/bind", json=body)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("already") is True


def test_mp_bind_rejects_unknown_ticket(client, monkeypatch):
    _as_mp(monkeypatch)
    r = client.post("/api/auth/wx/mp/bind", json={"state": "z" * 32, "code": "c" * 20})
    assert r.status_code == 400
    assert "失效" in r.text or "不存在" in r.text


def test_mp_bind_rejects_wrong_mode(client, monkeypatch):
    """拿 Mock 模式的票据去打小程序接口，必须被拒。"""
    _as_mock(monkeypatch)
    state = client.get("/api/auth/wx/qrcode").json()["state"]  # mode=mock
    _as_mp(monkeypatch)
    r = client.post("/api/auth/wx/mp/bind", json={"state": state, "code": "c" * 20})
    assert r.status_code == 400


def test_mp_bind_rejects_expired_ticket(client, monkeypatch):
    """过期票据必须拒绝，否则二维码可以无限期复用。"""
    _as_mp(monkeypatch)
    state = client.get("/api/auth/wx/qrcode").json()["state"]

    db = SessionLocal()
    try:
        row = db.query(WxLoginState).filter(WxLoginState.state == state).one()
        row.created_at = datetime.now() - timedelta(seconds=settings.wx_state_ttl_seconds + 60)
        db.commit()
    finally:
        db.close()

    r = client.post("/api/auth/wx/mp/bind", json={"state": state, "code": "c" * 20})
    assert r.status_code == 400
    assert "过期" in r.text or "失效" in r.text


def test_mp_bind_rejects_bad_wechat_response(client, monkeypatch):
    """微信拒绝授权（errcode）时应返回 400 且带上错误码，不能 500。"""
    _as_mp(monkeypatch)
    from app import wechat_service

    monkeypatch.setattr(
        wechat_service,
        "exchange_code_for_openid_mp",
        lambda code: {"errcode": 40029, "errmsg": "invalid code"},
    )
    state = client.get("/api/auth/wx/qrcode").json()["state"]
    r = client.post("/api/auth/wx/mp/bind", json={"state": state, "code": "c" * 20})
    assert r.status_code == 400
    assert "40029" in r.text


def test_mp_bind_validates_payload(client, monkeypatch):
    _as_mp(monkeypatch)
    assert client.post("/api/auth/wx/mp/bind", json={"state": "a" * 32, "code": "x"}).status_code == 422
    assert client.post("/api/auth/wx/mp/bind", json={"code": "c" * 20}).status_code == 422
