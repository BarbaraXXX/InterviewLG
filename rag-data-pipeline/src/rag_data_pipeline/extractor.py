from __future__ import annotations

import hashlib
import re

from rag_data_pipeline.models import Block, ExtractedCard, NormalizedDocument


QUESTION_PATTERNS = [
    r"[?？]$",
    r"^(Q|q|问|问题|面试题)[:：]",
    r"^(什么是|为什么|如何|怎么|怎样|讲讲|说说|介绍一下|谈谈|解释一下)",
    r"^.{2,50}(区别|差异|原理|流程|过程)$",
    r"^.{2,50}(如何实现|怎么实现)$",
]

STOP_PREFIXES = (
    "上一篇",
    "下一篇",
    "上次更新",
    "目录",
    "侧边栏",
    "关注小林",
)

STRUCTURAL_TOPICS = {
    "简要回答",
    "详细解析",
    "题目目录",
    "常见问题 FAQ",
    "结语",
}

KEYWORD_TAGS = {
    "redis": ["redis"],
    "mysql": ["mysql", "database"],
    "sql": ["sql", "database"],
    "tcp": ["tcp", "network"],
    "udp": ["udp", "network"],
    "http": ["http", "network"],
    "https": ["https", "network"],
    "索引": ["index", "database"],
    "事务": ["transaction", "database"],
    "锁": ["lock"],
    "mvcc": ["mvcc", "database"],
    "缓存": ["cache"],
    "指针": ["pointer", "cpp"],
    "引用": ["reference", "cpp"],
    "虚函数": ["virtual-function", "cpp"],
    "stl": ["stl", "cpp"],
    "agent": ["agent"],
    "rag": ["rag"],
    "mcp": ["mcp", "agent"],
    "function calling": ["function-calling", "agent"],
}


def is_question_anchor(text: str) -> bool:
    normalized, _ = split_inline_question(text)
    if len(normalized) < 4 or len(normalized) > 140:
        return False
    if any(normalized.startswith(prefix) for prefix in STOP_PREFIXES):
        return False
    if is_topic_colon_item(text):
        return True
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in QUESTION_PATTERNS)


def normalize_question(text: str) -> str:
    normalized, _ = split_inline_question(text)
    return normalized


def split_inline_question(text: str) -> tuple[str, str]:
    text = re.sub(r"^#+\s*", "", text.strip())
    text = re.sub(r"^(Q|q|问|问题|面试题)[:：]\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    match = re.match(r"^(.{2,45}?)[：:]\s*(.{8,})$", text)
    if match:
        topic = cleanup_inline_topic(match.group(1))
        answer = match.group(2).strip()
        if topic and len(topic) <= 45:
            return topic, answer
    return text, ""


def cleanup_inline_topic(text: str) -> str:
    text = re.sub(r"^[👉#\-\d.、\s]+", "", text.strip())
    return text.strip("《》「」[]【】 ")


def is_topic_colon_item(text: str) -> bool:
    question, answer = split_inline_question(text)
    if not answer:
        return False
    if question.startswith(("上一篇", "下一篇", "Java基础面试题 →")):
        return False
    return bool(
        re.search(
            r"(面试题|基础|原理|区别|机制|特性|场景|优化|架构|索引|事务|锁|缓存|Agent|RAG|MCP)",
            text,
            re.IGNORECASE,
        )
    )


def trim_document_blocks(blocks: list[Block]) -> list[Block]:
    start = 0
    for idx, block in enumerate(blocks):
        if block.kind == "heading" and block.level == 1:
            start = idx
            break
    trimmed: list[Block] = []
    for block in blocks[start:]:
        if block.text.startswith(STOP_PREFIXES):
            break
        trimmed.append(block)
    return trimmed


def extract_cards(doc: NormalizedDocument) -> list[ExtractedCard]:
    blocks = trim_document_blocks(doc.blocks)
    cards: list[ExtractedCard] = []
    heading_stack: dict[int, str] = {}
    page_topic = clean_topic_text(doc.source_title)
    current_question = ""
    current_topic = ""
    current_level = 0
    answer_blocks: list[Block] = []

    def close_current() -> None:
        nonlocal current_question, current_topic, current_level, answer_blocks
        if not current_question:
            return
        append_card(current_question, current_topic, answer_blocks)
        current_question = ""
        current_topic = ""
        current_level = 0
        answer_blocks = []

    def append_card(question: str, topic: str, blocks: list[Block]) -> None:
        answer_text = render_answer_text(blocks)
        outline = build_answer_outline(blocks)
        followups = extract_followups(blocks)
        tags = infer_tags(doc.tags, topic, question, answer_text)
        card_id = stable_card_id(doc.source_url, question)
        cards.append(
            ExtractedCard(
                id=card_id,
                domain=doc.domain,
                topic=topic,
                question=question,
                answer_text=answer_text,
                answer_outline=outline,
                followups=followups,
                tags=tags,
                difficulty="",
                source_url=doc.source_url,
                source_title=doc.source_title,
            )
        )

    for block in blocks:
        if block.kind == "heading":
            cleaned_heading = clean_topic_text(block.text)
            if block.level == 1 and cleaned_heading:
                page_topic = cleaned_heading
            is_question = is_question_anchor(block.text)
            if current_question and block.level <= current_level:
                close_current()
            if is_question:
                close_current()
                current_question = normalize_question(block.text)
                current_topic = nearest_topic(heading_stack) or page_topic
                current_level = block.level
            else:
                heading_stack = {level: text for level, text in heading_stack.items() if level < block.level}
                if not is_structural_topic(cleaned_heading):
                    heading_stack[block.level] = cleaned_heading
            continue

        if block.kind == "li" and is_question_anchor(block.text):
            close_current()
            question, inline_answer = split_inline_question(block.text)
            topic = nearest_topic(heading_stack) or page_topic
            if inline_answer:
                append_card(question, topic, [Block(kind="inline_answer", text=inline_answer)])
            else:
                current_question = question
                current_topic = topic
                current_level = 6
            continue

        if current_question:
            answer_blocks.append(block)

    close_current()
    return dedupe_cards(cards)


def nearest_topic(stack: dict[int, str]) -> str:
    for level in sorted(stack.keys(), reverse=True):
        topic = stack[level]
        if not is_question_anchor(topic) and not is_structural_topic(topic):
            return topic
    return ""


def clean_topic_text(text: str) -> str:
    cleaned = re.sub(r"^#+\s*", "", text.strip())
    cleaned = re.sub(r"^[\W_]+", "", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"^\d+[.、]\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_structural_topic(text: str) -> bool:
    cleaned = clean_topic_text(text)
    return cleaned in STRUCTURAL_TOPICS


def render_answer_text(blocks: list[Block], max_chars: int = 4000) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.kind == "code":
            continue
        text = block.text.strip()
        if text:
            parts.append(text)
        if sum(len(part) for part in parts) >= max_chars:
            break
    return "\n".join(parts)[:max_chars].strip()


def build_answer_outline(blocks: list[Block], max_items: int = 6) -> list[str]:
    outline: list[str] = []
    for block in blocks:
        if block.kind == "code":
            continue
        candidates = split_outline_candidates(block.text)
        for candidate in candidates:
            cleaned = cleanup_outline_item(candidate)
            if not cleaned:
                continue
            if block.kind != "inline_answer" and is_question_anchor(cleaned):
                continue
            if cleaned not in outline:
                outline.append(cleaned)
            if len(outline) >= max_items:
                return outline
    return outline


def split_outline_candidates(text: str) -> list[str]:
    if "；" in text:
        return [part for part in text.split("；") if part.strip()]
    parts = re.split(r"(?<=[。.!！])\s*", text)
    if len(parts) == 1 and len(parts[0]) > 180:
        return [parts[0][:180]]
    return parts


def cleanup_outline_item(text: str) -> str:
    text = re.sub(r"^[\-*•\d.、\s]+", "", text.strip())
    text = re.sub(r"\s+", " ", text)
    if len(text) < 8:
        return ""
    return text[:180]


def extract_followups(blocks: list[Block], max_items: int = 5) -> list[str]:
    followups: list[str] = []
    for block in blocks:
        if block.kind in {"code", "inline_answer"}:
            continue
        for part in re.split(r"[\n。；;]", block.text):
            text = extract_explicit_question(part)
            if is_question_anchor(text) and text not in followups:
                followups.append(text)
            if len(followups) >= max_items:
                return followups
    return followups


def extract_explicit_question(text: str) -> str:
    text = text.strip()
    if "？" in text:
        return normalize_question(text.split("？", 1)[0] + "？")
    if "?" in text:
        return normalize_question(text.split("?", 1)[0] + "?")
    return ""


def infer_tags(source_tags: list[str], topic: str, question: str, answer_text: str) -> list[str]:
    tags: list[str] = []
    for tag in source_tags:
        add_tag(tags, tag)
    haystack = f"{topic} {question} {answer_text[:800]}".lower()
    for keyword, inferred in KEYWORD_TAGS.items():
        if keyword.lower() in haystack:
            for tag in inferred:
                add_tag(tags, tag)
    return tags[:12]


def add_tag(tags: list[str], tag: str) -> None:
    value = tag.strip().lower()
    if value and value not in tags:
        tags.append(value)


def stable_card_id(source_url: str, question: str) -> str:
    digest = hashlib.sha1(f"{source_url}\n{question}".encode("utf-8")).hexdigest()[:16]
    return f"qc_{digest}"


def dedupe_cards(cards: list[ExtractedCard]) -> list[ExtractedCard]:
    seen: set[str] = set()
    result: list[ExtractedCard] = []
    for card in cards:
        key = re.sub(r"\s+", "", card.question.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(card)
    return result
