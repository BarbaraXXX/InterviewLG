from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

from rag_data_pipeline.models import Block

SKIP_TAGS = {"script", "style", "svg", "noscript", "iframe"}
BLOCK_TAGS = {"p", "li", "blockquote", "pre"}
HEADING_TAGS = {f"h{i}": i for i in range(1, 7)}


def clean_text(value: str) -> str:
    text = unescape(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("\u200b", "")
    return text


class HtmlBlockParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.title = ""
        self._skip_depth = 0
        self._current_kind: str | None = None
        self._current_level = 0
        self._current_tag: str | None = None
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
            self._title_parts = []
            return
        if tag == "br" and self._current_kind:
            self._parts.append("\n")
            return
        if self._current_kind:
            return
        if tag in HEADING_TAGS:
            self._begin_block("heading", tag, HEADING_TAGS[tag])
        elif tag in BLOCK_TAGS:
            self._begin_block("code" if tag == "pre" else tag, tag, 0)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
            self.title = clean_text(" ".join(self._title_parts))
            return
        if self._current_tag == tag:
            self._end_block()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._current_kind:
            self._parts.append(data)

    def _begin_block(self, kind: str, tag: str, level: int) -> None:
        self._current_kind = kind
        self._current_tag = tag
        self._current_level = level
        self._parts = []

    def _end_block(self) -> None:
        text = clean_text(" ".join(self._parts))
        if text:
            self.blocks.append(Block(kind=self._current_kind or "paragraph", text=text, level=self._current_level))
        self._current_kind = None
        self._current_tag = None
        self._current_level = 0
        self._parts = []


def parse_html_blocks(html: str) -> tuple[str, list[Block]]:
    parser = HtmlBlockParser()
    parser.feed(html)
    return parser.title, parser.blocks

