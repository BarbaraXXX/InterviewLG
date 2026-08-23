from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from rag_data_pipeline.env import DeepSeekSettings
from rag_data_pipeline.extractor import is_structural_topic
from rag_data_pipeline.splitter import read_jsonl_dir

ALLOWED_DIFFICULTIES = {"", "junior", "mid", "senior"}


SYSTEM_PROMPT = """你是中文技术面试 RAG 数据清洗助手。
你的任务是把来源面试资料规范化为 QuestionCard。
要求：
1. 只能基于输入问题、答案原文和来源信息整理，不要编造事实。
2. 可以生成真实面试风格的追问，但追问必须围绕该问题的知识点和工程场景。
3. 输出必须是 JSON object，不要 Markdown，不要解释。
4. 字段只能包含：domain, topic, question, answer_outline, followups, tags, difficulty。
5. difficulty 只能是 junior、mid、senior 或空字符串。
"""


def build_user_prompt(card: dict) -> str:
    payload = {
        "domain": card.get("domain", []),
        "topic": card.get("topic", ""),
        "question": card.get("question", ""),
        "answer_text": card.get("answer_text", ""),
        "answer_outline": card.get("answer_outline", []),
        "followups": card.get("followups", []),
        "tags": card.get("tags", []),
        "source_title": card.get("source_title", ""),
        "source_url": card.get("source_url", ""),
    }
    return (
        "请规范化下面这条 QuestionCard。\n"
        "answer_outline 输出 3-6 条中文要点；如果原文不足，基于问题和已有信息给出简洁要点。\n"
        "followups 输出 2-5 条中文技术面试追问。\n"
        "tags 输出 3-10 个小写标签。\n"
        "question 可以轻微清洗编号和空格，但不能改变含义。\n"
        f"输入：{json.dumps(payload, ensure_ascii=False)}"
    )


class DeepSeekClient:
    def __init__(self, settings: DeepSeekSettings, timeout: int = 60) -> None:
        self.settings = settings
        self.timeout = timeout

    def complete_json(self, card: dict) -> dict:
        return self.complete_json_prompt(SYSTEM_PROMPT, build_user_prompt(card))

    def complete_json_prompt(self, system_prompt: str, user_prompt: str) -> dict:
        body = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        request = Request(
            f"{self.settings.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek request failed: HTTP {exc.code}: {detail}") from exc
        content = payload["choices"][0]["message"].get("content", "")
        try:
            return parse_json_content(content)
        except ValueError as exc:
            raise RuntimeError(f"DeepSeek returned non-JSON content: {content[:500]!r}") from exc


def enrich_all(
    extracted_dir: Path,
    enriched_dir: Path,
    cache_dir: Path,
    client: DeepSeekClient,
    *,
    limit: int = 0,
    force: bool = False,
) -> dict[str, int]:
    enriched_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cards = read_jsonl_dir(extracted_dir)
    if limit > 0:
        cards = cards[:limit]

    enriched: list[dict] = []
    failures: list[dict] = []
    requested = 0
    reused = 0
    for card in cards:
        cache_path = cache_dir / f"{card['id']}.json"
        error_path = cache_dir / f"{card['id']}.error.json"
        if cache_path.exists() and not force:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            normalized = normalize_llm_card(card, cached)
            if normalized != cached:
                cache_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
            reused += 1
        else:
            try:
                normalized = normalize_llm_card(card, client.complete_json(card))
            except Exception as exc:
                failure = {
                    "id": card.get("id", ""),
                    "question": card.get("question", ""),
                    "source_url": card.get("source_url", ""),
                    "error": str(exc),
                }
                failures.append(failure)
                error_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
                normalized = normalize_llm_card(card, {})
            else:
                requested += 1
            cache_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        enriched.append({**card, **normalized})

    output = enriched_dir / "question_cards.jsonl"
    output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in enriched) + ("\n" if enriched else ""),
        encoding="utf-8",
    )
    if failures:
        (enriched_dir / "failures.json").write_text(
            json.dumps(failures, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        failure_path = enriched_dir / "failures.json"
        if failure_path.exists():
            failure_path.unlink()
    return {"cards": len(enriched), "requested": requested, "reused": reused, "failed": len(failures)}


def parse_json_content(content: str) -> dict:
    text = content.strip()
    if not text:
        raise ValueError("empty content")
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object found")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("JSON content is not an object")
    return value


def normalize_llm_card(original: dict, candidate: dict) -> dict:
    domain = candidate.get("domain")
    if not isinstance(domain, list) or not all(isinstance(item, str) for item in domain):
        domain = original.get("domain", [])
    difficulty = candidate.get("difficulty", original.get("difficulty", ""))
    if difficulty not in ALLOWED_DIFFICULTIES:
        difficulty = ""
    topic = as_string(candidate.get("topic", original.get("topic", "")))
    if is_structural_topic(topic):
        topic = as_string(original.get("topic", ""))
    return {
        "domain": domain,
        "topic": topic,
        "question": as_string(candidate.get("question", original.get("question", ""))),
        "answer_outline": as_string_list(candidate.get("answer_outline")),
        "followups": as_string_list(candidate.get("followups")),
        "tags": dedupe_strings(as_string_list(candidate.get("tags", original.get("tags", []))))[:12],
        "difficulty": difficulty,
    }


def as_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
    return result


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
