from __future__ import annotations

import logging
from typing import Any

import httpx

from interview_agent.config import rag_settings, vectordb_settings

logger = logging.getLogger(__name__)


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(rag_settings.timeout_seconds, connect=min(rag_settings.timeout_seconds, 2.0))


async def search_coding_problems(
    *,
    query: str,
    difficulty: list[str] | None = None,
    importance: list[str] | None = None,
    answer_mode: list[str] | None = None,
    topics: list[str] | None = None,
    exclude_ids: list[str] | None = None,
    top_k: int = 5,
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=_timeout(), follow_redirects=False) as client:
            resp = await client.post(
                f"{vectordb_settings.base_url}/api/coding-problems/search",
                json={
                    "query": query,
                    "difficulty": difficulty or [],
                    "importance": importance or [],
                    "answer_mode": answer_mode or [],
                    "topics": topics or [],
                    "exclude_ids": exclude_ids or [],
                    "top_k": top_k,
                    "min_score": min_score,
                },
            )
            if resp.status_code != 200:
                logger.warning("coding problem search failed status=%d body=%s", resp.status_code, resp.text[:300])
                return []
            payload = resp.json()
            problems = payload.get("problems", [])
            return problems if isinstance(problems, list) else []
    except Exception:
        logger.warning("coding problem search request failed", exc_info=True)
        return []


async def get_coding_problem(problem_id: str) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=_timeout(), follow_redirects=False) as client:
            resp = await client.get(f"{vectordb_settings.base_url}/api/coding-problems/{problem_id}")
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.warning("coding problem get failed status=%d body=%s", resp.status_code, resp.text[:300])
                return None
            payload = resp.json()
            problem = payload.get("problem")
            return problem if isinstance(problem, dict) else None
    except Exception:
        logger.warning("coding problem get request failed id=%s", problem_id, exc_info=True)
        return None
