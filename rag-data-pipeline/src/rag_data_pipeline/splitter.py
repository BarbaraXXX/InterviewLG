from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_jsonl_dir(directory: Path) -> list[dict]:
    rows: list[dict] = []
    if not directory.exists():
        return rows
    for path in sorted(directory.glob("*.jsonl")):
        rows.extend(read_jsonl(path))
    return rows


def dedupe_cards(cards: Iterable[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for card in cards:
        key = "".join(str(card.get("question", "")).lower().split())
        source = str(card.get("source_url", ""))
        dedupe_key = f"{source}|{key}"
        if not key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(card)
    return result


def public_card(card: dict) -> dict:
    return {
        "id": card.get("id", ""),
        "domain": list(card.get("domain") or []),
        "topic": card.get("topic", ""),
        "question": card.get("question", ""),
        "answer_outline": list(card.get("answer_outline") or []),
        "followups": list(card.get("followups") or []),
        "tags": list(card.get("tags") or []),
        "difficulty": card.get("difficulty", ""),
        "source_url": card.get("source_url", ""),
        "source_title": card.get("source_title", ""),
    }


def primary_domain(card: dict) -> str:
    domain = card.get("domain") or []
    if isinstance(domain, list) and domain:
        return safe_filename(str(domain[0]))
    return "uncategorized"


def safe_filename(value: str) -> str:
    lowered = value.strip().lower()
    safe = re.sub(r"[^a-z0-9_-]+", "_", lowered)
    return safe.strip("_") or "uncategorized"


def write_domain_splits(cards: Iterable[dict], output_dir: Path, source: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_file in output_dir.glob("*.jsonl"):
        old_file.unlink()

    grouped: dict[str, list[dict]] = {}
    for card in dedupe_cards(public_card(item) for item in cards):
        grouped.setdefault(primary_domain(card), []).append(card)

    files: dict[str, dict] = {}
    for domain, rows in sorted(grouped.items()):
        path = output_dir / f"{domain}.jsonl"
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
            encoding="utf-8",
        )
        files[path.name] = {"domain": domain, "cards": len(rows)}

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": source,
        "total_cards": sum(item["cards"] for item in files.values()),
        "files": files,
    }
    (output_dir.parent / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest

