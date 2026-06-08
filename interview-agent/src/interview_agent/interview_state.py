"""Formatting helpers for lightweight interview state."""

from __future__ import annotations

import json

TARGET_LABELS = {
    "campus_intern": "校招实习",
    "campus_fulltime": "校招正式岗",
    "junior": "校招实习",
    "mid": "校招正式岗",
    "senior": "校招正式岗",
}

STAGE_LABELS = {
    "opening": "开场与自我介绍",
    "project": "项目深挖",
    "technical": "技术追问",
    "coding": "手撕代码",
    "summary": "总结反馈",
}

STAGE_ORDER = ("opening", "project", "technical", "coding", "summary")

STAGE_STATUS_LABELS = {
    "pending": "待进行",
    "active": "进行中",
    "completed": "已完成",
    "skipped": "已跳过",
}

TOPIC_STATUS_LABELS = {
    "not_started": "未开始",
    "asking": "提出主问题",
    "probing": "追问中",
    "completed": "已完成",
    "skipped": "已跳过",
}

ANSWER_QUALITY_LABELS = {
    "unknown": "未知",
    "weak": "较弱",
    "partial": "部分覆盖",
    "good": "较好",
}


def _label(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value or "未知")


def _json_object(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def initial_stage_plan(current_stage: str = "opening") -> dict[str, str]:
    current = current_stage if current_stage in STAGE_ORDER else "opening"
    current_index = STAGE_ORDER.index(current)
    plan: dict[str, str] = {}
    for index, stage in enumerate(STAGE_ORDER):
        if index < current_index:
            plan[stage] = "completed"
        elif stage == current:
            plan[stage] = "active"
        else:
            plan[stage] = "pending"
    return plan


def normalize_stage_plan(raw: str, current_stage: str = "opening") -> dict[str, str]:
    current = current_stage if current_stage in STAGE_ORDER else "opening"
    parsed = _json_object(raw)
    if not parsed:
        return initial_stage_plan(current)

    plan = initial_stage_plan(current)
    valid_statuses = set(STAGE_STATUS_LABELS)
    for stage in STAGE_ORDER:
        status = str(parsed.get(stage) or "").strip()
        if status in valid_statuses:
            plan[stage] = status

    for stage, status in list(plan.items()):
        if status == "active" and stage != current:
            plan[stage] = "pending"
    plan[current] = "active"
    return plan


def dump_stage_plan(plan: dict[str, str]) -> str:
    normalized = {stage: plan.get(stage, "pending") for stage in STAGE_ORDER}
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def transition_stage_plan(
    raw: str,
    current_stage: str,
    next_stage: str,
    *,
    complete_current: bool = False,
) -> dict[str, str]:
    plan = normalize_stage_plan(raw, current_stage)
    current = current_stage if current_stage in STAGE_ORDER else "opening"
    target = next_stage if next_stage in STAGE_ORDER else current

    if current != target:
        plan[current] = "completed" if complete_current else "pending"
    for stage, status in list(plan.items()):
        if status == "active" and stage != target:
            plan[stage] = "pending"
    plan[target] = "active"
    return plan


def complete_stage_and_choose_next(raw: str, current_stage: str) -> tuple[dict[str, str], str]:
    current = current_stage if current_stage in STAGE_ORDER else "opening"
    plan = normalize_stage_plan(raw, current)
    plan[current] = "completed"
    for stage in STAGE_ORDER:
        if plan.get(stage) == "pending":
            plan[stage] = "active"
            return plan, stage
    plan["summary"] = "active"
    return plan, "summary"


def format_stage_plan(raw: str, current_stage: str) -> str:
    plan = normalize_stage_plan(raw, current_stage)
    labels = []
    for stage in STAGE_ORDER:
        labels.append(f"{STAGE_LABELS[stage]}({STAGE_STATUS_LABELS.get(plan[stage], plan[stage])})")
    return "、".join(labels)


def _covered_topics(value: str) -> str:
    try:
        topics = json.loads(value or "[]")
    except json.JSONDecodeError:
        topics = []
    if not isinstance(topics, list) or not topics:
        return "暂无"
    labels = []
    for item in topics[:12]:
        if isinstance(item, dict):
            topic = str(item.get("topic", "")).strip()
            quality = str(item.get("quality", "")).strip()
            if topic and quality:
                labels.append(f"{topic[:32]}({quality[:12]})")
            elif topic:
                labels.append(topic[:40])
        else:
            text = str(item).strip()
            if text:
                labels.append(text[:40])
    return "、".join(labels) or "暂无"


def format_state_context(state: dict | None) -> str:
    if not state:
        return ""

    lines = [
        "当前面试状态：",
        f"- 面试目标：{_label(TARGET_LABELS, str(state.get('target', '')))}",
        f"- 当前阶段：{_label(STAGE_LABELS, str(state.get('stage', '')))}",
        f"- 当前阶段轮数：{int(state.get('stage_round') or 0)}",
        f"- 总轮数：{int(state.get('total_round') or 0)}",
        f"- 当前主题：{state.get('current_topic') or '暂无'}",
        f"- 当前主题状态：{_label(TOPIC_STATUS_LABELS, str(state.get('topic_status', '')))}",
        f"- 已考查知识点：{_covered_topics(str(state.get('covered_topics', '[]')))}",
        f"- 阶段计划：{format_stage_plan(str(state.get('stage_goal_status', '{}')), str(state.get('stage', 'opening')))}",
        f"- 当前关注点：{state.get('pending_focus') or '暂无'}",
        f"- 上轮回答质量：{_label(ANSWER_QUALITY_LABELS, str(state.get('last_user_quality', '')))}",
        "",
        "请根据该状态保持面试连续性。此状态只用于流程参考，不要直接向候选人复述。",
    ]
    return "\n".join(lines)
