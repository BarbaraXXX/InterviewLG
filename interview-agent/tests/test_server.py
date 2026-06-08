
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from interview_agent import context as context_module
from interview_agent import server as server_module
from interview_agent.auth import get_current_user
from interview_agent.db import (
    create_coding_task,
    create_message,
    create_resume as db_create_resume,
    create_session as db_create_session,
    create_user,
    get_session,
    init_db,
    update_session_status,
)
from interview_agent.jd_parser import StructuredJD


RESUME_PROJECTS = [{"name": "订单系统", "description": "负责缓存和接口设计"}]


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


def test_resume_crud(auth_client):
    import anyio

    async def seed():
        await create_user("tester", "hash")

    anyio.run(seed)

    created = auth_client.post(
        "/api/resumes",
        json={"title": "后端实习版", "projects": RESUME_PROJECTS, "skills": "Python, Redis"},
    )
    assert created.status_code == 200
    resume = created.json()["resume"]
    assert resume["title"] == "后端实习版"
    assert resume["projects"] == RESUME_PROJECTS

    listed = auth_client.get("/api/resumes")
    assert listed.status_code == 200
    assert [item["title"] for item in listed.json()["resumes"]] == ["后端实习版"]

    updated = auth_client.put(
        f"/api/resumes/{resume['id']}",
        json={
            "title": "后端正式版",
            "projects": [{"name": "支付系统", "description": "负责支付回调和幂等处理"}],
            "skills": "FastAPI",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["resume"]["projects"][0]["name"] == "支付系统"

    deleted = auth_client.delete(f"/api/resumes/{resume['id']}")
    assert deleted.status_code == 200
    assert auth_client.get("/api/resumes").json()["resumes"] == []


def test_resume_create_limit(auth_client):
    import anyio

    async def seed():
        await create_user("tester", "hash")

    anyio.run(seed)

    for i in range(3):
        resp = auth_client.post(
            "/api/resumes",
            json={"title": f"简历{i}", "projects": [{"name": f"项目{i}", "description": "项目描述"}], "skills": ""},
        )
        assert resp.status_code == 200

    resp = auth_client.post(
        "/api/resumes",
        json={"title": "第四份", "projects": [{"name": "超出限制", "description": "项目描述"}], "skills": ""},
    )
    assert resp.status_code == 409


def test_resume_validation(auth_client):
    import anyio

    async def seed():
        await create_user("tester", "hash")

    anyio.run(seed)

    missing_title = auth_client.post("/api/resumes", json={"title": "", "projects": RESUME_PROJECTS, "skills": ""})
    assert missing_title.status_code == 400

    missing_projects = auth_client.post("/api/resumes", json={"title": "空简历", "projects": [], "skills": "Python"})
    assert missing_projects.status_code == 400

    missing_project_description = auth_client.post(
        "/api/resumes",
        json={"title": "项目不完整", "projects": [{"name": "订单系统", "description": ""}], "skills": ""},
    )
    assert missing_project_description.status_code == 400


def test_resume_rejects_other_user_operations(auth_client):
    import anyio

    async def seed():
        await create_user("tester", "hash")
        other_id = await create_user("other", "hash")
        return await db_create_resume(other_id, "其他用户简历", "项目", "技能")

    other_resume = anyio.run(seed)

    update_resp = auth_client.put(
        f"/api/resumes/{other_resume['id']}",
        json={"title": "非法修改", "projects": RESUME_PROJECTS, "skills": ""},
    )
    assert update_resp.status_code == 404

    delete_resp = auth_client.delete(f"/api/resumes/{other_resume['id']}")
    assert delete_resp.status_code == 404


def test_create_session_with_resume_snapshot(auth_client, monkeypatch):
    import anyio

    class FakeSessionManager:
        async def create(
            self,
            domain,
            difficulty,
            username,
            user_id,
            structured_jd="",
            structured_profile="",
            resume_title_snapshot="",
        ):
            await db_create_session(
                "sid-resume",
                user_id,
                username,
                domain,
                difficulty,
                structured_jd,
                structured_profile,
                resume_title_snapshot,
            )
            return "sid-resume"

    async def seed():
        user_id = await create_user("tester", "hash")
        return await db_create_resume(
            user_id,
            "后端项目版",
            json.dumps(RESUME_PROJECTS, ensure_ascii=False),
            "Python, Redis",
        )

    resume = anyio.run(seed)
    monkeypatch.setattr(server_module, "session_manager", FakeSessionManager())

    resp = auth_client.post(
        "/api/sessions",
        json={"domain": "backend", "difficulty": "campus_fulltime", "resume_id": resume["id"]},
    )

    assert resp.status_code == 200
    row = anyio.run(get_session, "sid-resume")
    assert row["resume_title_snapshot"] == "后端项目版"
    assert "候选人简历上下文" in row["structured_profile"]
    assert "订单系统" in row["structured_profile"]
    assert "项目名称" in row["structured_profile"]


def test_last_interview_config_empty(auth_client):
    import anyio

    async def seed():
        await create_user("tester", "hash")

    anyio.run(seed)

    resp = auth_client.get("/api/interview-config/last")

    assert resp.status_code == 200
    assert resp.json() == {"config": None}


def test_create_session_saves_last_interview_config(auth_client, monkeypatch):
    import anyio

    class FakeSessionManager:
        def __init__(self):
            self.count = 0

        async def create(
            self,
            domain,
            difficulty,
            username,
            user_id,
            structured_jd="",
            structured_profile="",
            resume_title_snapshot="",
        ):
            self.count += 1
            session_id = f"sid-config-{self.count}"
            await db_create_session(
                session_id,
                user_id,
                username,
                domain,
                difficulty,
                structured_jd,
                structured_profile,
                resume_title_snapshot,
            )
            return session_id

    async def seed():
        user_id = await create_user("tester", "hash")
        return await db_create_resume(
            user_id,
            "后端项目版",
            json.dumps(RESUME_PROJECTS, ensure_ascii=False),
            "Python, Redis",
        )

    resume = anyio.run(seed)
    monkeypatch.setattr(server_module, "session_manager", FakeSessionManager())

    first = auth_client.post(
        "/api/sessions",
        json={
            "domain": "backend",
            "difficulty": "campus_fulltime",
            "job_description": "后端开发 JD",
            "profile_company": "Acme",
            "profile_position": "Backend Engineer",
            "resume_id": resume["id"],
        },
    )
    assert first.status_code == 200

    second = auth_client.post(
        "/api/sessions",
        json={"domain": "frontend", "difficulty": "campus_intern"},
    )
    assert second.status_code == 200

    resp = auth_client.get("/api/interview-config/last")

    assert resp.status_code == 200
    config = resp.json()["config"]
    assert config["domain"] == "frontend"
    assert config["difficulty"] == "campus_intern"
    assert config["job_description"] == ""
    assert config["profile_company"] == ""
    assert config["resume_id"] is None


def test_list_sessions_returns_current_user_summaries(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      other_id = await create_user("other", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "campus_fulltime")
      await create_message("sid-1", "user", "question content", 0)
      await create_message("sid-1", "ai", "answer content", 1)
      await db_create_session("sid-other", other_id, "other", "frontend", "campus_intern")

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
      await db_create_session("sid-1", user_id, "tester", "backend", "campus_fulltime")
      await create_message("sid-1", "user", "我了解缓存", 0)
      await create_message("sid-1", "ai", "那 Redis 为什么快？", 1)

    anyio.run(seed)

    resp = auth_client.get("/api/sessions/sid-1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["id"] == "sid-1"
    assert [m["role"] for m in body["messages"]] == ["user", "ai"]
    assert body["messages"][0]["content"] == "我了解缓存"
    assert body["coding_tasks"] == []


def test_coding_task_active_and_submit(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-code", user_id, "tester", "backend", "campus_fulltime")
      return await create_coding_task(
          "task-1",
          "sid-code",
          "两数之和",
          "给定数组和目标值，返回两个数的下标。",
          "python",
          "class Solution:\n    pass",
          json.dumps(["只需要返回任意一种答案"], ensure_ascii=False),
          json.dumps([{"input": "nums=[2,7], target=9", "output": "[0,1]"}], ensure_ascii=False),
      )

    anyio.run(seed)

    active = auth_client.get("/api/sessions/sid-code/coding-task/active")
    assert active.status_code == 200
    task = active.json()["task"]
    assert task["title"] == "两数之和"
    assert task["constraints"] == ["只需要返回任意一种答案"]
    assert task["examples"][0]["output"] == "[0,1]"

    draft = auth_client.put(
        "/api/coding-tasks/task-1/draft",
        json={"language": "python", "code": "class Solution:\n    def twoSum(self, nums, target):\n        pass"},
    )
    assert draft.status_code == 200
    assert draft.json()["task"]["draft_code"].endswith("pass")

    active_after_draft = auth_client.get("/api/sessions/sid-code/coding-task/active")
    assert active_after_draft.status_code == 200
    assert active_after_draft.json()["task"]["draft_language"] == "python"
    assert active_after_draft.json()["task"]["draft_code"].endswith("pass")

    submitted = auth_client.post(
        "/api/coding-tasks/task-1/submit",
        json={"language": "python", "code": "class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]"},
    )
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["task"]["status"] == "submitted"
    assert "用户提交了一道手撕代码题答案" in body["context_message"]
    assert "twoSum" in body["context_message"]

    repeat = auth_client.post(
        "/api/coding-tasks/task-1/submit",
        json={"language": "python", "code": "print('again')"},
    )
    assert repeat.status_code == 409

    draft_after_submit = auth_client.put(
        "/api/coding-tasks/task-1/draft",
        json={"language": "python", "code": "print('late draft')"},
    )
    assert draft_after_submit.status_code == 409

    active_after_submit = auth_client.get("/api/sessions/sid-code/coding-task/active")
    assert active_after_submit.status_code == 200
    assert active_after_submit.json()["task"] is None


def test_coding_task_rejects_other_user(auth_client):
    import anyio

    async def seed():
      await create_user("tester", "hash")
      other_id = await create_user("other", "hash")
      await db_create_session("sid-other", other_id, "other", "backend", "campus_fulltime")
      await create_coding_task("task-other", "sid-other", "反转链表", "反转链表。", "java", "", "[]", "[]")

    anyio.run(seed)

    resp = auth_client.post(
        "/api/coding-tasks/task-other/submit",
        json={"language": "java", "code": "class Solution {}"},
    )

    assert resp.status_code == 404


def test_get_session_detail_rejects_other_user_session(auth_client):
    import anyio

    async def seed():
      await create_user("tester", "hash")
      other_id = await create_user("other", "hash")
      await db_create_session("sid-other", other_id, "other", "frontend", "campus_intern")

    anyio.run(seed)

    resp = auth_client.get("/api/sessions/sid-other")

    assert resp.status_code == 404


def test_end_session_marks_completed(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "campus_fulltime")

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
      await db_create_session("sid-1", user_id, "tester", "backend", "campus_fulltime")

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
      await db_create_session("sid-1", user_id, "tester", "backend", "campus_fulltime", "jd", "profile")
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
      await db_create_session("sid-1", user_id, "tester", "backend", "campus_fulltime")
      await update_session_status("sid-1", "completed")

    anyio.run(seed)

    resp = auth_client.post("/api/sessions/sid-1/resume")

    assert resp.status_code == 409


def test_delete_session_removes_history(auth_client):
    import anyio

    async def seed():
      user_id = await create_user("tester", "hash")
      await db_create_session("sid-1", user_id, "tester", "backend", "campus_fulltime")
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
      await db_create_session("sid-1", user_id, "tester", "backend", "campus_fulltime")
      await db_create_session("sid-2", user_id, "tester", "frontend", "campus_intern")
      await db_create_session("sid-other", other_id, "other", "backend", "campus_fulltime")
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
        "difficulty_tendency": "campus_fulltime",
        "focus_areas": ["distributed systems"],
        "interview_style": "deep technical",
        "question_types": ["system design"],
        "key_traits": ["pragmatic"],
        "source_count": 5,
    }
    out = server_module._format_profile(data)
    assert "Acme" in out
    assert "SWE" in out
    assert "校招正式岗" in out
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
        self.difficulty = "campus_fulltime"
        self.username = "tester"


def test_chat_stream_injects_rag_context(auth_client, monkeypatch):
    agent = FakeStreamAgent()
    fake_manager = FakeSessionManager(agent)

    async def fake_get_user(username):
        return {"id": 1, "username": username}

    async def fake_search(query, domain):
        assert domain == "redis"
        return [{"topic": "ZSet", "question": "Zset底层是怎么实现的？", "followups": ["跳表怎么实现？"]}]

    async def fake_advance(*args, **kwargs):
        return {}

    async def fake_record_turn_state(*args, **kwargs):
        return {}

    monkeypatch.setattr(server_module, "session_manager", fake_manager)
    monkeypatch.setattr(server_module, "get_user_by_username", fake_get_user)
    monkeypatch.setattr(server_module, "advance_session_state", fake_advance)
    monkeypatch.setattr(server_module, "record_turn_state", fake_record_turn_state)
    monkeypatch.setattr(context_module, "search_interview_cards", fake_search)

    with auth_client.stream("POST", "/api/chat/stream", json={"session_id": "sid", "message": "继续问 Redis"}) as resp:
        body = "".join(resp.iter_text())

    assert resp.status_code == 200
    assert "好的" in body
    assert isinstance(agent.last_messages[-1], SystemMessage)
    assert "真实面试题参考" in agent.last_messages[-1].content
    assert fake_manager.appended[0] == ("user", "继续问 Redis")
    assert fake_manager.appended[-1] == ("ai", "好的")


def test_chat_stream_uses_context_message_for_agent(auth_client, monkeypatch):
    agent = FakeStreamAgent()
    fake_manager = FakeSessionManager(agent)

    async def fake_get_user(username):
        return {"id": 1, "username": username}

    async def fake_search(query, domain):
        assert "完整代码上下文" in query
        return []

    async def fake_advance(*args, **kwargs):
        return {}

    async def fake_record_turn_state(*args, **kwargs):
        return {}

    monkeypatch.setattr(server_module, "session_manager", fake_manager)
    monkeypatch.setattr(server_module, "get_user_by_username", fake_get_user)
    monkeypatch.setattr(server_module, "advance_session_state", fake_advance)
    monkeypatch.setattr(server_module, "record_turn_state", fake_record_turn_state)
    monkeypatch.setattr(context_module, "search_interview_cards", fake_search)

    with auth_client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": "sid", "message": "已提交代码题：两数之和", "context_message": "完整代码上下文"},
    ) as resp:
        body = "".join(resp.iter_text())

    assert resp.status_code == 200
    assert "好的" in body
    assert isinstance(agent.last_messages[-1], HumanMessage)
    assert agent.last_messages[-1].content == "完整代码上下文"
    assert fake_manager.appended[0] == ("user", "已提交代码题：两数之和")
