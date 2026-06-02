
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from interview_agent import server as server_module
from interview_agent.auth import get_current_user
from interview_agent.db import init_db
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
