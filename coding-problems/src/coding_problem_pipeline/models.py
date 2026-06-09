from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DIFFICULTIES = {"easy", "medium", "hard"}
IMPORTANCE_LEVELS = {"hot100", "high", "normal"}
ANSWER_MODES = {"core", "acm"}
SUPPORTED_LANGUAGES = {"python", "cpp", "java", "go", "javascript", "typescript"}


@dataclass(frozen=True)
class ProblemIndex:
    source: str
    source_id: str
    slug: str
    title: str
    difficulty: str = "easy"
    importance: str = "hot100"
    answer_mode: str = "core"
    topics: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemIndex":
        return cls(
            source=str(data.get("source") or "manual").strip(),
            source_id=str(data.get("source_id") or data.get("id") or "").strip(),
            slug=str(data.get("slug") or "").strip(),
            title=str(data.get("title") or "").strip(),
            difficulty=str(data.get("difficulty") or "easy").strip().lower(),
            importance=str(data.get("importance") or "hot100").strip().lower(),
            answer_mode=str(data.get("answer_mode") or "core").strip().lower(),
            topics=_clean_list(data.get("topics")),
            tags=_clean_list(data.get("tags")),
        )

    def stable_id(self) -> str:
        parts = [self.source, self.source_id, self.slug or self.title]
        cleaned = []
        for part in parts:
            text = "".join(ch.lower() if ch.isalnum() else "_" for ch in part)
            text = "_".join(item for item in text.split("_") if item)
            if text:
                cleaned.append(text)
        return "_".join(cleaned)[:128] or "coding_problem"


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_problem(index: ProblemIndex, raw: dict[str, Any]) -> dict[str, Any]:
    examples = raw.get("examples") if isinstance(raw.get("examples"), list) else []
    starter_code = raw.get("starter_code") if isinstance(raw.get("starter_code"), dict) else {}
    normalized_starter = {
        str(language).strip().lower(): str(code)
        for language, code in starter_code.items()
        if str(language).strip().lower() in SUPPORTED_LANGUAGES and str(code).strip()
    }
    return {
        "id": str(raw.get("id") or index.stable_id()).strip()[:128],
        "title": str(raw.get("title") or index.title).strip()[:256],
        "difficulty": str(raw.get("difficulty") or index.difficulty).strip().lower(),
        "importance": str(raw.get("importance") or index.importance).strip().lower(),
        "answer_mode": str(raw.get("answer_mode") or index.answer_mode).strip().lower(),
        "topics": _clean_list(raw.get("topics")) or index.topics,
        "tags": _clean_list(raw.get("tags")) or index.tags,
        "statement": str(raw.get("statement") or "").strip(),
        "constraints": _clean_list(raw.get("constraints")),
        "examples": [_normalize_example(item) for item in examples if isinstance(item, dict)],
        "starter_code": normalized_starter,
        "source_url": "",
        "source_title": f"{index.source}:{index.source_id}" if index.source_id else index.source,
    }


def _normalize_example(item: dict[str, Any]) -> dict[str, str]:
    return {
        "input": str(item.get("input") or "").strip()[:2000],
        "output": str(item.get("output") or "").strip()[:2000],
        "explanation": str(item.get("explanation") or "").strip()[:2000],
    }
