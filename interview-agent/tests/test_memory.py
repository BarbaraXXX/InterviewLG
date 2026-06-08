import json

from langchain_core.messages import AIMessage, HumanMessage

from interview_agent.db import (
    create_message,
    create_session,
    create_session_memory,
    create_user,
    get_session_memory,
    get_user_memory,
    init_db,
    list_session_memories,
)
from interview_agent.memory import (
    format_memory_context,
    format_user_memory_context,
    load_user_memory_context,
    summarize_completed_topic,
    summarize_running_context,
    summarize_user_interview_preference,
)


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


class FakeUserMemoryResponse:
    content = json.dumps(
        {
            "summary": "用户对 Agent 项目链路较熟，但工程边界分析需要继续观察。",
            "strengths": ["能结合项目说明 Agent 流程"],
            "recurring_weaknesses": ["边界条件分析不够完整"],
            "interview_style_suggestions": ["适合先项目追问，再单点追问异常处理"],
        },
        ensure_ascii=False,
    )


class FakeUserMemoryLLM:
    calls = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def ainvoke(self, messages):
        FakeUserMemoryLLM.calls += 1
        return FakeUserMemoryResponse()


class FakeRunningSummaryResponse:
    content = json.dumps(
        {
            "summary": "候选人介绍了早期项目背景，并回答了缓存相关问题。",
            "important_facts": ["项目涉及 Redis 缓存"],
            "covered_topics": ["缓存穿透"],
            "open_threads": ["后续继续观察边界条件"],
        },
        ensure_ascii=False,
    )


class FakeRunningSummaryLLM:
    calls = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def ainvoke(self, messages):
        FakeRunningSummaryLLM.calls += 1
        return FakeRunningSummaryResponse()


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


async def test_summarize_user_interview_preference_upserts_memory(isolate_env, monkeypatch):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-memory", user_id, "alice", "backend", "campus_fulltime")
    await create_session_memory(
        "sid-memory",
        "topic_summary",
        "Agent 状态管理",
        json.dumps(
            {
                "topic": "Agent 状态管理",
                "quality": "partial",
                "summary": "能说明基础链路，但边界条件分析不足。",
                "weaknesses": ["边界条件分析不够完整"],
            },
            ensure_ascii=False,
        ),
        "[1, 2]",
    )
    FakeUserMemoryLLM.calls = 0
    monkeypatch.setattr("interview_agent.memory.ChatOpenAI", FakeUserMemoryLLM)

    memory = await summarize_user_interview_preference(user_id=user_id, session_id="sid-memory")

    assert memory is not None
    assert FakeUserMemoryLLM.calls == 1
    assert memory["source_session_id"] == "sid-memory"
    stored = await get_user_memory(user_id, "interview_preference", "default")
    assert stored is not None
    summary = json.loads(stored["summary"])
    assert "Agent 项目链路" in summary["summary"]
    assert "边界条件分析不够完整" in summary["recurring_weaknesses"]


async def test_summarize_user_interview_preference_skips_without_session_memory(isolate_env, monkeypatch):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-empty", user_id, "alice", "backend", "campus_fulltime")
    FakeUserMemoryLLM.calls = 0
    monkeypatch.setattr("interview_agent.memory.ChatOpenAI", FakeUserMemoryLLM)

    memory = await summarize_user_interview_preference(user_id=user_id, session_id="sid-empty")

    assert memory is None
    assert FakeUserMemoryLLM.calls == 0


async def test_load_user_memory_context(isolate_env):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-memory", user_id, "alice", "backend", "campus_fulltime")
    await create_session_memory("sid-memory", "topic_summary", "占位", "{}", "[]")
    from interview_agent.db import upsert_user_memory

    await upsert_user_memory(
        user_id,
        "interview_preference",
        "default",
        json.dumps(
            {
                "summary": "用户项目表达较清楚。",
                "strengths": ["项目表达清晰"],
                "recurring_weaknesses": ["复杂边界条件不足"],
                "interview_style_suggestions": ["适合做单点追问"],
            },
            ensure_ascii=False,
        ),
        source_session_id="sid-memory",
    )

    context = await load_user_memory_context(user_id)

    assert context == format_user_memory_context(await get_user_memory(user_id, "interview_preference", "default"))
    assert "用户长期面试偏好摘要" in context
    assert "复杂边界条件不足" in context
    assert "不要直接向候选人复述" in context


async def test_summarize_running_context_keeps_recent_messages(isolate_env, monkeypatch):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-running", user_id, "alice", "backend", "campus_fulltime")
    messages = [
        HumanMessage(content="我做过 Redis 项目。" * 60),
        AIMessage(content="请解释缓存穿透。" * 60),
        HumanMessage(content="缓存穿透可以用布隆过滤器处理。" * 60),
        AIMessage(content="我们继续看边界条件。"),
    ]
    FakeRunningSummaryLLM.calls = 0
    monkeypatch.setattr("interview_agent.memory.ChatOpenAI", FakeRunningSummaryLLM)

    context, recent = await summarize_running_context(
        session_id="sid-running",
        messages=messages,
        trigger_tokens=10,
        keep_tokens=80,
        max_summary_tokens=300,
    )

    assert FakeRunningSummaryLLM.calls == 1
    assert "本场面试早期对话滚动摘要" in context
    assert 0 < len(recent) < len(messages)
    stored = await get_session_memory("sid-running", "running_summary", "__session__")
    assert stored is not None
    assert "缓存" in stored["summary"]
