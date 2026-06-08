"""Lightweight stage and topic control prompts for interview turns."""

from __future__ import annotations

from dataclasses import dataclass

from interview_agent.interview_state import STAGE_LABELS


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
    return "\n".join(
        [
            "本轮流程控制：",
            f"- 控制指令：{control.instruction}",
            f"- 允许动作：{actions}",
            "- 每轮只能提出一个主要问题；如果需要追问，只围绕当前主题的一个缺口追问。",
            "- 不要把内部阶段、主题状态、回答质量等字段直接告诉候选人。",
        ]
    )
