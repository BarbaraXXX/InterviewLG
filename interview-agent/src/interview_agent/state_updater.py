"""Post-turn interview state evaluation and persistence."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from interview_agent.config import llm_settings
from interview_agent.db import get_session_state, update_session_state_control
from interview_agent.memory import summarize_completed_topic

logger = logging.getLogger(__name__)

_VALID_STAGES = {"opening", "project", "technical", "coding", "summary"}
_VALID_TOPIC_STATUSES = {"not_started", "asking", "probing", "completed", "skipped"}
_VALID_QUALITIES = {"unknown", "weak", "partial", "good"}
_MAX_TEXT_CHARS = 4000
_MAX_FIELD_CHARS = 240
_MAX_COVERED_TOPICS = 40

_EVALUATOR_SYSTEM_PROMPT = """你是模拟面试系统的内部状态记录器。
你只负责根据候选人上一轮回答和面试官回复，更新面试状态，不要评价候选人，不要生成给用户看的内容。

必须只输出一个 JSON 对象，字段如下：
{
  "current_topic": "当前正在考查的单一主题，找不到则空字符串",
  "topic_status": "not_started|asking|probing|completed|skipped",
  "answer_quality": "unknown|weak|partial|good",
  "pending_focus": "下一轮如果继续追问，应聚焦的单一缺口，找不到则空字符串",
  "covered_topic": null 或 {"topic":"已完成或跳过的主题","quality":"unknown|weak|partial|good","notes":"一句话记录"},
  "should_change_stage": false,
  "next_stage": null
}

判断规则：
- 如果面试官仍在围绕同一主题追问，topic_status 用 probing。
- 如果候选人已经基本回答清楚，并且面试官自然转向新问题，covered_topic 填写刚完成的主题。
- 不要因为轮数达到某个数字而切阶段；只有回复中已经明确进入新阶段时，should_change_stage 才能为 true。
- 每次只记录一个 current_topic；不要把多个技术点拼成列表。
"""


def _clean_text(value: str, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit]


def _clean_field(value: Any, limit: int = _MAX_FIELD_CHARS) -> str:
    return str(value or "").strip().replace("\n", " ")[:limit]


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


def _load_covered_topics(raw: str) -> list:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _dedupe_append_topic(topics: list, item: dict) -> list:
    topic = _clean_field(item.get("topic"))
    if not topic:
        return topics[:_MAX_COVERED_TOPICS]
    normalized = topic.lower()
    kept = []
    for existing in topics:
        if isinstance(existing, dict):
            existing_topic = _clean_field(existing.get("topic")).lower()
        else:
            existing_topic = _clean_field(existing).lower()
        if existing_topic != normalized:
            kept.append(existing)
    kept.append(
        {
            "topic": topic,
            "stage": _clean_field(item.get("stage")),
            "status": _clean_field(item.get("status")) or "completed",
            "quality": _clean_field(item.get("quality")) or "unknown",
            "notes": _clean_field(item.get("notes"), 360),
        }
    )
    return kept[-_MAX_COVERED_TOPICS:]


def normalize_state_update(raw: dict, state: dict) -> dict:
    topic_status = _clean_field(raw.get("topic_status")) or str(state.get("topic_status") or "not_started")
    if topic_status not in _VALID_TOPIC_STATUSES:
        topic_status = "probing" if state.get("current_topic") else "asking"

    answer_quality = _clean_field(raw.get("answer_quality")) or "unknown"
    if answer_quality not in _VALID_QUALITIES:
        answer_quality = "unknown"

    current_topic = _clean_field(raw.get("current_topic")) or _clean_field(state.get("current_topic"))
    pending_focus = _clean_field(raw.get("pending_focus"), 500)

    should_change_stage = bool(raw.get("should_change_stage"))
    next_stage = _clean_field(raw.get("next_stage"))
    if not should_change_stage or next_stage not in _VALID_STAGES:
        next_stage = None

    covered_topic = raw.get("covered_topic")
    if not isinstance(covered_topic, dict) and topic_status == "completed" and current_topic:
        covered_topic = {
            "topic": current_topic,
            "quality": answer_quality,
            "notes": pending_focus,
            "status": "completed",
        }

    normalized: dict[str, Any] = {
        "stage": next_stage,
        "current_topic": current_topic,
        "topic_status": topic_status,
        "pending_focus": pending_focus,
        "last_user_quality": answer_quality,
        "covered_topic": covered_topic if isinstance(covered_topic, dict) else None,
    }
    return normalized


async def evaluate_turn_state(
    *,
    state: dict,
    user_message: str,
    agent_reply: str,
    answered_stage: str | None = None,
    provider_name: str | None = None,
) -> dict:
    provider = llm_settings.get_provider(provider_name)
    llm = ChatOpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=provider.model,
        temperature=0,
    )
    prompt = "\n\n".join(
        [
            "当前状态：",
            json.dumps(state, ensure_ascii=False),
            f"候选人刚刚回答的问题所属阶段：{answered_stage or state.get('stage') or 'unknown'}",
            "候选人上一轮输入：",
            _clean_text(user_message),
            "面试官刚刚回复：",
            _clean_text(agent_reply),
        ]
    )
    response = await llm.ainvoke([SystemMessage(content=_EVALUATOR_SYSTEM_PROMPT), HumanMessage(content=prompt)])
    content = response.content if isinstance(response.content, str) else ""
    return normalize_state_update(_load_json_object(content), state)


async def apply_state_update(session_id: str, update: dict, *, answered_stage: str | None = None) -> dict | None:
    state = await get_session_state(session_id)
    if state is None:
        return None

    covered_topics = _load_covered_topics(str(state.get("covered_topics") or "[]"))
    if covered_topic := update.get("covered_topic"):
        item = {
            "topic": covered_topic.get("topic"),
            "stage": covered_topic.get("stage") or answered_stage or state.get("stage"),
            "status": covered_topic.get("status") or update.get("topic_status") or "completed",
            "quality": covered_topic.get("quality") or update.get("last_user_quality") or "unknown",
            "notes": covered_topic.get("notes") or update.get("pending_focus") or "",
        }
        covered_topics = _dedupe_append_topic(covered_topics, item)

    topic_status = update.get("topic_status")
    current_topic = update.get("current_topic")
    pending_focus = update.get("pending_focus")
    if topic_status in {"completed", "skipped"}:
        pending_focus = ""

    # New schema-v1 sessions use the persisted Blueprint as the authoritative
    # stage controller. The evaluator still records topic/quality evidence, but
    # cannot move the interview to a different stage on its own. Legacy sessions
    # without a Blueprint retain the previous evaluator-driven transition path.
    evaluated_stage = None if state.get("blueprint_json") else update.get("stage")

    return await update_session_state_control(
        session_id,
        stage=evaluated_stage,
        current_topic=current_topic,
        topic_status=topic_status,
        covered_topics=json.dumps(covered_topics, ensure_ascii=False),
        pending_focus=pending_focus,
        last_user_quality=update.get("last_user_quality"),
    )


async def record_turn_state(
    *,
    session_id: str,
    user_message: str,
    agent_reply: str,
    answered_stage: str | None = None,
    provider_name: str | None = None,
) -> dict | None:
    state = await get_session_state(session_id)
    if state is None:
        return None
    update = await evaluate_turn_state(
        state=state,
        user_message=user_message,
        agent_reply=agent_reply,
        answered_stage=answered_stage,
        provider_name=provider_name,
    )
    updated = await apply_state_update(session_id, update, answered_stage=answered_stage)
    if updated:
        logger.info(
            "interview state updated session=%s stage=%s topic=%s status=%s quality=%s",
            session_id,
            updated.get("stage"),
            updated.get("current_topic"),
            updated.get("topic_status"),
            updated.get("last_user_quality"),
        )
    if covered_topic := update.get("covered_topic"):
        try:
            await summarize_completed_topic(
                session_id=session_id,
                covered_topic=covered_topic,
                provider_name=provider_name,
            )
        except Exception:
            logger.warning("session memory summary failed session=%s", session_id, exc_info=True)
    return updated
