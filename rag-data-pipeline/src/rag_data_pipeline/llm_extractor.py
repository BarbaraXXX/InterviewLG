from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Protocol

from rag_data_pipeline.chunker import read_chunks_dir
from rag_data_pipeline.enricher import ALLOWED_DIFFICULTIES, as_string, as_string_list, dedupe_strings
from rag_data_pipeline.extractor import is_structural_topic


class JsonPromptClient(Protocol):
    def complete_json_prompt(self, system_prompt: str, user_prompt: str) -> dict:
        ...


EXTRACT_SYSTEM_PROMPT = """你是中文技术面试 RAG 数据抽取助手。
你的任务是从给定的清洗正文 chunk 中抽取多个 QuestionCard。
要求：
1. question 必须能在正文中找到明确依据，不要凭空编造新问题。
2. topic 是知识点归类，不是解释段落标题；不要使用“简要回答”“详细解析”等结构标题。
3. answer_outline 基于正文整理 3-6 条中文要点。
4. followups 优先使用正文中真实出现的追问；如果没有，可以补充 2-5 条贴近真实面试的追问。
5. 必须填写 evidence_block_ids，指向支撑该 question/answer 的正文 block id。
6. 输出必须是 JSON object，格式为 {"cards": [...]}，不要 Markdown，不要解释。
7. 每个 card 字段只能包含：domain, topic, question, answer_outline, followups, tags, difficulty, evidence_block_ids, followups_source。
8. difficulty 只能是 junior、mid、senior 或空字符串。
9. followups_source 只能是 source、generated、mixed 或空字符串。
10. 单个 chunk 最多输出 10 条 card；没有可抽取问题时输出 {"cards": []}。
"""


def build_extract_prompt(chunk: dict) -> str:
    payload = {
        "source_url": chunk.get("source_url", ""),
        "source_title": chunk.get("source_title", ""),
        "domain_hint": chunk.get("domain_hint", []),
        "tags_hint": chunk.get("tags_hint", []),
        "title_chain": chunk.get("title_chain", []),
        "blocks": chunk.get("blocks", []),
        "text": chunk.get("text", ""),
    }
    return (
        "请从下面这个正文 chunk 中抽取 QuestionCard 数组。\n"
        "如果标题或段落只是解释结构，不要把它当作 topic。\n"
        "如果正文里的问题编号、标题编号存在，可以清理编号但不能改变问题含义。\n"
        f"输入：{json.dumps(payload, ensure_ascii=False)}"
    )


def extract_all(
    chunks_dir: Path,
    extracted_dir: Path,
    audit_dir: Path,
    cache_dir: Path,
    client: JsonPromptClient,
    *,
    limit: int = 0,
    force: bool = False,
) -> dict[str, int]:
    extracted_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    clear_jsonl(extracted_dir)
    clear_jsonl(audit_dir)

    chunks = read_chunks_dir(chunks_dir)
    if limit > 0:
        chunks = chunks[:limit]

    grouped_public: dict[str, list[dict]] = {}
    grouped_audit: dict[str, list[dict]] = {}
    failures: list[dict] = []
    requested = 0
    reused = 0

    for chunk in chunks:
        cache_path = cache_dir / f"{chunk['id']}.json"
        error_path = cache_dir / f"{chunk['id']}.error.json"
        if cache_path.exists() and not force:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            reused += 1
        else:
            try:
                payload = client.complete_json_prompt(
                    EXTRACT_SYSTEM_PROMPT,
                    build_extract_prompt(chunk),
                )
            except Exception as exc:
                failure = {
                    "chunk_id": chunk.get("id", ""),
                    "source_url": chunk.get("source_url", ""),
                    "error": str(exc),
                }
                failures.append(failure)
                error_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
                payload = {"cards": []}
            else:
                requested += 1
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        for card in normalize_chunk_cards(chunk, payload):
            grouped_public.setdefault(chunk["source_id"], []).append(public_card(card))
            grouped_audit.setdefault(chunk["source_id"], []).append(card)

    total_cards = 0
    for source_id, rows in grouped_public.items():
        rows = dedupe_dict_cards(rows)
        total_cards += len(rows)
        write_jsonl(extracted_dir / f"{source_id}.jsonl", rows)
    for source_id, rows in grouped_audit.items():
        write_jsonl(audit_dir / f"{source_id}.jsonl", dedupe_dict_cards(rows))

    failure_path = audit_dir / "failures.json"
    if failures:
        failure_path.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    elif failure_path.exists():
        failure_path.unlink()

    return {
        "chunks": len(chunks),
        "cards": total_cards,
        "requested": requested,
        "reused": reused,
        "failed": len(failures),
    }


def normalize_chunk_cards(chunk: dict, payload: dict) -> list[dict]:
    raw_cards = payload.get("cards", [])
    if not isinstance(raw_cards, list):
        return []
    valid_block_ids = {str(block.get("id", "")) for block in chunk.get("blocks", [])}
    rows: list[dict] = []
    for raw in raw_cards[:10]:
        if not isinstance(raw, dict):
            continue
        evidence_block_ids = [item for item in as_string_list(raw.get("evidence_block_ids")) if item in valid_block_ids]
        question = clean_question(as_string(raw.get("question")))
        if not question or not evidence_block_ids:
            continue
        domain = as_string_list(raw.get("domain")) or as_string_list(chunk.get("domain_hint"))
        topic = clean_topic(as_string(raw.get("topic")), chunk)
        difficulty = as_string(raw.get("difficulty"))
        if difficulty not in ALLOWED_DIFFICULTIES:
            difficulty = ""
        answer_outline = as_string_list(raw.get("answer_outline"))[:6]
        followups = as_string_list(raw.get("followups"))[:5]
        tags = dedupe_strings(as_string_list(raw.get("tags")) + as_string_list(chunk.get("tags_hint")))[:12]
        card_id = stable_llm_card_id(chunk.get("source_url", ""), question)
        rows.append(
            {
                "id": card_id,
                "domain": domain,
                "topic": topic,
                "question": question,
                "answer_outline": answer_outline,
                "followups": followups,
                "tags": tags,
                "difficulty": difficulty,
                "source_url": chunk.get("source_url", ""),
                "source_title": chunk.get("source_title", ""),
                "chunk_id": chunk.get("id", ""),
                "evidence_block_ids": evidence_block_ids,
                "followups_source": normalize_followups_source(raw.get("followups_source")),
            }
        )
    return rows


def clean_question(text: str) -> str:
    text = re.sub(r"^\d+[.、]\s*", "", text.strip())
    text = re.sub(r"\s+", " ", text)
    return text


def clean_topic(text: str, chunk: dict) -> str:
    text = re.sub(r"^\d+[.、]\s*", "", text.strip())
    text = re.sub(r"\s+", " ", text).strip()
    if text and not is_structural_topic(text) and not looks_like_explanation_heading(text):
        return text
    for title in reversed(as_string_list(chunk.get("title_chain"))):
        cleaned = re.sub(r"^\d+[.、]\s*", "", title.strip())
        if cleaned and not is_structural_topic(cleaned) and not looks_like_explanation_heading(cleaned):
            return cleaned
    return as_string(chunk.get("source_title", ""))


def looks_like_explanation_heading(text: str) -> bool:
    return "：" in text or ":" in text


def normalize_followups_source(value: object) -> str:
    source = as_string(value)
    return source if source in {"source", "generated", "mixed", ""} else ""


def public_card(card: dict) -> dict:
    return {
        "id": card.get("id", ""),
        "domain": card.get("domain", []),
        "topic": card.get("topic", ""),
        "question": card.get("question", ""),
        "answer_outline": card.get("answer_outline", []),
        "followups": card.get("followups", []),
        "tags": card.get("tags", []),
        "difficulty": card.get("difficulty", ""),
        "source_url": card.get("source_url", ""),
        "source_title": card.get("source_title", ""),
    }


def stable_llm_card_id(source_url: str, question: str) -> str:
    digest = hashlib.sha1(f"{source_url}\n{question}".encode("utf-8")).hexdigest()[:16]
    return f"qc_{digest}"


def dedupe_dict_cards(cards: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for card in cards:
        key = "".join(str(card.get("question", "")).lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(card)
    return result


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def clear_jsonl(directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.glob("*.jsonl"):
        path.unlink()
