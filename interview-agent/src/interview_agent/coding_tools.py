"""Local LangChain tools for coding interview tasks."""

import json
import uuid

import aiosqlite
from langchain_core.tools import BaseTool, tool

from interview_agent.coding_problem_client import get_coding_problem
from interview_agent.coding_problem_client import search_coding_problems as client_search_coding_problems
from interview_agent.db import create_coding_task as db_create_coding_task
from interview_agent.db import (
    get_session_blueprint,
    get_session_state,
    list_used_coding_problem_ids,
    request_latest_coding_task_revision,
    set_session_state_stage,
)

_SUPPORTED_LANGUAGES = {"python", "javascript", "typescript", "java", "cpp", "go"}
_MAX_TITLE_LEN = 120
_MAX_DESCRIPTION_LEN = 5000
_MAX_STARTER_CODE_LEN = 8000
_MAX_ITEMS = 12
_MAX_ITEM_LEN = 800


async def _coding_mutation_error(session_id: str) -> str:
    blueprint = await get_session_blueprint(session_id)
    if blueprint is None:
        return ""
    if not blueprint["include_coding"]:
        return "当前面试挡位不包含手撕代码，不能创建或重新打开代码题。"
    state = await get_session_state(session_id)
    if state is None or state.get("stage") != "coding":
        return "当前阶段不允许创建或重新打开代码题，请等待流程控制进入手撕代码阶段。"
    return ""


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


def _clean_starter_code_map(starter_code: object) -> dict[str, str]:
    if not isinstance(starter_code, dict):
        return {}
    cleaned: dict[str, str] = {}
    for language, code in starter_code.items():
        clean_language = _clean_language(str(language))
        clean_code = str(code or "").strip()[:_MAX_STARTER_CODE_LEN]
        if clean_code:
            cleaned[clean_language] = clean_code
    return cleaned


def build_coding_tools(session_id: str) -> list[BaseTool]:
    @tool
    async def search_coding_problems(
        query: str = "",
        difficulty: list[str] | None = None,
        importance: list[str] | None = None,
        answer_mode: list[str] | None = None,
        topics: list[str] | None = None,
        top_k: int = 5,
    ) -> str:
        """Search the coding problem bank before creating a hand-coding task.

        Use this before entering the coding section. Prefer importance=["hot100"], answer_mode=["core"],
        and pick difficulty from the candidate's observed coding/algorithm strength: easy for weak basics,
        medium for normal campus interviews, hard only for very strong candidates or explicit requests.
        The tool automatically excludes problems already used in the current session.
        """

        used_problem_ids = await list_used_coding_problem_ids(session_id)
        problems = await client_search_coding_problems(
            query=query.strip()[:1200],
            difficulty=_clean_items(difficulty),
            importance=_clean_items(importance) or ["hot100"],
            answer_mode=_clean_items(answer_mode) or ["core"],
            topics=_clean_items(topics),
            exclude_ids=used_problem_ids,
            top_k=min(max(int(top_k or 5), 1), 8),
        )
        summaries = []
        for problem in problems:
            statement = str(problem.get("statement") or "").strip().replace("\n", " ")
            summaries.append(
                {
                    "id": problem.get("id"),
                    "title": problem.get("title"),
                    "difficulty": problem.get("difficulty"),
                    "importance": problem.get("importance"),
                    "answer_mode": problem.get("answer_mode"),
                    "topics": problem.get("topics") or [],
                    "statement_preview": statement[:240],
                    "score": problem.get("score"),
                }
            )
        return json.dumps(
            {
                "ok": True,
                "problems": summaries,
                "excluded_problem_ids": used_problem_ids,
                "message": "请选择一个 problem_id 调用 create_coding_task_from_problem；若列表为空，才考虑 fallback 自拟题。",
            },
            ensure_ascii=False,
        )

    @tool
    async def create_coding_task_from_problem(problem_id: str, language: str = "python") -> str:
        """Create one hand-coding task from the approved coding problem bank.

        Use this after search_coding_problems returns a suitable problem. Do not rewrite the problem statement,
        examples, constraints, or starter code yourself. If the problem is unavailable, search again or only then
        fall back to create_coding_task.
        """

        if permission_error := await _coding_mutation_error(session_id):
            return json.dumps({"ok": False, "error": permission_error}, ensure_ascii=False)
        clean_problem_id = problem_id.strip()[:128]
        if not clean_problem_id:
            return json.dumps({"ok": False, "error": "problem_id is required"}, ensure_ascii=False)
        problem = await get_coding_problem(clean_problem_id)
        if not problem:
            return json.dumps({"ok": False, "error": "题库中没有找到该手撕题。"}, ensure_ascii=False)

        clean_language = _clean_language(language)
        starter_code_map = _clean_starter_code_map(problem.get("starter_code"))
        starter_code = str(starter_code_map.get(clean_language) or starter_code_map.get("python") or "")[
            :_MAX_STARTER_CODE_LEN
        ]
        clean_title = str(problem.get("title") or "").strip()[:_MAX_TITLE_LEN]
        clean_description = str(problem.get("statement") or "").strip()[:_MAX_DESCRIPTION_LEN]
        if not clean_title or not clean_description:
            return json.dumps({"ok": False, "error": "题库题目缺少 title 或 statement。"}, ensure_ascii=False)

        task_id = uuid.uuid4().hex
        try:
            task = await db_create_coding_task(
                task_id=task_id,
                session_id=session_id,
                title=clean_title,
                description=clean_description,
                language=clean_language,
                starter_code=starter_code,
                starter_code_json=json.dumps(starter_code_map, ensure_ascii=False),
                constraints_json=json.dumps(_clean_items(problem.get("constraints")), ensure_ascii=False),
                examples_json=json.dumps(_clean_examples(problem.get("examples")), ensure_ascii=False),
                source_problem_id=str(problem.get("id") or clean_problem_id)[:128],
                source_problem_title=clean_title,
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
                "problem_id": problem.get("id"),
                "title": task["title"],
                "message": "已从题库创建代码题，等待候选人在手撕平台提交代码。",
            },
            ensure_ascii=False,
        )

    @tool
    async def create_coding_task(
        title: str,
        description: str,
        language: str = "python",
        starter_code: str = "",
        constraints: list[str] | None = None,
        examples: list[dict] | None = None,
    ) -> str:
        """Fallback: create one hand-coding interview task manually.

        Prefer search_coding_problems and create_coding_task_from_problem. Use this only when the approved
        coding problem bank is unavailable or returns no suitable task. Do not create another task while
        the previous task is still active.
        """

        if permission_error := await _coding_mutation_error(session_id):
            return json.dumps({"ok": False, "error": permission_error}, ensure_ascii=False)
        clean_title = title.strip()[:_MAX_TITLE_LEN]
        clean_description = description.strip()[:_MAX_DESCRIPTION_LEN]
        if not clean_title or not clean_description:
            return json.dumps({"ok": False, "error": "title and description are required"}, ensure_ascii=False)

        clean_language = _clean_language(language)
        clean_starter_code = starter_code[:_MAX_STARTER_CODE_LEN]
        starter_code_map = {clean_language: clean_starter_code} if clean_starter_code.strip() else {}
        task_id = uuid.uuid4().hex
        try:
            task = await db_create_coding_task(
                task_id=task_id,
                session_id=session_id,
                title=clean_title,
                description=clean_description,
                language=clean_language,
                starter_code=clean_starter_code,
                starter_code_json=json.dumps(starter_code_map, ensure_ascii=False),
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

        if permission_error := await _coding_mutation_error(session_id):
            return json.dumps({"ok": False, "error": permission_error}, ensure_ascii=False)
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

    return [search_coding_problems, create_coding_task_from_problem, create_coding_task, request_coding_revision]


def build_coding_task_tool(session_id: str) -> BaseTool:
    return build_coding_tools(session_id)[0]
