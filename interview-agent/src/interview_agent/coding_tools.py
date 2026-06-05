"""Local LangChain tools for coding interview tasks."""

import json
import uuid

import aiosqlite
from langchain_core.tools import BaseTool, tool

from interview_agent.db import create_coding_task as db_create_coding_task

_SUPPORTED_LANGUAGES = {"python", "javascript", "typescript", "java", "cpp", "go"}
_MAX_TITLE_LEN = 120
_MAX_DESCRIPTION_LEN = 5000
_MAX_STARTER_CODE_LEN = 8000
_MAX_ITEMS = 12
_MAX_ITEM_LEN = 800


def _clean_language(language: str) -> str:
    normalized = language.strip().lower()
    aliases = {
        "js": "javascript",
        "ts": "typescript",
        "c++": "cpp",
        "golang": "go",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _SUPPORTED_LANGUAGES else "python"


def _clean_items(items: list[str] | None) -> list[str]:
    if not items:
        return []
    return [str(item).strip()[:_MAX_ITEM_LEN] for item in items[:_MAX_ITEMS] if str(item).strip()]


def _clean_examples(examples: list[dict] | None) -> list[dict]:
    if not examples:
        return []
    cleaned = []
    for example in examples[:_MAX_ITEMS]:
        if not isinstance(example, dict):
            continue
        input_text = str(example.get("input", "")).strip()[:_MAX_ITEM_LEN]
        output_text = str(example.get("output", "")).strip()[:_MAX_ITEM_LEN]
        explanation = str(example.get("explanation", "")).strip()[:_MAX_ITEM_LEN]
        if input_text or output_text:
            cleaned.append({"input": input_text, "output": output_text, "explanation": explanation})
    return cleaned


def build_coding_task_tool(session_id: str) -> BaseTool:
    @tool
    async def create_coding_task(
        title: str,
        description: str,
        language: str = "python",
        starter_code: str = "",
        constraints: list[str] | None = None,
        examples: list[dict] | None = None,
    ) -> str:
        """Create one hand-coding interview task for the current candidate.

        Use this only when the interview should enter a coding section. Do not create another task while
        the previous task is still active. The platform will show the task to the candidate and wait for
        a code submission before you evaluate it.
        """

        clean_title = title.strip()[:_MAX_TITLE_LEN]
        clean_description = description.strip()[:_MAX_DESCRIPTION_LEN]
        if not clean_title or not clean_description:
            return json.dumps({"ok": False, "error": "title and description are required"}, ensure_ascii=False)

        clean_language = _clean_language(language)
        clean_starter_code = starter_code[:_MAX_STARTER_CODE_LEN]
        task_id = uuid.uuid4().hex
        try:
            task = await db_create_coding_task(
                task_id=task_id,
                session_id=session_id,
                title=clean_title,
                description=clean_description,
                language=clean_language,
                starter_code=clean_starter_code,
                constraints_json=json.dumps(_clean_items(constraints), ensure_ascii=False),
                examples_json=json.dumps(_clean_examples(examples), ensure_ascii=False),
            )
        except aiosqlite.IntegrityError:
            return json.dumps(
                {
                    "ok": False,
                    "error": "当前已经有一道未提交的手撕题，请等待候选人提交后再创建下一题。",
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "ok": True,
                "task_id": task["id"],
                "message": "代码题已创建，等待候选人在手撕平台提交代码。",
            },
            ensure_ascii=False,
        )

    return create_coding_task
