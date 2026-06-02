from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from interview_vectordb.embeddings import EmbeddingProvider, cosine_similarity
from interview_vectordb.schema import QuestionCard

logger = logging.getLogger(__name__)


class QuestionCardStore:
    def __init__(self, db_path: Path, embedding_provider: EmbeddingProvider) -> None:
        self.db_path = db_path
        self.embedding_provider = embedding_provider
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS question_cards (
                    id TEXT PRIMARY KEY,
                    domain_json TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer_outline_json TEXT NOT NULL,
                    followups_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    search_text TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dimensions INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_question_cards_topic ON question_cards(topic)")

    def import_cards(self, cards: list[QuestionCard], *, batch_size: int = 10, replace: bool = True) -> dict:
        unique_cards = dedupe_cards(cards)
        imported = 0
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            if replace:
                conn.execute("DELETE FROM question_cards")
            for batch in batched(unique_cards, batch_size):
                texts = [build_search_text(card) for card in batch]
                embeddings = self.embedding_provider.embed_texts(texts)
                for card, text, embedding in zip(batch, texts, embeddings, strict=True):
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO question_cards (
                            id, domain_json, topic, question, answer_outline_json, followups_json,
                            tags_json, difficulty, source_url, source_title, search_text,
                            embedding_json, embedding_model, embedding_dimensions, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            card.id,
                            json.dumps(card.domain, ensure_ascii=False),
                            card.topic,
                            card.question,
                            json.dumps(card.answer_outline, ensure_ascii=False),
                            json.dumps(card.followups, ensure_ascii=False),
                            json.dumps(card.tags, ensure_ascii=False),
                            card.difficulty,
                            card.source_url,
                            card.source_title,
                            text,
                            json.dumps(embedding),
                            self.embedding_provider.provider_name,
                            len(embedding),
                            now,
                        ),
                    )
                    imported += 1
        logger.info("Imported %d question cards into %s", imported, self.db_path)
        return {"imported": imported, "deduped": len(cards) - len(unique_cards)}

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM question_cards").fetchone()[0])

    def domain_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._connect() as conn:
            for row in conn.execute("SELECT domain_json FROM question_cards"):
                for domain in json.loads(row["domain_json"]):
                    counts[domain] = counts.get(domain, 0) + 1
        return counts

    def search(self, query: str, *, domain: list[str] | None = None, top_k: int = 5, min_score: float = 0.0) -> list[dict]:
        query_vector = self.embedding_provider.embed_texts([query])[0]
        filters = set(domain or [])
        scored: list[tuple[float, sqlite3.Row]] = []
        with self._connect() as conn:
            for row in conn.execute("SELECT * FROM question_cards"):
                row_domains = set(json.loads(row["domain_json"]))
                if filters and not filters.intersection(row_domains):
                    continue
                score = cosine_similarity(query_vector, json.loads(row["embedding_json"]))
                if score >= min_score:
                    scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row_to_search_result(row, score) for score, row in scored[:top_k]]


def load_question_cards_from_path(path: Path) -> list[QuestionCard]:
    if path.is_dir():
        cards: list[QuestionCard] = []
        for file_path in sorted(path.glob("*.jsonl")):
            cards.extend(load_question_cards_from_path(file_path))
        return cards
    if path.suffix != ".jsonl":
        raise ValueError(f"Unsupported question card file: {path}")
    cards = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cards.append(QuestionCard(**json.loads(line)))
        except Exception as exc:
            raise ValueError(f"Invalid QuestionCard at {path}:{line_no}: {exc}") from exc
    return cards


def build_search_text(card: QuestionCard) -> str:
    parts = [
        " ".join(card.domain),
        " ".join(card.tags),
        card.topic,
        card.question,
        " ".join(card.answer_outline),
        " ".join(card.followups),
    ]
    return "\n".join(part for part in parts if part.strip())


def row_to_search_result(row: sqlite3.Row, score: float) -> dict:
    return {
        "id": row["id"],
        "domain": json.loads(row["domain_json"]),
        "topic": row["topic"],
        "question": row["question"],
        "answer_outline": json.loads(row["answer_outline_json"]),
        "followups": json.loads(row["followups_json"]),
        "tags": json.loads(row["tags_json"]),
        "difficulty": row["difficulty"],
        "source_url": row["source_url"],
        "source_title": row["source_title"],
        "score": score,
    }


def dedupe_cards(cards: list[QuestionCard]) -> list[QuestionCard]:
    seen: set[str] = set()
    result: list[QuestionCard] = []
    for card in cards:
        if card.id in seen:
            continue
        seen.add(card.id)
        result.append(card)
    return result


def batched(items: list[QuestionCard], batch_size: int) -> list[list[QuestionCard]]:
    return [items[idx : idx + batch_size] for idx in range(0, len(items), batch_size)]
