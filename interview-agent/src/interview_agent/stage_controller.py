"""Lightweight stage and topic control prompts for interview turns."""

from __future__ import annotations

from dataclasses import dataclass

from interview_agent.interview_blueprint import (
    BlueprintValidationError,
    build_interview_progress,
    deserialize_blueprint,
)
from interview_agent.interview_state import STAGE_LABELS, format_stage_plan

INTENSITY_GUIDANCE = {
    "guided": (
        "引导型：候选人回答不完整时，必要时给出一个简短提示或换一种问法，"
        "帮助其继续思考，但不要直接给出完整答案。"
    ),
    "standard": "标准型：保持真实校招面试节奏，根据回答质量自然追问、收束或切换主题。",
    "pressure": (
        "压力型：减少鼓励性铺垫，优先追问边界、反例和取舍；始终保持专业、克制，"
        "不得使用贬低或攻击性表达。"
    ),
}

FOCUS_LABELS = {
    "project_depth": "项目深挖",
    "technical_foundation": "技术基础",
    "system_design": "系统设计",
    "coding": "编码能力",
    "communication": "表达与思路",
}


@dataclass(frozen=True)
class StageControl:
    stage: str
    current_topic: str
    topic_status: str
    instruction: str
    allowed_actions: tuple[str, ...]


def build_stage_control(state: dict | None) -> StageControl | None:
    if not state:
        return None

    stage = str(state.get("stage") or "opening")
    current_topic = str(state.get("current_topic") or "").strip()
    topic_status = str(state.get("topic_status") or "not_started").strip()
    pending_focus = str(state.get("pending_focus") or "").strip()
    last_quality = str(state.get("last_user_quality") or "").strip()
    stage_label = STAGE_LABELS.get(stage, stage)

    if stage == "summary":
        return StageControl(
            stage=stage,
            current_topic=current_topic,
            topic_status=topic_status,
            instruction=(
                "当前进入总结反馈阶段。本轮只给出简洁的总体评价、主要优势和最优先改进建议，"
                "不要再提出新问题，不要调用代码题工具。结尾必须且只能说一次“本次面试到此结束”。"
            ),
            allowed_actions=("final_summary",),
        )

    if stage == "coding":
        return StageControl(
            stage=stage,
            current_topic=current_topic,
            topic_status=topic_status,
            instruction=(
                "当前进入手撕代码阶段。如果尚无 active coding_task，必须调用 search_coding_problems 后再调用 "
                "create_coding_task_from_problem（题库不可用时才调用 create_coding_task）；如果候选人已提交代码，"
                "只围绕思路、复杂度、边界条件和代码质量做一次主要追问或收束，不要切回无关主题。"
            ),
            allowed_actions=("create_coding_task", "evaluate_coding_submission", "brief_feedback"),
        )

    allowed_actions = ["ask_one_question", "brief_feedback"]
    if current_topic and topic_status in {"asking", "probing"}:
        focus = pending_focus or current_topic
        instruction = (
            f"当前处于{stage_label}阶段，正在考查主题：{current_topic}。"
            f"候选人上一轮回答质量为：{last_quality or 'unknown'}。"
            f"本轮优先围绕“{focus}”做单点追问或确认，不要切换到新的无关主题。"
            "如果你判断该主题已经问透，可以自然收束并提出下一个单一主题的问题。"
        )
        allowed_actions.append("complete_current_topic")
    elif current_topic and topic_status == "completed":
        instruction = (
            f"当前处于{stage_label}阶段，上一个主题“{current_topic}”已完成。"
            "本轮可以选择下一个与岗位、简历、JD 或 RAG 上下文相关的单一主题。"
        )
        allowed_actions.append("start_next_topic")
    else:
        instruction = (
            f"当前处于{stage_label}阶段，尚未锁定本轮主题。"
            "请选择一个最适合当前阶段的单一主题开始考查，不要一次提出多个方向的问题。"
        )
        allowed_actions.append("start_next_topic")

    return StageControl(
        stage=stage,
        current_topic=current_topic,
        topic_status=topic_status,
        instruction=instruction,
        allowed_actions=tuple(allowed_actions),
    )


def format_stage_control_context(state: dict | None) -> str:
    control = build_stage_control(state)
    if control is None:
        return ""

    actions = "、".join(control.allowed_actions)
    stage_plan = format_stage_plan(str(state.get("stage_goal_status") or "{}"), control.stage)
    lines = [
        "本轮流程控制：",
        f"- 阶段计划：{stage_plan}",
        f"- 控制指令：{control.instruction}",
        f"- 允许动作：{actions}",
    ]
    blueprint = _load_blueprint(state)
    if blueprint is not None:
        progress = build_interview_progress(blueprint, state)
        lines.append(
            f"- 问题预算：已完成 {progress['answered_questions']}/{progress['question_budget']} 个问题，"
            f"剩余 {progress['remaining_questions']} 个。"
        )
        if control.stage != "summary":
            lines.append("- 尚未进入总结阶段，不要提前给出整场总结，也不要说“本次面试到此结束”。")
        lines.append(f"- 面试强度：{INTENSITY_GUIDANCE[blueprint['intensity']]}")
        focus_labels = [FOCUS_LABELS[item] for item in blueprint["focus_areas"] if item in FOCUS_LABELS]
        if focus_labels:
            lines.append(f"- 本场重点：{'、'.join(focus_labels)}。选择问题时优先覆盖这些能力。")
    if control.stage != "summary":
        lines.append("- 每轮只能提出一个主要问题；如果需要追问，只围绕当前主题的一个缺口追问。")
    if blueprint is None:
        lines.append("- 如果候选人要求提前或延后某个环节，可以合理配合；被打断但未完成的阶段后续需要补回。")
    else:
        lines.append("- 本场按已选问题挡位推进；候选人可通过界面中断或结束，不要自行改写问题预算和阶段顺序。")
    lines.append("- 不要把内部阶段、主题状态、回答质量等字段直接告诉候选人。")
    return "\n".join(lines)


def _load_blueprint(state: dict) -> dict | None:
    raw = state.get("blueprint_json")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return deserialize_blueprint(raw)
    except BlueprintValidationError:
        return None
