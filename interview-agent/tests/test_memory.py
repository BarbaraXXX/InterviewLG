import json

from interview_agent.db import create_message, create_session, create_user, init_db, list_session_memories
from interview_agent.memory import format_memory_context, summarize_completed_topic


class FakeSummaryResponse:
    content = json.dumps(
        {
            "summary": "候选人能说明 LangGraph 基本状态传递，但 reducer 机制解释不完整。",
            "strengths": ["能描述 StateGraph 基本流程"],
            "weaknesses": ["reducer 机制不清楚"],
            "followup_suggestions": ["后续结合项目追问状态合并"],
        },
        ensure_ascii=False,
    )


class FakeSummaryLLM:
    calls = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def ainvoke(self, messages):
        FakeSummaryLLM.calls += 1
        return FakeSummaryResponse()


async def test_summarize_completed_topic_creates_memory_once(isolate_env, monkeypatch):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-memory", user_id, "alice", "backend", "campus_fulltime")
    await create_message("sid-memory", "user", "LangGraph 的状态会在节点间传递", 0)
    await create_message("sid-memory", "ai", "这里 reducer 机制还可以补充。", 1)
    FakeSummaryLLM.calls = 0
    monkeypatch.setattr("interview_agent.memory.ChatOpenAI", FakeSummaryLLM)

    first = await summarize_completed_topic(
        session_id="sid-memory",
        covered_topic={
            "topic": "LangGraph 状态管理",
            "quality": "partial",
            "notes": "reducer 机制解释不足",
        },
    )
    second = await summarize_completed_topic(
        session_id="sid-memory",
        covered_topic={
            "topic": "LangGraph 状态管理",
            "quality": "good",
            "notes": "重复完成不应再次摘要",
        },
    )

    assert first is not None
    assert second is not None
    assert first["id"] == second["id"]
    assert FakeSummaryLLM.calls == 1
    memories = await list_session_memories("sid-memory")
    assert len(memories) == 1
    summary = json.loads(memories[0]["summary"])
    assert summary["topic"] == "LangGraph 状态管理"
    assert "reducer" in " ".join(summary["weaknesses"])
    assert json.loads(memories[0]["evidence_message_ids"]) == [1, 2]


def test_format_memory_context():
    context = format_memory_context(
        [
            {
                "topic": "Redis 缓存一致性",
                "summary": json.dumps(
                    {
                        "quality": "partial",
                        "summary": "知道缓存穿透，但雪崩治理解释较浅。",
                        "weaknesses": ["雪崩治理不完整"],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )

    assert "本场面试长期记忆摘要" in context
    assert "Redis 缓存一致性" in context
    assert "雪崩治理不完整" in context
    assert "不要直接向候选人复述" in context
