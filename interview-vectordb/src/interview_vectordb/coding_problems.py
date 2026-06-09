from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from interview_vectordb.embeddings import EmbeddingProvider, cosine_similarity
from interview_vectordb.schema import CodingProblem

logger = logging.getLogger(__name__)


class CodingProblemStore:
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
                CREATE TABLE IF NOT EXISTS coding_problems (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    importance TEXT NOT NULL,
                    answer_mode TEXT NOT NULL,
                    topics_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    constraints_json TEXT NOT NULL,
                    examples_json TEXT NOT NULL,
                    starter_code_json TEXT NOT NULL,
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_coding_problems_difficulty ON coding_problems(difficulty)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_coding_problems_importance ON coding_problems(importance)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_coding_problems_answer_mode ON coding_problems(answer_mode)")

    def import_problems(self, problems: list[CodingProblem], *, batch_size: int = 10, replace: bool = True) -> dict:
        unique_problems = dedupe_problems(problems)
        imported = 0
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            if replace:
                conn.execute("DELETE FROM coding_problems")
            for batch in batched(unique_problems, batch_size):
                texts = [build_search_text(problem) for problem in batch]
                embeddings = self.embedding_provider.embed_texts(texts)
                for problem, text, embedding in zip(batch, texts, embeddings, strict=True):
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO coding_problems (
                            id, title, difficulty, importance, answer_mode, topics_json, tags_json,
                            statement, constraints_json, examples_json, starter_code_json,
                            source_url, source_title, search_text, embedding_json,
                            embedding_model, embedding_dimensions, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            problem.id,
                            problem.title,
                            problem.difficulty,
                            problem.importance,
                            problem.answer_mode,
                            json.dumps(problem.topics, ensure_ascii=False),
                            json.dumps(problem.tags, ensure_ascii=False),
                            problem.statement,
                            json.dumps(problem.constraints, ensure_ascii=False),
                            json.dumps([example.model_dump() for example in problem.examples], ensure_ascii=False),
                            json.dumps(problem.starter_code, ensure_ascii=False),
                            problem.source_url,
                            problem.source_title,
                            text,
                            json.dumps(embedding),
                            self.embedding_provider.provider_name,
                            len(embedding),
                            now,
                        ),
                    )
                    imported += 1
        logger.info("Imported %d coding problems into %s", imported, self.db_path)
        return {"imported": imported, "deduped": len(problems) - len(unique_problems)}

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM coding_problems").fetchone()[0])

    def get(self, problem_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM coding_problems WHERE id = ?", (problem_id,)).fetchone()
            return row_to_search_result(row, 1.0) if row else None

    def stats(self) -> dict:
        stats = {
            "difficulty": {},
            "importance": {},
            "answer_mode": {},
            "topics": {},
        }
        with self._connect() as conn:
            for row in conn.execute("SELECT difficulty, importance, answer_mode, topics_json FROM coding_problems"):
                _increment(stats["difficulty"], row["difficulty"])
                _increment(stats["importance"], row["importance"])
                _increment(stats["answer_mode"], row["answer_mode"])
                for topic in json.loads(row["topics_json"]):
                    _increment(stats["topics"], topic)
        return stats

    def search(
        self,
        query: str,
        *,
        difficulty: list[str] | None = None,
        importance: list[str] | None = None,
        answer_mode: list[str] | None = None,
        topics: list[str] | None = None,
        exclude_ids: list[str] | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict]:
        query_text = query.strip() or "经典手撕算法题"
        query_vector = self.embedding_provider.embed_texts([query_text])[0]
        difficulty_filter = _clean_filter(difficulty)
        importance_filter = _clean_filter(importance)
        answer_mode_filter = _clean_filter(answer_mode)
        topics_filter = _clean_filter(topics)
        excluded = _clean_filter(exclude_ids)

        scored: list[tuple[float, sqlite3.Row]] = []
        with self._connect() as conn:
            for row in conn.execute("SELECT * FROM coding_problems"):
                if row["id"] in excluded:
                    continue
                if difficulty_filter and row["difficulty"] not in difficulty_filter:
                    continue
                if importance_filter and row["importance"] not in importance_filter:
                    continue
                if answer_mode_filter and row["answer_mode"] not in answer_mode_filter:
                    continue
                row_topics = set(json.loads(row["topics_json"]))
                if topics_filter and not topics_filter.intersection(row_topics):
                    continue
                score = cosine_similarity(query_vector, json.loads(row["embedding_json"]))
                if score >= min_score:
                    scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row_to_search_result(row, score) for score, row in scored[:top_k]]


def load_coding_problems_from_path(path: Path) -> list[CodingProblem]:
    if path.is_dir():
        problems: list[CodingProblem] = []
        for file_path in sorted(path.glob("*.jsonl")):
            problems.extend(load_coding_problems_from_path(file_path))
        return problems
    if path.suffix != ".jsonl":
        raise ValueError(f"Unsupported coding problem file: {path}")
    problems = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            problems.append(CodingProblem(**json.loads(line)))
        except Exception as exc:
            raise ValueError(f"Invalid CodingProblem at {path}:{line_no}: {exc}") from exc
    return problems


def build_search_text(problem: CodingProblem) -> str:
    example_text = []
    for example in problem.examples[:3]:
        example_text.extend([example.input, example.output, example.explanation])
    parts = [
        problem.title,
        problem.difficulty,
        problem.importance,
        problem.answer_mode,
        " ".join(problem.topics),
        " ".join(problem.tags),
        problem.statement,
        " ".join(problem.constraints),
        " ".join(example_text),
    ]
    return "\n".join(part for part in parts if part.strip())


def row_to_search_result(row: sqlite3.Row, score: float) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "difficulty": row["difficulty"],
        "importance": row["importance"],
        "answer_mode": row["answer_mode"],
        "topics": json.loads(row["topics_json"]),
        "tags": json.loads(row["tags_json"]),
        "statement": row["statement"],
        "constraints": json.loads(row["constraints_json"]),
        "examples": json.loads(row["examples_json"]),
        "starter_code": json.loads(row["starter_code_json"]),
        "source_url": row["source_url"],
        "source_title": row["source_title"],
        "score": score,
    }


def dedupe_problems(problems: list[CodingProblem]) -> list[CodingProblem]:
    seen: set[str] = set()
    result: list[CodingProblem] = []
    for problem in problems:
        if problem.id in seen:
            continue
        seen.add(problem.id)
        result.append(problem)
    return result


def batched(items: list[CodingProblem], batch_size: int) -> list[list[CodingProblem]]:
    return [items[idx : idx + batch_size] for idx in range(0, len(items), batch_size)]


def _clean_filter(values: list[str] | None) -> set[str]:
    return {str(value).strip() for value in values or [] if str(value).strip()}


def _increment(target: dict, key: str) -> None:
    if key:
        target[key] = target.get(key, 0) + 1
