from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    adapter: str = "generic"
    extract: bool = True
    discover_prefixes: list[str] = field(default_factory=list)
    domain: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Block:
    kind: str
    text: str
    level: int = 0


@dataclass(frozen=True)
class NormalizedDocument:
    source_id: str
    source_url: str
    source_title: str
    domain: list[str]
    tags: list[str]
    blocks: list[Block]


@dataclass
class ExtractedCard:
    id: str
    domain: list[str]
    topic: str
    question: str
    answer_text: str
    answer_outline: list[str]
    followups: list[str]
    tags: list[str]
    difficulty: str
    source_url: str
    source_title: str

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain,
            "topic": self.topic,
            "question": self.question,
            "answer_outline": self.answer_outline,
            "followups": self.followups,
            "tags": self.tags,
            "difficulty": self.difficulty,
            "source_url": self.source_url,
            "source_title": self.source_title,
        }

    def to_extracted_dict(self) -> dict:
        data = self.to_public_dict()
        data["answer_text"] = self.answer_text
        return data
