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
    get_user_memory,
    list_session_memories,
    upsert_user_memory,
)

logger = logging.getLogger(__name__)

_MEMORY_TYPE_TOPIC_SUMMARY = "topic_summary"
_MEMORY_TYPE_USER_PREFERENCE = "interview_preference"
_USER_MEMORY_KEY_DEFAULT = "default"
_MAX_MESSAGE_CHARS = 1600
_MAX_SUMMARY_CHARS = 1200
_MAX_USER_MEMORY_CHARS = 1800
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

_USER_MEMORY_PROMPT = """你是模拟面试系统的用户级长期记忆维护器。
你只负责把本场面试摘要合并进用户长期面试偏好，不要生成给用户看的内容。

必须只输出 JSON 对象：
{
  "summary": "一句话概括用户跨面试的表现特征",
  "strengths": ["最多4条稳定优势"],
  "recurring_weaknesses": ["最多4条反复薄弱点"],
  "interview_style_suggestions": ["最多4条后续面试追问风格建议"]
}

要求：
- 只保留和技术面试表现、追问节奏、复习方向有关的信息。
- 不要记录姓名、联系方式、证件号、精确公司隐私、住址等敏感个人信息。
- 不要保存大段原文，不要把单场偶然表现夸大成稳定结论。
- 如果证据不足，用谨慎措辞，例如“目前看起来”“可继续观察”。
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


def _normalize_user_memory(raw: dict, *, previous_summary: str, session_context: str) -> str:
    fallback = "用户长期面试偏好仍需更多面试数据观察。"
    if previous_summary:
        try:
            previous = json.loads(previous_summary)
            if isinstance(previous, dict):
                fallback = _clean_text(previous.get("summary"), 360) or fallback
        except json.JSONDecodeError:
            fallback = _clean_text(previous_summary, 360) or fallback
    elif session_context:
        fallback = "已根据最近一次面试生成初步表现画像，后续仍需更多面试验证。"

    def clean_list(value: Any, limit: int = 4) -> list[str]:
        if not isinstance(value, list):
            return []
        items = [_clean_text(item, 180) for item in value[:limit]]
        return [item for item in items if item]

    payload = {
        "summary": _clean_text(raw.get("summary") or fallback, 420),
        "strengths": clean_list(raw.get("strengths")),
        "recurring_weaknesses": clean_list(raw.get("recurring_weaknesses")),
        "interview_style_suggestions": clean_list(raw.get("interview_style_suggestions")),
    }
    return json.dumps(payload, ensure_ascii=False)[:_MAX_USER_MEMORY_CHARS]


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


def _user_memory_to_lines(memory: dict) -> list[str]:
    raw_summary = str(memory.get("summary") or "")
    try:
        data = json.loads(raw_summary)
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    summary = _clean_text(data.get("summary") or raw_summary, 360)
    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    weaknesses = data.get("recurring_weaknesses") if isinstance(data.get("recurring_weaknesses"), list) else []
    suggestions = (
        data.get("interview_style_suggestions") if isinstance(data.get("interview_style_suggestions"), list) else []
    )
    lines = ["用户长期面试偏好摘要："]
    if summary:
        lines.append(f"- 概况：{summary}")
    if strengths:
        lines.append("- 历史优势：" + "、".join(_clean_text(item, 90) for item in strengths[:3] if item))
    if weaknesses:
        lines.append("- 反复薄弱点：" + "、".join(_clean_text(item, 90) for item in weaknesses[:3] if item))
    if suggestions:
        lines.append("- 追问建议：" + "、".join(_clean_text(item, 90) for item in suggestions[:3] if item))
    lines.append("以上信息只用于调整追问方式和复习建议，不要直接向候选人复述。")
    return [line for line in lines if line.strip()]


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


def format_user_memory_context(memory: dict | None) -> str:
    if memory is None:
        return ""
    return "\n".join(_user_memory_to_lines(memory))


async def load_user_memory_context(user_id: int) -> str:
    memory = await get_user_memory(user_id, _MEMORY_TYPE_USER_PREFERENCE, _USER_MEMORY_KEY_DEFAULT)
    return format_user_memory_context(memory)


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


def _format_topic_memories_for_user_update(memories: list[dict]) -> str:
    lines = []
    for memory in reversed(memories):
        topic = _clean_text(memory.get("topic"), _MAX_TOPIC_CHARS)
        raw_summary = str(memory.get("summary") or "")
        try:
            data = json.loads(raw_summary)
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        summary = _clean_text(data.get("summary") or raw_summary, 320)
        quality = _clean_text(data.get("quality"), 40)
        weaknesses = data.get("weaknesses") if isinstance(data.get("weaknesses"), list) else []
        weakness_text = "；不足：" + "、".join(_clean_text(item, 90) for item in weaknesses[:2] if item) if weaknesses else ""
        if topic or summary:
            quality_text = f"({quality})" if quality else ""
            lines.append(f"- {topic}{quality_text}：{summary}{weakness_text}")
    return "\n".join(lines)


async def summarize_user_interview_preference(
    *,
    user_id: int,
    session_id: str,
    provider_name: str | None = None,
) -> dict | None:
    topic_memories = await list_session_memories(session_id, limit=20, memory_type=_MEMORY_TYPE_TOPIC_SUMMARY)
    if not topic_memories:
        return None

    existing = await get_user_memory(user_id, _MEMORY_TYPE_USER_PREFERENCE, _USER_MEMORY_KEY_DEFAULT)
    previous_summary = existing["summary"] if existing else ""
    session_context = _format_topic_memories_for_user_update(topic_memories)
    if not session_context:
        return existing

    provider = llm_settings.get_provider(provider_name)
    llm = ChatOpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=provider.model,
        temperature=0,
    )
    prompt = "\n\n".join(
        [
            "已有用户长期记忆：",
            previous_summary or "暂无",
            "本场面试 topic 摘要：",
            session_context,
        ]
    )
    response = await llm.ainvoke([SystemMessage(content=_USER_MEMORY_PROMPT), HumanMessage(content=prompt)])
    content = response.content if isinstance(response.content, str) else ""
    summary = _normalize_user_memory(_load_json_object(content), previous_summary=previous_summary, session_context=session_context)
    memory = await upsert_user_memory(
        user_id,
        _MEMORY_TYPE_USER_PREFERENCE,
        _USER_MEMORY_KEY_DEFAULT,
        summary,
        source_session_id=session_id,
    )
    if memory:
        logger.info("user memory updated user_id=%s type=%s session=%s", user_id, _MEMORY_TYPE_USER_PREFERENCE, session_id)
    return memory
