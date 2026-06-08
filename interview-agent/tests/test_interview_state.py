from interview_agent.db import (
    advance_session_state,
    create_session,
    create_user,
    get_session_state,
    init_db,
    set_session_state_stage,
)
from interview_agent.interview_state import format_state_context


async def test_session_state_created_with_session(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")

    await create_session("sid-state", user_id, "alice", "backend", "campus_intern")

    state = await get_session_state("sid-state")
    assert state is not None
    assert state["target"] == "campus_intern"
    assert state["stage"] == "opening"
    assert state["stage_round"] == 0
    assert state["total_round"] == 0
    assert state["current_topic"] == ""
    assert state["topic_status"] == "not_started"


async def test_advance_session_state_moves_opening_to_project(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-state", user_id, "alice", "backend", "campus_fulltime")

    state = await advance_session_state("sid-state", "campus_fulltime")

    assert state["stage"] == "project"
    assert state["stage_round"] == 1
    assert state["total_round"] == 1


async def test_coding_stage_stays_for_submission_then_returns_to_technical(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-state", user_id, "alice", "backend", "campus_fulltime")
    await set_session_state_stage("sid-state", "coding")

    submitted = await advance_session_state("sid-state", "campus_fulltime", is_coding_submission=True)
    assert submitted["stage"] == "coding"
    assert submitted["stage_round"] == 1

    next_turn = await advance_session_state("sid-state", "campus_fulltime")
    assert next_turn["stage"] == "technical"
    assert next_turn["stage_round"] == 1


def test_format_state_context():
    context = format_state_context(
        {
            "target": "campus_fulltime",
            "stage": "project",
            "stage_round": 2,
            "total_round": 4,
            "current_topic": "LangGraph 架构",
            "topic_status": "probing",
            "covered_topics": '[{"topic": "Redis", "quality": "good"}, "MySQL"]',
            "pending_focus": "继续项目深挖",
            "last_user_quality": "partial",
        }
    )

    assert "当前面试状态" in context
    assert "校招正式岗" in context
    assert "项目深挖" in context
    assert "LangGraph 架构" in context
    assert "追问中" in context
    assert "Redis(good)、MySQL" in context
    assert "不要直接向候选人复述" in context
