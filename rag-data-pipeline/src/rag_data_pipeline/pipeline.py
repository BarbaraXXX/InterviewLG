from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from rag_data_pipeline.chunker import chunk_document, write_chunks
from rag_data_pipeline.enricher import DeepSeekClient, enrich_all
from rag_data_pipeline.env import load_deepseek_settings
from rag_data_pipeline.html_blocks import parse_html_blocks
from rag_data_pipeline.llm_extractor import extract_all
from rag_data_pipeline.models import Block, NormalizedDocument, Source
from rag_data_pipeline.splitter import read_jsonl, read_jsonl_dir, write_domain_splits

USER_AGENT = "InterviewLG-RAG-Pipeline/0.1 (+offline data preparation)"


class Pipeline:
    def __init__(self, sources_path: Path, data_dir: Path, output_dir: Path) -> None:
        self.root = Path.cwd()
        self.sources_path = self._resolve(sources_path)
        self.data_dir = self._resolve(data_dir)
        self.output_dir = self._resolve(output_dir)
        self.raw_dir = self.data_dir / "raw"
        self.normalized_dir = self.data_dir / "normalized"
        self.chunks_dir = self.data_dir / "chunks"
        self.extracted_dir = self.data_dir / "extracted"
        self.extracted_audit_dir = self.data_dir / "extracted_audit"
        self.enriched_dir = self.data_dir / "enriched"
        self.llm_cache_dir = self.data_dir / "llm_cache"
        self.llm_extract_cache_dir = self.data_dir / "llm_extract_cache"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_all(self, refresh: bool = False) -> None:
        base_sources = self.load_sources()
        for source in base_sources:
            self.fetch_source(source, refresh=refresh)
        base_ids = {source.id for source in base_sources}
        for source in self.expand_sources(base_sources):
            if source.id in base_ids:
                continue
            self.fetch_source(source, refresh=refresh)

    def fetch_source(self, source: Source, refresh: bool = False) -> None:
        metadata_path = self.raw_dir / source.id / "latest.json"
        if metadata_path.exists() and not refresh:
            print(f"cached {source.id}")
            return
        html, content_type = fetch_url(source.url)
        raw_source_dir = self.raw_dir / source.id
        raw_source_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        html_path = raw_source_dir / f"{digest}.html"
        html_path.write_text(html, encoding="utf-8")
        metadata = {
            "source": source.__dict__,
            "content_type": content_type,
            "sha256": digest,
            "html_path": str(html_path.relative_to(self.data_dir)),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"fetched {source.id}")

    def prepare_all(self) -> dict[str, int]:
        clear_files(self.normalized_dir, "*.json")
        clear_files(self.chunks_dir, "*.jsonl")
        chunk_count = 0
        for source in self.expand_sources(self.load_sources()):
            html = self.load_cached_html(source)
            doc = self.normalize(source, html)
            self.write_normalized(doc)
            if not source.extract:
                print(f"skipped {source.id}: chunking disabled")
                continue
            chunks = chunk_document(doc)
            write_chunks(source.id, chunks, self.chunks_dir)
            chunk_count += len(chunks)
            print(f"prepared {source.id}: {len(chunks)} chunks")
        return {"chunks": chunk_count}

    def extract(self, limit: int = 0, force: bool = False) -> dict[str, int]:
        settings = load_deepseek_settings(self.root)
        client = DeepSeekClient(settings)
        return extract_all(
            self.chunks_dir,
            self.extracted_dir,
            self.extracted_audit_dir,
            self.llm_extract_cache_dir,
            client,
            limit=limit,
            force=force,
        )

    def build_all(self, limit: int = 0, force_extract: bool = False) -> dict[str, int]:
        prepare_stats = self.prepare_all()
        extract_stats = self.extract(limit=limit, force=force_extract)
        return {**prepare_stats, **extract_stats}

    def enrich(self, limit: int = 0, force: bool = False) -> dict[str, int]:
        settings = load_deepseek_settings(self.root)
        client = DeepSeekClient(settings)
        return enrich_all(
            self.extracted_dir,
            self.enriched_dir,
            self.llm_cache_dir,
            client,
            limit=limit,
            force=force,
        )

    def split(self, prefer_enriched: bool = True) -> dict:
        enriched_file = self.enriched_dir / "question_cards.jsonl"
        extracted_cards = read_jsonl_dir(self.extracted_dir)
        if prefer_enriched and enriched_file.exists():
            enriched_cards = read_jsonl(enriched_file)
            enriched_is_current = enriched_file.stat().st_mtime >= newest_mtime(self.extracted_dir)
            if enriched_is_current and len(enriched_cards) >= len(extracted_cards):
                cards = enriched_cards
                source = "enriched"
            elif not enriched_is_current:
                cards = extracted_cards
                source = "extracted (enriched stale)"
            else:
                cards = extracted_cards
                source = f"extracted (enriched incomplete: {len(enriched_cards)}/{len(extracted_cards)})"
        else:
            cards = extracted_cards
            source = "extracted"
        return write_domain_splits(cards, self.output_dir, source=source)

    def normalize(self, source: Source, html: str) -> NormalizedDocument:
        title, blocks = parse_html_blocks(html)
        if source.adapter == "xiaolin":
            blocks = normalize_xiaolin_blocks(blocks)
        return NormalizedDocument(
            source_id=source.id,
            source_url=source.url,
            source_title=title or source.id,
            domain=source.domain,
            tags=source.tags,
            blocks=blocks,
        )

    def write_normalized(self, doc: NormalizedDocument) -> None:
        self.normalized_dir.mkdir(parents=True, exist_ok=True)
        path = self.normalized_dir / f"{doc.source_id}.json"
        data = {
            "source_id": doc.source_id,
            "source_url": doc.source_url,
            "source_title": doc.source_title,
            "domain": doc.domain,
            "tags": doc.tags,
            "blocks": [block.__dict__ for block in doc.blocks],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_extracted(self, source_id: str, cards) -> None:
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        path = self.extracted_dir / f"{source_id}.jsonl"
        lines = [json.dumps(card.to_extracted_dict(), ensure_ascii=False) for card in cards]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def load_cached_html(self, source: Source) -> str:
        metadata_path = self.raw_dir / source.id / "latest.json"
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"raw cache missing for {source.id}; run `python3 run.py fetch` first"
            )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        html_path = self.data_dir / metadata["html_path"]
        return html_path.read_text(encoding="utf-8")

    def load_sources(self) -> list[Source]:
        data = json.loads(self.sources_path.read_text(encoding="utf-8"))
        return [Source(**item) for item in data.get("sources", [])]

    def expand_sources(self, base_sources: list[Source]) -> list[Source]:
        result: list[Source] = []
        by_url = {source.url.rstrip("/"): source for source in base_sources}
        for source in base_sources:
            result.append(source)
            if not source.discover_prefixes:
                continue
            try:
                html = self.load_cached_html(source)
            except FileNotFoundError:
                continue
            for url in discover_links(source.url, html, source.discover_prefixes):
                key = url.rstrip("/")
                if key in by_url:
                    continue
                by_url[key] = Source(
                    id=discovered_source_id(source.id, url),
                    url=url,
                    adapter=source.adapter,
                    extract=True,
                    domain=source.domain,
                    tags=[*source.tags, "discovered"],
                )
                result.append(by_url[key])
        return result

    def _resolve(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.root / path


def fetch_url(url: str) -> tuple[str, str]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
    return raw.decode("utf-8", errors="replace"), content_type


def clear_files(directory: Path, pattern: str) -> None:
    if not directory.exists():
        return
    for path in directory.glob(pattern):
        path.unlink()


def newest_mtime(directory: Path) -> float:
    if not directory.exists():
        return 0
    mtimes = [path.stat().st_mtime for path in directory.glob("*.jsonl")]
    return max(mtimes, default=0)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in {"a", "link"}:
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self.hrefs.append(href)


def discover_links(base_url: str, html: str, prefixes: list[str]) -> list[str]:
    parser = LinkParser()
    parser.feed(html)
    seen: set[str] = set()
    result: list[str] = []
    base_host = urlparse(base_url).netloc
    for href in parser.hrefs:
        if href.startswith("#"):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc != base_host:
            continue
        if not any(parsed.path.startswith(prefix) for prefix in prefixes):
            continue
        clean_url = parsed._replace(fragment="", query="").geturl()
        if clean_url.rstrip("/") == base_url.rstrip("/"):
            continue
        if clean_url not in seen:
            seen.add(clean_url)
            result.append(clean_url)
    return sorted(result)


def discovered_source_id(parent_id: str, url: str) -> str:
    parsed = urlparse(url)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", parsed.path.strip("/")).strip("_")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{parent_id}_{slug}_{digest}"[:120]


def normalize_xiaolin_blocks(blocks: list[Block]) -> list[Block]:
    start = 0
    for idx, block in enumerate(blocks):
        if block.kind == "heading" and block.level == 1:
            start = idx
            break
    result: list[Block] = []
    for block in blocks[start:]:
        text = block.text.strip()
        if text.startswith(("上次更新", "上一篇", "下一篇", "关注小林的公众号")):
            break
        if text in {"首页", "目录", "侧边栏", "夜间", "技术群"}:
            continue
        if text.startswith("Image:"):
            continue
        result.append(block)
    return result
