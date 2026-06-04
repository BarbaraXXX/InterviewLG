from unittest.mock import MagicMock

import pytest

from interview_agent.db import (
    create_message,
    create_session,
    create_user,
    expire_stale_sessions,
    get_db,
    get_next_message_seq,
    get_session,
    get_session_messages,
    init_db,
    list_user_sessions,
)
from interview_agent.session import SessionManager


@pytest.fixture
def mock_agent_build(monkeypatch):
    calls = []

    async def fake_build(*args, **kwargs):
        calls.append((args, kwargs))
        return MagicMock()

    monkeypatch.setattr("interview_agent.session.build_interview_agent", fake_build)
    return calls


async def _make_user(username: str) -> int:
    return await create_user(username, "hash")


async def test_session_manager_create(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", user_id)
    assert isinstance(sid, str)
    assert sid in mgr._agents
    row = await get_session(sid)
    assert row is not None
    assert row["username"] == "alice"


async def test_session_manager_get_agent(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", user_id)
    got = mgr.get_agent(sid, "alice")
    assert got is not None
    assert got.username == "alice"


async def test_session_manager_get_wrong_user(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", user_id)
    assert mgr.get_agent(sid, "bob") is None


async def test_session_manager_rebuild_from_db(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", user_id, "jd", "profile")
    mgr._agents.clear()

    rebuilt = await mgr.get_or_rebuild_agent(sid, "alice", user_id)
    assert rebuilt is not None
    assert rebuilt.domain == "backend"
    assert rebuilt.difficulty == "mid"
    assert sid in mgr._agents
    assert mock_agent_build[-1][0] == ("backend", "mid", "jd", "profile")


async def test_session_manager_rebuild_wrong_user_denied(mock_agent_build, isolate_env):
    await init_db()
    alice_id = await _make_user("alice")
    bob_id = await _make_user("bob")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", alice_id)
    mgr._agents.clear()

    assert await mgr.get_or_rebuild_agent(sid, "bob", bob_id) is None


async def test_session_manager_delete(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", user_id)
    assert await mgr.delete(sid, "alice", user_id) is True
    assert mgr.get_agent(sid, "alice") is None
    assert await get_session(sid) is None


async def test_session_manager_delete_wrong_user(mock_agent_build, isolate_env):
    await init_db()
    alice_id = await _make_user("alice")
    bob_id = await _make_user("bob")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", alice_id)
    assert await mgr.delete(sid, "bob", bob_id) is False
    assert mgr.get_agent(sid, "alice") is not None
    assert await get_session(sid) is not None


async def test_session_manager_pause_and_resume(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", user_id, "jd", "profile")

    await mgr.pause_session(sid)
    paused = await get_session(sid)
    assert paused["status"] == "paused"
    assert mgr.get_agent(sid, "alice") is None
    assert await mgr.get_or_rebuild_agent(sid, "alice", user_id) is None

    resumed = await mgr.resume_session(sid, "alice", user_id)
    assert resumed is not None
    assert resumed.domain == "backend"
    assert resumed.difficulty == "mid"
    assert sid in mgr._agents
    row = await get_session(sid)
    assert row["status"] == "active"
    assert mock_agent_build[-1][0] == ("backend", "mid", "jd", "profile")


async def test_session_manager_trims_user_sessions(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    created = []
    for i in range(55):
        sid = await mgr.create("backend", "mid", "alice", user_id)
        created.append(sid)

    rows = await list_user_sessions(user_id, 100)
    ids = {row["id"] for row in rows}
    assert len(rows) == 50
    assert created[-1] in ids
    assert created[0] not in ids
    assert created[0] not in mgr._agents


async def test_session_manager_keeps_sessions_before_retention_trigger(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    for _ in range(54):
        await mgr.create("backend", "mid", "alice", user_id)

    rows = await list_user_sessions(user_id, 100)

    assert len(rows) == 54


async def test_session_manager_max_agents(mock_agent_build, isolate_env):
    from interview_agent import session as session_module

    await init_db()
    mgr = SessionManager()
    created_ids = []
    for i in range(session_module._MAX_AGENTS + 1):
        user_id = await _make_user(f"u{i}")
        sid = await mgr.create("backend", "mid", f"u{i}", user_id)
        created_ids.append(sid)
    assert created_ids[0] not in mgr._agents
    assert created_ids[-1] in mgr._agents
    assert len(mgr._agents) == session_module._MAX_AGENTS


async def test_append_message_uses_monotonic_seq_after_trim(mock_agent_build, isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    mgr = SessionManager()
    sid = await mgr.create("backend", "mid", "alice", user_id)

    for i in range(205):
        await mgr.append_message(sid, "user", f"m{i}")

    rows = await get_session_messages(sid, 500)
    assert len(rows) == 200
    assert rows[0]["content"] == "m5"
    assert rows[-1]["seq"] == 204
    assert await get_next_message_seq(sid) == 205


async def test_expire_stale_sessions_keeps_history(isolate_env):
    await init_db()
    user_id = await _make_user("alice")
    await create_session("old-session", user_id, "alice", "backend", "mid")
    await create_message("old-session", "user", "hello", 0)
    await create_message("old-session", "ai", "hi", 1)

    db = await get_db()
    try:
        await db.execute(
            "UPDATE sessions SET created_at = datetime('now', '-2 hours') WHERE id = ?",
            ("old-session",),
        )
        await db.commit()
    finally:
        await db.close()

    expired = await expire_stale_sessions()

    assert expired == 1
    row = await get_session("old-session")
    assert row is not None
    assert row["status"] == "expired"
    messages = await get_session_messages("old-session")
    assert [m["content"] for m in messages] == ["hello", "hi"]
