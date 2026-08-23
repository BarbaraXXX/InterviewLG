"""Pure domain helpers for versioned interview blueprints."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

BLUEPRINT_SCHEMA_VERSION = 1

QUESTION_TIERS = ("compact", "standard", "deep")
INTERVIEW_INTENSITIES = ("guided", "standard", "pressure")
FOCUS_AREAS = (
    "project_depth",
    "technical_foundation",
    "system_design",
    "coding",
    "communication",
)

DEFAULT_QUESTION_TIER = "standard"
DEFAULT_INTENSITY = "standard"
MAX_FOCUS_AREAS = 2

QUESTION_STAGES = ("opening", "project", "technical", "coding")

STAGE_LABELS = {
    "opening": "开场与自我介绍",
    "project": "项目深挖",
    "technical": "技术追问",
    "coding": "手撕代码",
    "summary": "总结反馈",
}

_TIER_STAGE_BUDGETS = {
    "compact": {"opening": 1, "project": 2, "technical": 3, "coding": 0},
    "standard": {"opening": 1, "project": 3, "technical": 4, "coding": 2},
    "deep": {"opening": 1, "project": 5, "technical": 6, "coding": 3},
}


class BlueprintValidationError(ValueError):
    """Raised when a persisted blueprint does not conform to schema version 1."""


def _normalize_choice(value: object, choices: tuple[str, ...], default: str) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip().lower()
    return normalized if normalized in choices else default


def _normalize_focus_areas(value: object) -> list[str]:
    candidates: Sequence[object]
    if isinstance(value, str):
        candidates = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        candidates = value
    else:
        candidates = ()

    normalized: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        focus = item.strip().lower()
        if focus in FOCUS_AREAS and focus not in normalized:
            normalized.append(focus)
        if len(normalized) == MAX_FOCUS_AREAS:
            break
    return normalized


def build_interview_blueprint(
    question_tier: str = DEFAULT_QUESTION_TIER,
    intensity: str = DEFAULT_INTENSITY,
    focus_areas: Sequence[str] | str | None = None,
) -> dict[str, Any]:
    """Build a canonical schema-v1 blueprint from user-facing configuration."""

    normalized_tier = _normalize_choice(question_tier, QUESTION_TIERS, DEFAULT_QUESTION_TIER)
    normalized_intensity = _normalize_choice(intensity, INTERVIEW_INTENSITIES, DEFAULT_INTENSITY)
    normalized_focus_areas = _normalize_focus_areas(focus_areas)
    stage_budgets = dict(_TIER_STAGE_BUDGETS[normalized_tier])

    return {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "question_tier": normalized_tier,
        "intensity": normalized_intensity,
        "focus_areas": normalized_focus_areas,
        "question_budget": sum(stage_budgets.values()),
        "include_coding": stage_budgets["coding"] > 0,
        "stage_budgets": stage_budgets,
    }


def normalize_blueprint(raw: Mapping[str, object] | None) -> dict[str, Any]:
    """Normalize API input into a canonical schema-v1 blueprint.

    Missing or invalid user-selectable values fall back to the standard defaults.
    An explicitly unsupported schema is rejected so it cannot be interpreted using
    rules from a different version.
    """

    source: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    if "schema_version" in source:
        schema_version = source["schema_version"]
        if (
            not isinstance(schema_version, int)
            or isinstance(schema_version, bool)
            or schema_version != BLUEPRINT_SCHEMA_VERSION
        ):
            raise BlueprintValidationError(f"unsupported blueprint schema_version: {schema_version!r}")

    focus_areas = source.get("focus_areas", source.get("focuses"))
    return build_interview_blueprint(
        question_tier=source.get("question_tier", DEFAULT_QUESTION_TIER),  # type: ignore[arg-type]
        intensity=source.get("intensity", DEFAULT_INTENSITY),  # type: ignore[arg-type]
        focus_areas=focus_areas,  # type: ignore[arg-type]
    )


def _validate_blueprint(blueprint: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(blueprint, Mapping):
        raise BlueprintValidationError("blueprint must be a JSON object")

    required_fields = {
        "schema_version",
        "question_tier",
        "intensity",
        "focus_areas",
        "question_budget",
        "include_coding",
        "stage_budgets",
    }
    missing_fields = required_fields.difference(blueprint)
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise BlueprintValidationError(f"blueprint is missing required fields: {missing}")

    try:
        canonical = normalize_blueprint(blueprint)
    except BlueprintValidationError:
        raise

    for field in required_fields:
        if blueprint[field] != canonical[field]:
            raise BlueprintValidationError(f"invalid blueprint field: {field}")
    return canonical


def serialize_blueprint(blueprint: Mapping[str, object]) -> str:
    """Serialize a valid blueprint into stable compact JSON."""

    canonical = _validate_blueprint(blueprint)
    return json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))


def deserialize_blueprint(raw: str) -> dict[str, Any]:
    """Deserialize and strictly validate a persisted schema-v1 blueprint."""

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BlueprintValidationError("blueprint is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise BlueprintValidationError("blueprint must be a JSON object")
    return _validate_blueprint(parsed)


def _validate_answered_questions(answered_questions: object) -> int:
    if not isinstance(answered_questions, int) or isinstance(answered_questions, bool) or answered_questions < 0:
        raise ValueError("answered_questions must be a non-negative integer")
    return answered_questions


def stage_for_answered_questions(blueprint: Mapping[str, object], answered_questions: int) -> str:
    """Return the stage that should ask the next question.

    ``answered_questions`` counts completed question-answer pairs. Summary is not a
    question stage and becomes active as soon as the configured budget is exhausted.
    """

    canonical = _validate_blueprint(blueprint)
    answered = _validate_answered_questions(answered_questions)
    if answered >= canonical["question_budget"]:
        return "summary"

    cumulative_budget = 0
    for stage in QUESTION_STAGES:
        cumulative_budget += canonical["stage_budgets"][stage]
        if answered < cumulative_budget:
            return stage
    return "summary"


def _stage_answered_questions(blueprint: Mapping[str, Any], answered_questions: int, stage: str) -> int:
    if stage == "summary":
        return 0

    previous_budget = 0
    for candidate in QUESTION_STAGES:
        if candidate == stage:
            return answered_questions - previous_budget
        previous_budget += blueprint["stage_budgets"][candidate]
    return 0


def build_interview_progress(
    blueprint: Mapping[str, object],
    state: Mapping[str, object] | None,
) -> dict[str, Any]:
    """Build a frontend-ready progress snapshot from a blueprint and session state."""

    canonical = _validate_blueprint(blueprint)
    session_state: Mapping[str, object] = state if isinstance(state, Mapping) else {}
    answered_raw = session_state.get("answered_questions", session_state.get("total_round", 0))
    answered = _validate_answered_questions(answered_raw)
    question_budget = canonical["question_budget"]
    capped_answered = min(answered, question_budget)
    stage = stage_for_answered_questions(canonical, answered)
    stage_budget = 0 if stage == "summary" else canonical["stage_budgets"][stage]
    stage_answered = _stage_answered_questions(canonical, capped_answered, stage)

    return {
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "answered_questions": capped_answered,
        "question_budget": question_budget,
        "remaining_questions": question_budget - capped_answered,
        "percent": round(capped_answered * 100 / question_budget),
        "include_coding": canonical["include_coding"],
        "question_tier": canonical["question_tier"],
        "intensity": canonical["intensity"],
        "focus_areas": list(canonical["focus_areas"]),
        "current_stage_answered": stage_answered,
        "current_stage_budget": stage_budget,
        "is_complete": stage == "summary",
    }
