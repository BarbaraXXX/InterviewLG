import pytest
from langchain_core.messages import AIMessage, HumanMessage

from interview_agent import rag as rag_module
from interview_agent.rag import build_rag_query, domain_filter, format_rag_context, search_interview_cards


def test_domain_filter_aliases():
    assert domain_filter("mysql") == ["mysql", "database"]
    assert domain_filter("database") == ["database", "mysql"]
    assert domain_filter("redis") == ["redis"]
    assert domain_filter("unknown") == ["unknown"]


def test_build_rag_query_includes_recent_context():
    query = build_rag_query(
        "redis",
        "mid",
        "我用过 zset",
        [HumanMessage(content="讲讲 Redis"), AIMessage(content="你了解 zset 吗？")],
    )

    assert "redis" in query
    assert "mid" in query
    assert "zset" in query


def test_format_rag_context():
    context = format_rag_context(
        [
            {
                "topic": "ZSet底层实现",
                "question": "Zset底层是怎么实现的？",
                "followups": ["跳表是怎么实现的？", "为什么不用红黑树？"],
            }
        ],
        max_chars=1000,
    )

    assert "真实面试题参考" in context
    assert "ZSet底层实现" in context
    assert "不要逐字照搬" in context


@pytest.mark.asyncio
async def test_search_interview_cards_disabled(monkeypatch):
    monkeypatch.setattr(rag_module.rag_settings, "enabled", False)

    cards = await search_interview_cards("redis", "redis")

    assert cards == []
