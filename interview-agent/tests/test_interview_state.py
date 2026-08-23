import json

from interview_agent.db import (
    advance_session_state,
    create_session,
    create_user,
    get_session_blueprint,
    get_session_state,
    init_db,
    set_session_state_stage,
    update_session_state_control,
)
from interview_agent.interview_blueprint import build_interview_blueprint
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
    assert json.loads(state["stage_goal_status"]) == {
        "opening": "active",
        "project": "pending",
        "technical": "pending",
        "coding": "pending",
        "summary": "pending",
    }


async def test_advance_session_state_moves_opening_to_project(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-state", user_id, "alice", "backend", "campus_fulltime")

    state = await advance_session_state("sid-state", "campus_fulltime")

    assert state["stage"] == "project"
    assert state["stage_round"] == 1
    assert state["total_round"] == 1
    assert json.loads(state["stage_goal_status"])["opening"] == "completed"
    assert json.loads(state["stage_goal_status"])["project"] == "active"


async def test_blueprint_is_persisted_with_session_and_exposed_through_state(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    blueprint = build_interview_blueprint(
        question_tier="deep",
        intensity="pressure",
        focus_areas=["system_design", "communication"],
    )

    await create_session(
        "sid-blueprint",
        user_id,
        "alice",
        "backend",
        "campus_fulltime",
        blueprint=blueprint,
    )

    assert await get_session_blueprint("sid-blueprint") == blueprint
    state = await get_session_state("sid-blueprint")
    assert state is not None
    assert json.loads(state["blueprint_json"]) == blueprint


async def test_standard_blueprint_advances_by_question_budget(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    blueprint = build_interview_blueprint(question_tier="standard")
    await create_session(
        "sid-blueprint",
        user_id,
        "alice",
        "backend",
        "campus_fulltime",
        blueprint=blueprint,
    )

    stages = []
    for _ in range(10):
        state = await advance_session_state("sid-blueprint", "campus_fulltime")
        stages.append(state["stage"])

    assert stages == [
        "project",
        "project",
        "project",
        "technical",
        "technical",
        "technical",
        "technical",
        "coding",
        "coding",
        "summary",
    ]
    assert json.loads(state["stage_goal_status"]) == {
        "opening": "completed",
        "project": "completed",
        "technical": "completed",
        "coding": "completed",
        "summary": "active",
    }


async def test_blueprint_stage_round_counts_completed_questions_in_current_stage(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session(
        "sid-blueprint",
        user_id,
        "alice",
        "backend",
        "campus_fulltime",
        blueprint=build_interview_blueprint(question_tier="standard"),
    )

    first_project_question = await advance_session_state("sid-blueprint", "campus_fulltime")
    second_project_question = await advance_session_state("sid-blueprint", "campus_fulltime")

    assert first_project_question["stage"] == "project"
    assert first_project_question["stage_round"] == 0
    assert second_project_question["stage_round"] == 1


async def test_compact_blueprint_skips_coding_stage(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    blueprint = build_interview_blueprint(question_tier="compact")
    await create_session(
        "sid-blueprint",
        user_id,
        "alice",
        "backend",
        "campus_fulltime",
        blueprint=blueprint,
    )

    initial = await get_session_state("sid-blueprint")
    assert json.loads(initial["stage_goal_status"])["coding"] == "skipped"

    stages = [
        (await advance_session_state("sid-blueprint", "campus_fulltime"))["stage"]
        for _ in range(6)
    ]
    assert stages == ["project", "project", "technical", "technical", "technical", "summary"]


async def test_blueprint_submission_that_exhausts_budget_enters_summary(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    blueprint = build_interview_blueprint(question_tier="standard")
    await create_session(
        "sid-blueprint",
        user_id,
        "alice",
        "backend",
        "campus_fulltime",
        blueprint=blueprint,
    )
    for _ in range(9):
        await advance_session_state("sid-blueprint", "campus_fulltime")

    submitted = await advance_session_state(
        "sid-blueprint",
        "campus_fulltime",
        is_coding_submission=True,
    )
    assert submitted["stage"] == "summary"
    assert submitted["answered_questions"] == 10


async def test_active_coding_clarification_does_not_consume_question_budget(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session(
        "sid-blueprint",
        user_id,
        "alice",
        "backend",
        "campus_fulltime",
        blueprint=build_interview_blueprint(question_tier="standard"),
    )
    for _ in range(8):
        await advance_session_state("sid-blueprint", "campus_fulltime")

    clarification = await advance_session_state(
        "sid-blueprint",
        "campus_fulltime",
        has_active_coding_task=True,
    )

    assert clarification["stage"] == "coding"
    assert clarification["total_round"] == 9
    assert clarification["answered_questions"] == 8


async def test_coding_stage_stays_for_submission_then_returns_to_interrupted_stage(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-state", user_id, "alice", "backend", "campus_fulltime")
    await advance_session_state("sid-state", "campus_fulltime")
    await set_session_state_stage("sid-state", "coding")

    submitted = await advance_session_state("sid-state", "campus_fulltime", is_coding_submission=True)
    assert submitted["stage"] == "coding"
    assert submitted["stage_round"] == 1

    next_turn = await advance_session_state("sid-state", "campus_fulltime")
    assert next_turn["stage"] == "project"
    assert next_turn["stage_round"] == 1
    assert json.loads(next_turn["stage_goal_status"])["coding"] == "completed"
    assert json.loads(next_turn["stage_goal_status"])["project"] == "active"


async def test_coding_stage_returns_to_summary_after_completed_technical_stage(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-state", user_id, "alice", "backend", "campus_fulltime")

    await advance_session_state("sid-state", "campus_fulltime")
    await update_session_state_control("sid-state", stage="technical", topic_status="completed")
    await set_session_state_stage("sid-state", "coding")

    submitted = await advance_session_state("sid-state", "campus_fulltime", is_coding_submission=True)
    assert submitted["stage"] == "coding"

    next_turn = await advance_session_state("sid-state", "campus_fulltime")
    assert next_turn["stage"] == "summary"
    assert json.loads(next_turn["stage_goal_status"])["technical"] == "completed"
    assert json.loads(next_turn["stage_goal_status"])["summary"] == "active"


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
    assert "阶段计划" in context
    assert "不要直接向候选人复述" in context
