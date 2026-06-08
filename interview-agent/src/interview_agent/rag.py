from __future__ import annotations

import logging

import httpx
from langchain_core.messages import BaseMessage

from interview_agent.config import rag_settings, vectordb_settings

logger = logging.getLogger(__name__)


def domain_filter(domain: str) -> list[str]:
    value = domain.strip().lower()
    if not value:
        return []
    aliases = {
        "database": ["database", "mysql"],
        "mysql": ["mysql", "database"],
        "network": ["network"],
        "redis": ["redis"],
        "backend": ["backend"],
        "frontend": ["frontend"],
        "algorithm": ["algorithm"],
        "cpp": ["cpp"],
        "agent": ["agent"],
        "rag": ["rag"],
        "llm": ["llm"],
    }
    return aliases.get(value, [value])


def build_rag_query(domain: str, difficulty: str, user_message: str, messages: list[BaseMessage]) -> str:
    recent_parts: list[str] = []
    for message in messages[-4:]:
        content = message.content if isinstance(message.content, str) else ""
        if content:
            recent_parts.append(content[:500])
    parts = [
        f"面试方向：{domain}",
        f"目标岗位：{difficulty}",
        "最近对话：",
        "\n".join(recent_parts),
        f"当前用户回答：{user_message[:1000]}",
    ]
    return "\n".join(part for part in parts if part.strip())


async def search_interview_cards(query: str, domain: str) -> list[dict]:
    if not rag_settings.enabled:
        return []
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(rag_settings.timeout_seconds, connect=min(rag_settings.timeout_seconds, 2.0)),
            follow_redirects=False,
        ) as client:
            resp = await client.post(
                f"{vectordb_settings.base_url}/api/question-cards/search",
                json={
                    "query": query,
                    "domain": domain_filter(domain),
                    "top_k": rag_settings.top_k,
                    "min_score": rag_settings.min_score,
                },
            )
            if resp.status_code != 200:
                logger.warning("rag search failed status=%d body=%s", resp.status_code, resp.text[:300])
                return []
            payload = resp.json()
            cards = payload.get("cards", [])
            return cards if isinstance(cards, list) else []
    except Exception:
        logger.warning("rag search request failed", exc_info=True)
        return []


def format_rag_context(cards: list[dict], max_chars: int | None = None) -> str:
    if not cards:
        return ""
    limit = max_chars or rag_settings.max_context_chars
    lines = [
        "以下是真实面试题参考。请只参考其提问方式、知识点覆盖和追问角度，不要逐字照搬；如果与当前面试流程无关，请忽略。",
    ]
    for idx, card in enumerate(cards, start=1):
        topic = str(card.get("topic", ""))[:120]
        question = str(card.get("question", ""))[:300]
        followups = [str(item)[:180] for item in (card.get("followups") or [])[:3]]
        lines.append(f"{idx}. topic: {topic}")
        lines.append(f"   question: {question}")
        if followups:
            lines.append(f"   followups: {'；'.join(followups)}")
    context = "\n".join(lines).strip()
    return context[:limit]
