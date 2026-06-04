
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from interview_agent import server as server_module
from interview_agent.auth import get_current_user
from interview_agent.db import (
    create_message,
    create_session as db_create_session,
    create_user,
    get_session,
    init_db,
    update_session_status,
)
from interview_agent.jd_parser import StructuredJD


@pytest.fixture
def client(isolate_env):
    import anyio

    anyio.run(init_db)
    return TestClient(server_module.app)


@pytest.fixture
def auth_client(client):
    server_module.app.dependency_overrides[get_current_user] = lambda: "tester"
    yield client
    server_module.app.dependency_overrides.pop(get_current_user, None)


def test_register_success(client):
    resp = client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert "interviewlg_token" in resp.cookies


def test_register_short_username(client):
    resp = client.post("/api/auth/register", json={"username": "a", "password": "secret1"})
    assert resp.status_code == 400


def test_register_short_password(client):
    resp = client.post("/api/auth/register", json={"username": "alice", "password": "12"})
    assert resp.status_code == 400


def test_register_invalid_username(client):
    resp = client.post("/api/auth/register", json={"username": "../alice", "password": "secret1"})
    assert resp.status_code == 400


def test_login_success(client):
    client.post("/api/auth/register", json={"username": "bob", "password": "secret1"})
    resp = client.post("/api/auth/login", json={"username": "bob", "password": "secret1"})
    assert resp.status_code == 200
    assert resp.json() == {"username": "bob"}
    assert "interviewlg_token" in resp.cookies


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"username": "carol", "password": "secret1"})
    resp = client.post("/api/auth/login", json={"username": "carol", "password": "wrong"})
    assert resp.status_code == 401


def test_me_authenticated(auth_client):
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json() == {"username": "tester"}


def test_me_unauthenticated(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


def test_list_domains(client):
    resp = client.get("/api/domains")
    assert resp.status_code == 200
    body = resp.json()
    assert "presets" in body
    assert "backend" in body["presets"]
    assert len(body["presets"]) == 8


def test_list_sessions_returns_current_user_summaries(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      other_id = await create_user("other", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "mid")
      await create_message("sid-1", "user", "question content", 0)
      await create_message("sid-1", "ai", "answer content", 1)
      await db_create_session("sid-other", other_id, "other", "frontend", "junior")

    anyio.run(seed)

    resp = auth_client.get("/api/sessions")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sessions"]) == 1
    item = body["sessions"][0]
    assert item["id"] == "sid-1"
    assert item["domain"] == "backend"
    assert item["message_count"] == 2
    assert "question content" not in str(item)


def test_get_session_detail_returns_messages_for_owner(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "mid")
      await create_message("sid-1", "user", "我了解缓存", 0)
      await create_message("sid-1", "ai", "那 Redis 为什么快？", 1)

    anyio.run(seed)

    resp = auth_client.get("/api/sessions/sid-1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["id"] == "sid-1"
    assert [m["role"] for m in body["messages"]] == ["user", "ai"]
    assert body["messages"][0]["content"] == "我了解缓存"


def test_get_session_detail_rejects_other_user_session(auth_client):
    import anyio

    async def seed():
      await create_user("tester", "hash")
      other_id = await create_user("other", "hash")
      await db_create_session("sid-other", other_id, "other", "frontend", "junior")

    anyio.run(seed)

    resp = auth_client.get("/api/sessions/sid-other")

    assert resp.status_code == 404


def test_end_session_marks_completed(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "mid")

    anyio.run(seed)

    resp = auth_client.post("/api/sessions/sid-1/end")

    assert resp.status_code == 200
    row = anyio.run(get_session, "sid-1")
    assert row["status"] == "completed"
    assert row["ended_at"] is not None


def test_pause_session_marks_paused(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "mid")

    anyio.run(seed)

    resp = auth_client.post("/api/sessions/sid-1/pause")

    assert resp.status_code == 200
    row = anyio.run(get_session, "sid-1")
    assert row["status"] == "paused"
    assert row["ended_at"] is None


def test_resume_session_returns_messages(auth_client, monkeypatch):
    import anyio
    from unittest.mock import MagicMock

    async def fake_build(*args, **kwargs):
      return MagicMock()

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "mid", "jd", "profile")
      await update_session_status("sid-1", "paused")
      await create_message("sid-1", "user", "上一轮回答", 0)
      await create_message("sid-1", "ai", "上一轮追问", 1)

    monkeypatch.setattr("interview_agent.session.build_interview_agent", fake_build)
    anyio.run(seed)

    resp = auth_client.post("/api/sessions/sid-1/resume")

    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["status"] == "active"
    assert [m["content"] for m in body["messages"]] == ["上一轮回答", "上一轮追问"]
    row = anyio.run(get_session, "sid-1")
    assert row["status"] == "active"


def test_resume_completed_session_rejected(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "mid")
      await update_session_status("sid-1", "completed")

    anyio.run(seed)

    resp = auth_client.post("/api/sessions/sid-1/resume")

    assert resp.status_code == 409


def test_delete_session_removes_history(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "mid")
      await create_message("sid-1", "user", "delete me", 0)

    anyio.run(seed)

    resp = auth_client.delete("/api/sessions/sid-1")

    assert resp.status_code == 200
    assert anyio.run(get_session, "sid-1") is None


def test_delete_sessions_batch_removes_current_user_history_only(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      other_id = await create_user("other", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "mid")
      await db_create_session("sid-2", user_id, "tester", "frontend", "junior")
      await db_create_session("sid-other", other_id, "other", "backend", "mid")
      await create_message("sid-1", "user", "delete me", 0)

    anyio.run(seed)

    resp = auth_client.request(
        "DELETE",
        "/api/sessions",
        json={"session_ids": ["sid-1", "sid-2", "sid-other"]},
    )

    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2}
    assert anyio.run(get_session, "sid-1") is None
    assert anyio.run(get_session, "sid-2") is None
    assert anyio.run(get_session, "sid-other") is not None


def test_sanitize_path_segment_normal():
    assert server_module._sanitize_path_segment("hello-world") == "hello-world"


def test_sanitize_path_segment_traversal():
    assert server_module._sanitize_path_segment("..") == ""
    assert server_module._sanitize_path_segment("foo/../bar") == ""


def test_sanitize_path_segment_slash():
    assert server_module._sanitize_path_segment("/") == ""
    assert server_module._sanitize_path_segment("a/b") == ""
    assert server_module._sanitize_path_segment("a\\b") == ""


def test_sanitize_path_segment_length():
    out = server_module._sanitize_path_segment("x" * 500)
    assert len(out) == 128


def test_format_jd_full():
    jd = StructuredJD(
        position_title="Backend Engineer",
        required_skills=["Python", "PostgreSQL"],
        required_experience="3+ years",
        key_responsibilities=["Build APIs"],
        preferred_qualifications=["AWS"],
        tech_stack=["FastAPI"],
        interview_focus="system design",
    )
    out = server_module._format_jd(jd)
    assert "Backend Engineer" in out
    assert "Python" in out
    assert "PostgreSQL" in out
    assert "3+ years" in out
    assert "Build APIs" in out
    assert "AWS" in out
    assert "FastAPI" in out
    assert "system design" in out


def test_format_jd_empty():
    jd = StructuredJD()
    assert server_module._format_jd(jd) == ""


def test_format_profile_full():
    data = {
        "company": "Acme",
        "position": "SWE",
        "difficulty_tendency": "senior",
        "focus_areas": ["distributed systems"],
        "interview_style": "deep technical",
        "question_types": ["system design"],
        "key_traits": ["pragmatic"],
        "source_count": 5,
    }
    out = server_module._format_profile(data)
    assert "Acme" in out
    assert "SWE" in out
    assert "高级" in out
    assert "distributed systems" in out
    assert "deep technical" in out
    assert "system design" in out
    assert "pragmatic" in out
    assert "5" in out


def test_format_profile_empty():
    assert server_module._format_profile({}) == ""


class FakeStreamAgent:
    def __init__(self):
        self.last_messages = None

    async def astream_events(self, payload, version):
        self.last_messages = payload["messages"]
        yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content="好的")}}


class FakeSessionManager:
    def __init__(self, agent):
        self.agent = agent
        self.appended = []

    async def get_or_rebuild_agent(self, session_id, username, user_id):
        return FakeSession(self.agent)

    async def append_message(self, session_id, role, content):
        self.appended.append((role, content))

    async def load_messages(self, session_id):
        return [HumanMessage(content="我了解 Redis zset")]


class FakeSession:
    def __init__(self, agent):
        self.agent = agent
        self.domain = "redis"
        self.difficulty = "mid"
        self.username = "tester"


def test_chat_stream_injects_rag_context(auth_client, monkeypatch):
    agent = FakeStreamAgent()
    fake_manager = FakeSessionManager(agent)

    async def fake_get_user(username):
        return {"id": 1, "username": username}

    async def fake_search(query, domain):
        assert domain == "redis"
        return [{"topic": "ZSet", "question": "Zset底层是怎么实现的？", "followups": ["跳表怎么实现？"]}]

    monkeypatch.setattr(server_module, "session_manager", fake_manager)
    monkeypatch.setattr(server_module, "get_user_by_username", fake_get_user)
    monkeypatch.setattr(server_module, "search_interview_cards", fake_search)

    with auth_client.stream("POST", "/api/chat/stream", json={"session_id": "sid", "message": "继续问 Redis"}) as resp:
        body = "".join(resp.iter_text())

    assert resp.status_code == 200
    assert "好的" in body
    assert isinstance(agent.last_messages[-1], SystemMessage)
    assert "真实面试题参考" in agent.last_messages[-1].content
    assert fake_manager.appended[0] == ("user", "继续问 Redis")
    assert fake_manager.appended[-1] == ("ai", "好的")
