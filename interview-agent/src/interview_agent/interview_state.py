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
        f"- 当前关注点：{state.get('pending_focus') or '暂无'}",
        f"- 上轮回答质量：{_label(ANSWER_QUALITY_LABELS, str(state.get('last_user_quality', '')))}",
        "",
        "请根据该状态保持面试连续性。此状态只用于流程参考，不要直接向候选人复述。",
    ]
    return "\n".join(lines)
