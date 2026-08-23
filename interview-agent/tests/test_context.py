from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from interview_agent import context as context_module


async def test_build_agent_input_replaces_context_message_and_appends_rag(monkeypatch):
    async def fake_load_messages(session_id):
        assert session_id == "sid-1"
        return [
            HumanMessage(content="我先自我介绍"),
            AIMessage(content="请讲项目"),
            HumanMessage(content="已提交代码题：反转链表"),
        ]

    async def fake_search(query, domain):
        assert domain == "backend"
        assert "完整代码上下文" in query
        assert "已提交代码题" not in query
        return [{"topic": "链表", "question": "如何反转链表？", "followups": ["递归怎么做？"]}]

    async def fake_load_state(session_id):
        assert session_id == "sid-1"
        return {
            "target": "campus_fulltime",
            "stage": "coding",
            "stage_round": 1,
            "total_round": 3,
            "current_topic": "反转链表",
            "topic_status": "probing",
            "covered_topics": "[]",
            "pending_focus": "边界条件",
            "last_user_quality": "partial",
        }

    async def fake_load_memory_context(session_id):
        assert session_id == "sid-1"
        return "本场面试长期记忆摘要：\n- Redis：缓存穿透掌握较好"

    async def fake_load_user_memory_context(session_id):
        assert session_id == "sid-1"
        return "用户长期面试偏好摘要：\n- 反复薄弱点：边界条件分析不足"

    monkeypatch.setattr(context_module, "search_interview_cards", fake_search)

    agent_input = await context_module.build_agent_input(
        session_id="sid-1",
        domain="backend",
        difficulty="campus_fulltime",
        display_message="已提交代码题：反转链表",
        context_message="完整代码上下文",
        load_messages=fake_load_messages,
        load_state=fake_load_state,
        load_user_memory_context=fake_load_user_memory_context,
        load_memory_context=fake_load_memory_context,
    )

    assert [type(message) for message in agent_input.messages] == [
        HumanMessage,
        AIMessage,
        HumanMessage,
        SystemMessage,
        SystemMessage,
        SystemMessage,
        SystemMessage,
        SystemMessage,
    ]
    assert agent_input.messages[-6].content == "完整代码上下文"
    assert "当前面试状态" in agent_input.messages[-5].content
    assert "用户长期面试偏好摘要" in agent_input.messages[-4].content
    assert "本场面试长期记忆摘要" in agent_input.messages[-3].content
    assert "本轮流程控制" in agent_input.messages[-2].content
    assert "真实面试题参考" in agent_input.messages[-1].content
    assert "边界条件分析不足" in agent_input.user_memory_context
    assert "缓存穿透掌握较好" in agent_input.memory_context
    assert agent_input.running_summary_context == ""
    assert "边界条件" in agent_input.stage_control_context


async def test_build_agent_input_injects_running_summary(monkeypatch):
    async def fake_load_messages(session_id):
        assert session_id == "sid-1"
        return [
            HumanMessage(content="早期问题"),
            AIMessage(content="早期回答"),
            HumanMessage(content="当前问题"),
        ]

    async def fake_summarize_running_context(**kwargs):
        assert kwargs["session_id"] == "sid-1"
        return "本场面试早期对话滚动摘要：\n- 已问过 Redis", [HumanMessage(content="当前问题")]

    async def fake_search(query, domain):
        assert "当前问题" in query
        assert "已问过 Redis" not in query
        return []

    monkeypatch.setattr(context_module, "summarize_running_context", fake_summarize_running_context)
    monkeypatch.setattr(context_module, "search_interview_cards", fake_search)

    agent_input = await context_module.build_agent_input(
        session_id="sid-1",
        domain="backend",
        difficulty="campus_fulltime",
        display_message="当前问题",
        context_message="",
        load_messages=fake_load_messages,
    )

    assert isinstance(agent_input.messages[0], SystemMessage)
    assert "本场面试早期对话滚动摘要" in agent_input.messages[0].content
    assert isinstance(agent_input.messages[1], HumanMessage)
    assert agent_input.messages[1].content == "当前问题"
    assert "已问过 Redis" in agent_input.running_summary_context
