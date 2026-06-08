"""Single-session long-term memory summaries."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from interview_agent.config import llm_settings
from interview_agent.db import (
    create_session_memory,
    get_recent_session_messages,
    get_session_memory,
    list_session_memories,
)

logger = logging.getLogger(__name__)

_MEMORY_TYPE_TOPIC_SUMMARY = "topic_summary"
_MAX_MESSAGE_CHARS = 1600
_MAX_SUMMARY_CHARS = 1200
_MAX_TOPIC_CHARS = 160

_TOPIC_SUMMARY_PROMPT = """你是模拟面试系统的长期记忆摘要器。
你只负责总结刚完成或跳过的一个面试主题，不要生成给候选人看的内容。

必须只输出 JSON 对象：
{
  "summary": "一句话总结该主题下候选人的表现",
  "strengths": ["最多3条优势"],
  "weaknesses": ["最多3条不足"],
  "followup_suggestions": ["最多3条后续可追问或复习建议"]
}

要求：
- 聚焦当前 topic，不要总结整场面试。
- 不要记录姓名、联系方式、证件号等敏感个人信息。
- 语言简洁，便于后续直接注入给面试官作为记忆。
"""


def _clean_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _load_json_object(content: str) -> dict:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    parsed = json.loads(stripped)
    return parsed if isinstance(parsed, dict) else {}


def _normalize_summary(raw: dict, *, topic: str, quality: str, notes: str) -> str:
    summary = _clean_text(raw.get("summary") or notes or "该主题已完成考查。", 360)

    def clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        items = [_clean_text(item, 180) for item in value[:3]]
        return [item for item in items if item]

    payload = {
        "topic": _clean_text(topic, _MAX_TOPIC_CHARS),
        "quality": _clean_text(quality, 40) or "unknown",
        "summary": summary,
        "strengths": clean_list(raw.get("strengths")),
        "weaknesses": clean_list(raw.get("weaknesses")),
        "followup_suggestions": clean_list(raw.get("followup_suggestions")),
    }
    return json.dumps(payload, ensure_ascii=False)[:_MAX_SUMMARY_CHARS]


def _format_messages(messages: list[dict]) -> str:
    lines = []
    for message in messages:
        role = "候选人" if message.get("role") == "user" else "面试官"
        content = _clean_text(message.get("content"), _MAX_MESSAGE_CHARS)
        if content:
            lines.append(f"{role}：{content}")
    return "\n\n".join(lines)


def _memory_to_line(memory: dict) -> str:
    topic = _clean_text(memory.get("topic"), _MAX_TOPIC_CHARS)
    raw_summary = str(memory.get("summary") or "")
    try:
        data = json.loads(raw_summary)
    except json.JSONDecodeError:
        return f"- {topic}：{_clean_text(raw_summary, 260)}"
    if not isinstance(data, dict):
        return f"- {topic}：{_clean_text(raw_summary, 260)}"

    summary = _clean_text(data.get("summary"), 260)
    quality = _clean_text(data.get("quality"), 40)
    weaknesses = data.get("weaknesses") if isinstance(data.get("weaknesses"), list) else []
    weakness_text = "；薄弱点：" + "、".join(_clean_text(item, 80) for item in weaknesses[:2] if item) if weaknesses else ""
    quality_text = f"（{quality}）" if quality else ""
    return f"- {topic}{quality_text}：{summary}{weakness_text}"


def format_memory_context(memories: list[dict]) -> str:
    if not memories:
        return ""
    lines = ["本场面试长期记忆摘要："]
    # list_session_memories returns newest first; reverse for a natural timeline.
    lines.extend(_memory_to_line(memory) for memory in reversed(memories))
    lines.append("以上摘要只用于避免重复提问和保持追问连续性，不要直接向候选人复述。")
    return "\n".join(line for line in lines if line.strip())


async def load_memory_context(session_id: str, limit: int = 6) -> str:
    memories = await list_session_memories(session_id, limit=limit, memory_type=_MEMORY_TYPE_TOPIC_SUMMARY)
    return format_memory_context(memories)


async def summarize_completed_topic(
    *,
    session_id: str,
    covered_topic: dict,
    provider_name: str | None = None,
) -> dict | None:
    topic = _clean_text(covered_topic.get("topic"), _MAX_TOPIC_CHARS)
    if not topic:
        return None
    existing = await get_session_memory(session_id, _MEMORY_TYPE_TOPIC_SUMMARY, topic)
    if existing is not None:
        return existing

    messages = await get_recent_session_messages(session_id, limit=12)
    evidence_ids = [message["id"] for message in messages if "id" in message]
    quality = _clean_text(covered_topic.get("quality"), 40) or "unknown"
    notes = _clean_text(covered_topic.get("notes"), 360)
    status = _clean_text(covered_topic.get("status"), 40) or "completed"

    provider = llm_settings.get_provider(provider_name)
    llm = ChatOpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=provider.model,
        temperature=0,
    )
    prompt = "\n\n".join(
        [
            f"主题：{topic}",
            f"主题状态：{status}",
            f"回答质量：{quality}",
            f"状态记录备注：{notes or '暂无'}",
            "最近对话：",
            _format_messages(messages),
        ]
    )
    response = await llm.ainvoke([SystemMessage(content=_TOPIC_SUMMARY_PROMPT), HumanMessage(content=prompt)])
    content = response.content if isinstance(response.content, str) else ""
    summary = _normalize_summary(_load_json_object(content), topic=topic, quality=quality, notes=notes)

    memory = await create_session_memory(
        session_id,
        _MEMORY_TYPE_TOPIC_SUMMARY,
        topic,
        summary,
        json.dumps(evidence_ids, ensure_ascii=False),
    )
    if memory:
        logger.info("session memory created session=%s topic=%s type=%s", session_id, topic, _MEMORY_TYPE_TOPIC_SUMMARY)
    return memory
