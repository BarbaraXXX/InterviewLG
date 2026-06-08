"""Local LangChain tools for coding interview tasks."""

import json
import uuid

import aiosqlite
from langchain_core.tools import BaseTool, tool

from interview_agent.db import create_coding_task as db_create_coding_task
from interview_agent.db import request_latest_coding_task_revision
from interview_agent.db import set_session_state_stage

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


def build_coding_tools(session_id: str) -> list[BaseTool]:
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
            await set_session_state_stage(session_id, "coding")
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

    @tool
    async def request_coding_revision(revision_instruction: str = "") -> str:
        """重新打开最近一次已提交的手撕代码题，让候选人在上一版代码基础上修改并再次提交。

        只有当候选人代码完成度很低、核心算法方向错误、代码基本无法表达解题思路，
        或关键数据结构/边界完全缺失，必须让候选人在代码层面重新组织实现时才调用。
        如果整体思路可接受，只是有小语法问题、命名问题、个别边界遗漏、复杂度表述不完整，
        或你只是想指出代码问题、给出优化建议、口头追问复杂度或进入下一环节，不要调用。
        revision_instruction 应写清本次需要修改的具体点，例如补充空输入边界、修正递归终止条件、优化复杂度。
        调用后平台会重新打开同一道题，并把候选人上一版提交代码作为可编辑草稿。
        """

        task = await request_latest_coding_task_revision(
            session_id,
            revision_instruction.strip()[:_MAX_ITEM_LEN],
        )
        if task is None:
            return json.dumps(
                {
                    "ok": False,
                    "error": "没有可修订的已提交代码题，或当前已有一道未提交的手撕题。",
                },
                ensure_ascii=False,
            )
        await set_session_state_stage(session_id, "coding")
        return json.dumps(
            {
                "ok": True,
                "task_id": task["id"],
                "message": "代码题已重新打开，候选人可以在上一版代码基础上修改后再次提交。",
            },
            ensure_ascii=False,
        )

    return [create_coding_task, request_coding_revision]


def build_coding_task_tool(session_id: str) -> BaseTool:
    return build_coding_tools(session_id)[0]
