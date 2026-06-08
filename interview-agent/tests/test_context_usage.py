from langchain_core.messages import HumanMessage

from interview_agent.context_usage import build_context_usage, count_text_tokens


def test_count_text_tokens_estimates_non_empty_text():
    assert count_text_tokens("你好，Redis 缓存一致性") > 0


def test_build_context_usage_sections_and_status():
    usage = build_context_usage(
        system_prompt="你是面试官",
        messages=[HumanMessage(content="请解释 LangGraph 状态管理")],
        state_context="当前阶段：技术追问",
        user_memory_context="用户长期面试偏好摘要",
        session_memory_context="本场面试长期记忆摘要",
        stage_control_context="每轮只问一个问题",
        rag_context="真实面试题参考",
    )

    assert usage["total_tokens"] > 0
    assert usage["input_budget_tokens"] > 0
    assert usage["status"] in {"normal", "warning", "critical"}
    assert usage["is_estimate"] is True
    section_keys = {section["key"] for section in usage["sections"]}
    assert {"system_prompt", "messages", "state", "user_memory", "session_memory", "stage_control", "rag"} <= section_keys
