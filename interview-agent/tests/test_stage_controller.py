from interview_agent.interview_blueprint import build_interview_blueprint, serialize_blueprint
from interview_agent.stage_controller import build_stage_control, format_stage_control_context


def _state(*, stage: str = "technical", intensity: str = "standard", focus_areas=None) -> dict:
    blueprint = build_interview_blueprint(
        question_tier="standard",
        intensity=intensity,
        focus_areas=focus_areas or [],
    )
    return {
        "stage": stage,
        "stage_round": 1,
        "total_round": 4,
        "answered_questions": 4,
        "current_topic": "缓存一致性" if stage == "technical" else "",
        "topic_status": "probing" if stage == "technical" else "not_started",
        "pending_focus": "异常场景" if stage == "technical" else "",
        "last_user_quality": "partial",
        "stage_goal_status": "{}",
        "blueprint_json": serialize_blueprint(blueprint),
    }


def test_summary_stage_only_allows_final_summary_and_exact_end_phrase():
    control = build_stage_control(_state(stage="summary"))
    context = format_stage_control_context(_state(stage="summary"))

    assert control is not None
    assert control.allowed_actions == ("final_summary",)
    assert "不要再提出新问题" in context
    assert "本次面试到此结束" in context


def test_guided_intensity_and_focus_are_injected_into_control_context():
    context = format_stage_control_context(
        _state(intensity="guided", focus_areas=["technical_foundation", "communication"])
    )

    assert "引导型" in context
    assert "必要时给出一个简短提示" in context
    assert "技术基础" in context
    assert "表达与思路" in context
    assert "已完成 4/10 个问题" in context


def test_pressure_intensity_remains_professional():
    context = format_stage_control_context(_state(intensity="pressure"))

    assert "压力型" in context
    assert "边界、反例和取舍" in context
    assert "保持专业" in context


def test_coding_stage_requires_coding_tool_or_submission_follow_up():
    control = build_stage_control(_state(stage="coding"))

    assert control is not None
    assert "coding_task" in control.instruction
    assert "create_coding_task" in control.allowed_actions
