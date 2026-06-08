import json

from interview_agent.db import create_session, create_user, get_session_state, init_db, update_session_state_control
from interview_agent.state_updater import apply_state_update, normalize_state_update


async def test_apply_state_update_records_completed_topic(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-state", user_id, "alice", "backend", "campus_fulltime")
    await update_session_state_control(
        "sid-state",
        stage="technical",
        current_topic="LangGraph 状态管理",
        topic_status="probing",
        pending_focus="状态合并",
        last_user_quality="partial",
    )

    updated = await apply_state_update(
        "sid-state",
        {
            "current_topic": "LangGraph 状态管理",
            "topic_status": "completed",
            "pending_focus": "候选人已能说明节点间状态传递",
            "last_user_quality": "good",
            "covered_topic": {
                "topic": "LangGraph 状态管理",
                "quality": "good",
                "notes": "能说明 StateGraph 的状态传递",
            },
        },
    )

    assert updated is not None
    assert updated["topic_status"] == "completed"
    assert updated["pending_focus"] == ""
    covered = json.loads(updated["covered_topics"])
    assert covered == [
        {
            "topic": "LangGraph 状态管理",
            "stage": "technical",
            "status": "completed",
            "quality": "good",
            "notes": "能说明 StateGraph 的状态传递",
        }
    ]


async def test_apply_state_update_dedupes_covered_topic(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-state", user_id, "alice", "backend", "campus_fulltime")
    payload = {
        "current_topic": "Redis 跳表",
        "topic_status": "completed",
        "last_user_quality": "partial",
        "covered_topic": {"topic": "Redis 跳表", "quality": "partial", "notes": "第一次记录"},
    }

    await apply_state_update("sid-state", payload)
    await apply_state_update(
        "sid-state",
        {
            **payload,
            "covered_topic": {"topic": "Redis 跳表", "quality": "good", "notes": "更新记录"},
        },
    )

    state = await get_session_state("sid-state")
    covered = json.loads(state["covered_topics"])
    assert len(covered) == 1
    assert covered[0]["quality"] == "good"
    assert covered[0]["notes"] == "更新记录"


def test_normalize_state_update_rejects_invalid_values():
    state = {
        "stage": "technical",
        "current_topic": "RAG 检索",
        "topic_status": "probing",
    }

    update = normalize_state_update(
        {
            "current_topic": "RAG 检索",
            "topic_status": "bad-status",
            "answer_quality": "excellent",
            "should_change_stage": True,
            "next_stage": "bad-stage",
        },
        state,
    )

    assert update["topic_status"] == "probing"
    assert update["last_user_quality"] == "unknown"
    assert update["stage"] is None
