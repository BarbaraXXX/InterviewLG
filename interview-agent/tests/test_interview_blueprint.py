import json

import pytest

from interview_agent.interview_blueprint import (
    BlueprintValidationError,
    build_interview_blueprint,
    build_interview_progress,
    deserialize_blueprint,
    normalize_blueprint,
    serialize_blueprint,
    stage_for_answered_questions,
)


@pytest.mark.parametrize(
    ("question_tier", "total", "include_coding", "stage_budgets"),
    [
        ("compact", 6, False, {"opening": 1, "project": 2, "technical": 3, "coding": 0}),
        ("standard", 10, True, {"opening": 1, "project": 3, "technical": 4, "coding": 2}),
        ("deep", 15, True, {"opening": 1, "project": 5, "technical": 6, "coding": 3}),
    ],
)
def test_build_interview_blueprint_uses_tier_budgets(
    question_tier: str,
    total: int,
    include_coding: bool,
    stage_budgets: dict[str, int],
):
    blueprint = build_interview_blueprint(question_tier=question_tier)

    assert blueprint["schema_version"] == 1
    assert blueprint["question_tier"] == question_tier
    assert blueprint["question_budget"] == total
    assert blueprint["include_coding"] is include_coding
    assert blueprint["stage_budgets"] == stage_budgets


def test_build_interview_blueprint_defaults_to_standard_configuration():
    blueprint = build_interview_blueprint()

    assert blueprint["question_tier"] == "standard"
    assert blueprint["intensity"] == "standard"
    assert blueprint["focus_areas"] == []
    assert blueprint["question_budget"] == 10
    assert blueprint["include_coding"] is True


def test_normalize_blueprint_cleans_values_and_limits_focus_areas():
    normalized = normalize_blueprint(
        {
            "question_tier": " DEEP ",
            "intensity": " Guided ",
            "focus_areas": [
                " project_depth ",
                "unknown",
                "project_depth",
                "coding",
                "communication",
            ],
        }
    )

    assert normalized["question_tier"] == "deep"
    assert normalized["intensity"] == "guided"
    assert normalized["focus_areas"] == ["project_depth", "coding"]


def test_normalize_blueprint_uses_defaults_for_invalid_scalar_values():
    normalized = normalize_blueprint(
        {
            "question_tier": "marathon",
            "intensity": object(),
            "focus_areas": "system_design",
        }
    )

    assert normalized["question_tier"] == "standard"
    assert normalized["intensity"] == "standard"
    assert normalized["focus_areas"] == ["system_design"]


def test_normalize_blueprint_accepts_legacy_focuses_key():
    normalized = normalize_blueprint({"focuses": ["technical_foundation"]})

    assert normalized["focus_areas"] == ["technical_foundation"]


@pytest.mark.parametrize(
    "intensity",
    ["guided", "standard", "pressure"],
)
def test_build_interview_blueprint_accepts_supported_intensities(intensity: str):
    blueprint = build_interview_blueprint(intensity=intensity)

    assert blueprint["intensity"] == intensity


def test_blueprint_serialization_round_trip_is_stable():
    blueprint = build_interview_blueprint(
        question_tier="deep",
        intensity="pressure",
        focus_areas=["system_design", "communication"],
    )

    serialized = serialize_blueprint(blueprint)
    restored = deserialize_blueprint(serialized)

    assert restored == blueprint
    assert serialize_blueprint(restored) == serialized
    assert json.loads(serialized) == {
        "schema_version": 1,
        "question_tier": "deep",
        "intensity": "pressure",
        "focus_areas": ["system_design", "communication"],
        "question_budget": 15,
        "include_coding": True,
        "stage_budgets": {
            "opening": 1,
            "project": 5,
            "technical": 6,
            "coding": 3,
        },
    }


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "[]",
        '{"schema_version":2}',
        (
            '{"schema_version":1,"question_tier":"standard","intensity":"standard",'
            '"focus_areas":[],"question_budget":9,"include_coding":true,'
            '"stage_budgets":{"opening":1,"project":3,"technical":4,"coding":2}}'
        ),
        (
            '{"schema_version":1,"question_tier":"standard","intensity":"standard",'
            '"focus_areas":["bad_focus"],"question_budget":10,"include_coding":true,'
            '"stage_budgets":{"opening":1,"project":3,"technical":4,"coding":2}}'
        ),
    ],
)
def test_deserialize_blueprint_rejects_invalid_persisted_data(raw: str):
    with pytest.raises(BlueprintValidationError):
        deserialize_blueprint(raw)


@pytest.mark.parametrize(
    ("answered_questions", "expected_stage"),
    [
        (0, "opening"),
        (1, "project"),
        (3, "technical"),
        (5, "technical"),
        (6, "summary"),
        (20, "summary"),
    ],
)
def test_stage_for_answered_questions_skips_zero_budget_coding_for_compact(
    answered_questions: int,
    expected_stage: str,
):
    blueprint = build_interview_blueprint(question_tier="compact")

    assert stage_for_answered_questions(blueprint, answered_questions) == expected_stage


@pytest.mark.parametrize(
    ("answered_questions", "expected_stage"),
    [
        (0, "opening"),
        (1, "project"),
        (3, "project"),
        (4, "technical"),
        (7, "technical"),
        (8, "coding"),
        (9, "coding"),
        (10, "summary"),
    ],
)
def test_stage_for_answered_questions_uses_completed_answer_count(
    answered_questions: int,
    expected_stage: str,
):
    blueprint = build_interview_blueprint(question_tier="standard")

    assert stage_for_answered_questions(blueprint, answered_questions) == expected_stage


@pytest.mark.parametrize("answered_questions", [-1, 1.5, True, "1"])
def test_stage_for_answered_questions_rejects_invalid_answer_count(answered_questions):
    blueprint = build_interview_blueprint()

    with pytest.raises(ValueError, match="answered_questions"):
        stage_for_answered_questions(blueprint, answered_questions)


def test_build_interview_progress_reports_stage_and_overall_progress():
    blueprint = build_interview_blueprint(question_tier="standard")

    progress = build_interview_progress(blueprint, {"answered_questions": 5})

    assert progress == {
        "stage": "technical",
        "stage_label": "技术追问",
        "answered_questions": 5,
        "question_budget": 10,
        "remaining_questions": 5,
        "percent": 50,
        "include_coding": True,
        "question_tier": "standard",
        "intensity": "standard",
        "focus_areas": [],
        "current_stage_answered": 1,
        "current_stage_budget": 4,
        "is_complete": False,
    }


def test_build_interview_progress_caps_completed_summary_progress():
    blueprint = build_interview_blueprint(question_tier="standard")

    progress = build_interview_progress(blueprint, {"answered_questions": 99})

    assert progress["answered_questions"] == 10
    assert progress["remaining_questions"] == 0
    assert progress["percent"] == 100
    assert progress["stage"] == "summary"
    assert progress["stage_label"] == "总结反馈"
    assert progress["current_stage_answered"] == 0
    assert progress["current_stage_budget"] == 0
    assert progress["is_complete"] is True


def test_build_interview_progress_accepts_existing_total_round_state_key():
    blueprint = build_interview_blueprint(question_tier="compact")

    progress = build_interview_progress(blueprint, {"total_round": 3})

    assert progress["answered_questions"] == 3
    assert progress["stage"] == "technical"
