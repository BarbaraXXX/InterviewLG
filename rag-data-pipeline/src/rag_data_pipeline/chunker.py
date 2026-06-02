from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from rag_data_pipeline.extractor import is_structural_topic
from rag_data_pipeline.models import Block, NormalizedDocument


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    source_id: str
    source_url: str
    source_title: str
    domain_hint: list[str]
    tags_hint: list[str]
    title_chain: list[str]
    blocks: list[dict]
    text: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "domain_hint": self.domain_hint,
            "tags_hint": self.tags_hint,
            "title_chain": self.title_chain,
            "blocks": self.blocks,
            "text": self.text,
        }


def chunk_document(doc: NormalizedDocument, max_chars: int = 5200) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    heading_stack: dict[int, str] = {}
    current_blocks: list[dict] = []
    current_title_chain: list[str] = []

    def active_title_chain() -> list[str]:
        return [heading_stack[level] for level in sorted(heading_stack) if not is_structural_topic(heading_stack[level])]

    def flush() -> None:
        nonlocal current_blocks, current_title_chain
        if not has_content(current_blocks):
            current_blocks = []
            current_title_chain = []
            return
        chunks.append(make_chunk(doc, current_title_chain, current_blocks))
        current_blocks = []
        current_title_chain = []

    for idx, block in enumerate(doc.blocks):
        block_row = block_to_row(idx, block)
        if block.kind == "heading":
            if block.level <= 2 and current_blocks:
                flush()
            heading_stack = {level: text for level, text in heading_stack.items() if level < block.level}
            heading_stack[block.level] = block.text
            if not current_blocks:
                current_title_chain = active_title_chain()
            current_blocks.append(block_row)
            continue

        if current_blocks and blocks_char_count(current_blocks) + len(block.text) > max_chars:
            flush()
        if not current_blocks:
            current_title_chain = active_title_chain()
        current_blocks.append(block_row)

    flush()
    return chunks


def block_to_row(idx: int, block: Block) -> dict:
    return {
        "id": f"b{idx:04d}",
        "kind": block.kind,
        "level": block.level,
        "text": block.text,
    }


def has_content(blocks: list[dict]) -> bool:
    return any(block.get("kind") != "heading" and str(block.get("text", "")).strip() for block in blocks)


def blocks_char_count(blocks: list[dict]) -> int:
    return sum(len(str(block.get("text", ""))) for block in blocks)


def make_chunk(doc: NormalizedDocument, title_chain: list[str], blocks: list[dict]) -> DocumentChunk:
    start_id = blocks[0]["id"] if blocks else "b0000"
    end_id = blocks[-1]["id"] if blocks else "b0000"
    text = render_chunk_text(title_chain, blocks)
    digest = hashlib.sha1(
        f"{doc.source_url}\n{start_id}\n{end_id}\n{'/'.join(title_chain)}".encode("utf-8")
    ).hexdigest()[:16]
    return DocumentChunk(
        id=f"chunk_{digest}",
        source_id=doc.source_id,
        source_url=doc.source_url,
        source_title=doc.source_title,
        domain_hint=doc.domain,
        tags_hint=doc.tags,
        title_chain=title_chain,
        blocks=blocks,
        text=text,
    )


def render_chunk_text(title_chain: list[str], blocks: list[dict]) -> str:
    lines: list[str] = []
    if title_chain:
        lines.append("标题链：" + " > ".join(title_chain))
    for block in blocks:
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        kind = block.get("kind")
        level = int(block.get("level") or 0)
        prefix = "#" * level + " " if kind == "heading" and level > 0 else ""
        lines.append(f"[{block['id']}] {prefix}{text}")
    return "\n".join(lines).strip()


def write_chunks(source_id: str, chunks: list[DocumentChunk], chunks_dir: Path) -> None:
    chunks_dir.mkdir(parents=True, exist_ok=True)
    path = chunks_dir / f"{source_id}.jsonl"
    lines = [json.dumps(chunk.to_dict(), ensure_ascii=False) for chunk in chunks]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_chunks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_chunks_dir(chunks_dir: Path) -> list[dict]:
    rows: list[dict] = []
    if not chunks_dir.exists():
        return rows
    for path in sorted(chunks_dir.glob("*.jsonl")):
        rows.extend(read_chunks(path))
    return rows
