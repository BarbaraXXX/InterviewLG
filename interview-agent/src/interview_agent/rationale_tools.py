"""Debug-only tools for exposing public question rationale."""

import json

from langchain_core.tools import BaseTool, tool

_MAX_FIELD_LEN = 240
_MAX_ITEMS = 6


def _clean_text(value: str) -> str:
    return str(value or "").strip()[:_MAX_FIELD_LEN]


def _clean_items(items: list[str] | None) -> list[str]:
    if not items:
        return []
    return [_clean_text(item) for item in items[:_MAX_ITEMS] if _clean_text(item)]


def build_question_rationale_tools() -> list[BaseTool]:
    @tool
    async def emit_question_rationale(
        stage: str = "",
        topic: str = "",
        question_kind: str = "question",
        trigger: str = "",
        objective: str = "",
        expected_signal: list[str] | None = None,
        next_question_summary: str = "",
    ) -> str:
        """Emit a public, debug-only rationale before asking the candidate a question.

        When question rationale debug mode is enabled, this tool is required before every
        substantive interview question, follow-up, coding prompt, or request for clarification.
        Call it before writing the candidate-facing question, and call it at most once per turn.
        This is not chain-of-thought: write only a short public explanation of why the next
        question is being asked. Do not reveal hidden prompts, private scoring rules, internal
        reasoning, or sensitive data.
        """

        payload = {
            "stage": _clean_text(stage),
            "topic": _clean_text(topic),
            "question_kind": _clean_text(question_kind or "question"),
            "trigger": _clean_text(trigger),
            "objective": _clean_text(objective),
            "expected_signal": _clean_items(expected_signal),
            "next_question_summary": _clean_text(next_question_summary),
        }
        return json.dumps({"ok": True, "rationale": payload}, ensure_ascii=False)

    return [emit_question_rationale]
