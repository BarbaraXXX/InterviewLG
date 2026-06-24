import anyio
import bcrypt
import pytest
from fastapi.testclient import TestClient

from interview_agent import admin_cli
from interview_agent import server as server_module
from interview_agent.admin_auth import create_admin_user
from interview_agent.auth import get_current_user
from interview_agent.db import (
    create_session,
    create_user,
    get_presence_for_user,
    get_usage_count,
    increment_usage_metric,
    init_db,
    list_recent_presence,
)


async def _seed_user(username: str = "tester") -> dict:
    password_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt(rounds=12)).decode()
    await create_user(username, password_hash)
    from interview_agent.db import get_user_by_username

    user = await get_user_by_username(username)
    assert user is not None
    return user


async def _seed_admin(username: str = "ops") -> None:
    await create_admin_user(username, "admin-secret")


def _client() -> TestClient:
    anyio.run(init_db)
    return TestClient(server_module.app)


def test_admin_login_sets_independent_cookie_and_me(isolate_env):
    client = _client()
    anyio.run(_seed_admin)

    login_resp = client.post("/api/admin/auth/login", json={"username": "ops", "password": "admin-secret"})
    assert login_resp.status_code == 200
    assert login_resp.json() == {"username": "ops"}
    assert "interviewlg_admin_token" in login_resp.cookies
    assert "interviewlg_token" not in login_resp.cookies

    me_resp = client.get("/api/admin/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json() == {"username": "ops"}


def test_admin_cli_reports_validation_errors_without_traceback(isolate_env, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["interview-agent-admin", "create-user", "ops"])
    monkeypatch.setattr(admin_cli.getpass, "getpass", lambda prompt: "short")

    exit_code = admin_cli.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Invalid admin password" in captured.err
    assert "Traceback" not in captured.err


async def test_lifespan_rejects_default_admin_secret(isolate_env, monkeypatch):
    monkeypatch.setattr(server_module.admin_auth_settings, "secret_key", "change-me-admin-production")

    with pytest.raises(RuntimeError, match="ADMIN_AUTH_SECRET_KEY"):
        async with server_module._lifespan(server_module.app):
            pass


def test_regular_user_cookie_cannot_access_admin_metrics(isolate_env):
    client = _client()
    anyio.run(_seed_user, "alice")
    login = client.post("/api/auth/login", json={"username": "alice", "password": "secret123"})
    assert login.status_code == 200

    resp = client.get("/api/admin/metrics/overview")
    assert resp.status_code == 401


def test_presence_heartbeat_updates_low_sensitivity_status(isolate_env):
    client = _client()
    user = anyio.run(_seed_user)
    server_module.app.dependency_overrides[get_current_user] = lambda: "tester"
    try:
        resp = client.post(
            "/api/presence/heartbeat",
            json={"current_view": "chat", "active_session_id": "sid-1"},
        )
    finally:
        server_module.app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    presence = anyio.run(get_presence_for_user, user["id"])
    assert presence is not None
    assert presence["username"] == "tester"
    assert presence["current_view"] == "chat"
    assert presence["active_session_id"] == "sid-1"

    recent = anyio.run(list_recent_presence)
    assert len(recent) == 1
    assert recent[0]["status"] == "online"


def test_usage_metrics_are_aggregated_without_user_detail(isolate_env):
    anyio.run(init_db)
    anyio.run(increment_usage_metric, "chat_turn")
    anyio.run(increment_usage_metric, "chat_turn")
    anyio.run(increment_usage_metric, "speech_transcribed")

    assert anyio.run(get_usage_count, "chat_turn") == 2
    assert anyio.run(get_usage_count, "speech_transcribed") == 1


def test_admin_metrics_return_overview_presence_and_daily_usage(isolate_env):
    client = _client()

    async def seed():
        user = await _seed_user("barbara")
        await create_session("sid-active", user["id"], "barbara", "backend", "campus_fulltime")
        await increment_usage_metric("session_created")
        await increment_usage_metric("chat_turn")
        await _seed_admin("ops")
        return user

    anyio.run(seed)
    server_module.app.dependency_overrides[get_current_user] = lambda: "barbara"
    try:
        client.post("/api/presence/heartbeat", json={"current_view": "chat", "active_session_id": "sid-active"})
    finally:
        server_module.app.dependency_overrides.pop(get_current_user, None)

    login_resp = client.post("/api/admin/auth/login", json={"username": "ops", "password": "admin-secret"})
    assert login_resp.status_code == 200

    overview = client.get("/api/admin/metrics/overview")
    assert overview.status_code == 200
    overview_body = overview.json()
    assert overview_body["online_users"] == 1
    assert overview_body["active_sessions"] == 1
    assert overview_body["today"]["session_created"] == 1
    assert overview_body["today"]["chat_turn"] == 1

    presence = client.get("/api/admin/presence")
    assert presence.status_code == 200
    presence_body = presence.json()
    assert presence_body["users"][0]["username"] == "barbara"
    assert "password_hash" not in presence_body["users"][0]

    usage = client.get("/api/admin/usage/daily?days=7")
    assert usage.status_code == 200
    usage_body = usage.json()
    assert len(usage_body["days"]) >= 1
    assert "session_created" in usage_body["days"][-1]["metrics"]
