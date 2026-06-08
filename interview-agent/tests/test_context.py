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

    monkeypatch.setattr(context_module, "search_interview_cards", fake_search)

    agent_input = await context_module.build_agent_input(
        session_id="sid-1",
        domain="backend",
        difficulty="campus_fulltime",
        display_message="已提交代码题：反转链表",
        context_message="完整代码上下文",
        load_messages=fake_load_messages,
    )

    assert [type(message) for message in agent_input.messages] == [
        HumanMessage,
        AIMessage,
        HumanMessage,
        SystemMessage,
    ]
    assert agent_input.messages[-2].content == "完整代码上下文"
    assert "真实面试题参考" in agent_input.messages[-1].content
