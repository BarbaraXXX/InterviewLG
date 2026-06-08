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


def _label(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value or "未知")


def _covered_topics(value: str) -> str:
    try:
        topics = json.loads(value or "[]")
    except json.JSONDecodeError:
        topics = []
    if not isinstance(topics, list) or not topics:
        return "暂无"
    return "、".join(str(item)[:40] for item in topics[:12] if str(item).strip()) or "暂无"


def format_state_context(state: dict | None) -> str:
    if not state:
        return ""

    lines = [
        "当前面试状态：",
        f"- 面试目标：{_label(TARGET_LABELS, str(state.get('target', '')))}",
        f"- 当前阶段：{_label(STAGE_LABELS, str(state.get('stage', '')))}",
        f"- 当前阶段轮数：{int(state.get('stage_round') or 0)}",
        f"- 总轮数：{int(state.get('total_round') or 0)}",
        f"- 已考查知识点：{_covered_topics(str(state.get('covered_topics', '[]')))}",
        f"- 当前关注点：{state.get('pending_focus') or '暂无'}",
        f"- 上轮回答质量：{state.get('last_user_quality') or '暂无'}",
        "",
        "请根据该状态保持面试连续性。此状态只用于流程参考，不要直接向候选人复述。",
    ]
    return "\n".join(lines)
