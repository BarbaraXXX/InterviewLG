"""Token usage estimation for assembled interview context."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import tiktoken
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from interview_agent.config import context_settings

_MESSAGE_OVERHEAD_TOKENS = 6
_SECTION_LABELS = {
    "system_prompt": "固定规则",
    "messages": "短期对话",
    "state": "当前状态",
    "user_memory": "用户记忆",
    "session_memory": "本场摘要",
    "stage_control": "流程控制",
    "rag": "RAG参考",
}


@dataclass(frozen=True)
class UsageSection:
    key: str
    label: str
    tokens: int


@lru_cache(maxsize=8)
def _encoding(name: str):
    try:
        return tiktoken.get_encoding(name)
    except ValueError:
        return tiktoken.get_encoding("cl100k_base")


def count_text_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoding(context_settings.tokenizer_encoding).encode(text))


def _role_name(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, SystemMessage):
        return "system"
    return getattr(message, "type", "message")


def count_message_tokens(message: BaseMessage) -> int:
    content = message.content if isinstance(message.content, str) else str(message.content)
    return count_text_tokens(_role_name(message)) + count_text_tokens(content) + _MESSAGE_OVERHEAD_TOKENS


def count_messages_tokens(messages: list[BaseMessage]) -> int:
    return sum(count_message_tokens(message) for message in messages)


def _conversation_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    return [message for message in messages if not isinstance(message, SystemMessage)]


def _status_for_ratio(ratio: float) -> str:
    if ratio >= 0.9:
        return "critical"
    if ratio >= 0.7:
        return "warning"
    return "normal"


def _section(key: str, tokens: int) -> UsageSection:
    return UsageSection(key=key, label=_SECTION_LABELS.get(key, key), tokens=max(tokens, 0))


def build_context_usage(
    *,
    system_prompt: str = "",
    messages: list[BaseMessage] | None = None,
    state_context: str = "",
    user_memory_context: str = "",
    session_memory_context: str = "",
    stage_control_context: str = "",
    rag_context: str = "",
) -> dict[str, Any]:
    conversation = _conversation_messages(messages or [])
    sections = [
        _section("system_prompt", count_text_tokens(system_prompt)),
        _section("messages", count_messages_tokens(conversation)),
        _section("state", count_text_tokens(state_context)),
        _section("user_memory", count_text_tokens(user_memory_context)),
        _section("session_memory", count_text_tokens(session_memory_context)),
        _section("stage_control", count_text_tokens(stage_control_context)),
        _section("rag", count_text_tokens(rag_context)),
    ]
    total = sum(section.tokens for section in sections)
    input_budget = min(
        context_settings.input_budget_tokens,
        max(context_settings.window_tokens - context_settings.output_reserve_tokens, 1),
    )
    ratio = total / input_budget if input_budget else 0.0
    return {
        "total_tokens": total,
        "input_budget_tokens": input_budget,
        "context_window_tokens": context_settings.window_tokens,
        "output_reserve_tokens": context_settings.output_reserve_tokens,
        "ratio": ratio,
        "status": _status_for_ratio(ratio),
        "tokenizer": context_settings.tokenizer_encoding,
        "is_estimate": True,
        "sections": [
            {
                "key": section.key,
                "label": section.label,
                "tokens": section.tokens,
                "ratio": section.tokens / input_budget if input_budget else 0.0,
            }
            for section in sections
        ],
    }


def compact_usage_for_log(usage: dict[str, Any]) -> str:
    parts = []
    for section in usage.get("sections", []):
        tokens = int(section.get("tokens") or 0)
        if tokens:
            parts.append(f"{section.get('key')}={tokens}")
    return " ".join(parts)
