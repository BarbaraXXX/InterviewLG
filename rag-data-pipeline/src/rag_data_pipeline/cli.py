from __future__ import annotations

import argparse
from pathlib import Path

from rag_data_pipeline.pipeline import Pipeline

DEFAULT_SOURCES = Path("config/xiaolin_sources.json")
DEFAULT_DATA_DIR = Path("data")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build QuestionCard JSONL from interview pages.")
    parser.add_argument(
        "command",
        choices=["fetch", "prepare", "extract", "build", "enrich", "split", "all"],
        help=(
            "fetch raw pages, prepare cleaned chunks, extract cards with DeepSeek, "
            "optionally enrich existing cards, split output, or run all stages"
        ),
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=DEFAULT_SOURCES,
        help="source config JSON file",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="directory for raw, normalized, extracted, and output data",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="fetch pages again even when cached raw HTML exists",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/output/question_cards"),
        help="final directory for domain-split JSONL files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="limit number of chunks to extract or cards to enrich; 0 means no limit",
    )
    parser.add_argument(
        "--force-extract",
        action="store_true",
        help="ignore cached LLM extraction responses and request DeepSeek again",
    )
    parser.add_argument(
        "--force-enrich",
        action="store_true",
        help="ignore cached LLM responses and request DeepSeek again",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = Pipeline(
        sources_path=args.sources,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
    )
    if args.command in {"fetch", "all"}:
        pipeline.fetch_all(refresh=args.refresh)
    if args.command in {"prepare"}:
        stats = pipeline.prepare_all()
        print(f"prepared {stats['chunks']} chunks")
    if args.command in {"extract"}:
        stats = pipeline.extract(limit=args.limit, force=args.force_extract)
        print(
            f"extracted {stats['cards']} cards from {stats['chunks']} chunks "
            f"({stats['requested']} requested, {stats['reused']} cached, {stats['failed']} failed)"
        )
    if args.command in {"build", "all"}:
        stats = pipeline.build_all(limit=args.limit, force_extract=args.force_extract)
        print(
            f"built {stats['cards']} extracted cards from {stats['chunks']} chunks "
            f"({stats['requested']} requested, {stats['reused']} cached, {stats['failed']} failed)"
        )
    if args.command in {"enrich"}:
        stats = pipeline.enrich(limit=args.limit, force=args.force_enrich)
        print(
            f"enriched {stats['cards']} cards "
            f"({stats['requested']} requested, {stats['reused']} cached, {stats['failed']} failed)"
        )
    if args.command in {"split", "all"}:
        manifest = pipeline.split()
        print(f"wrote {manifest['total_cards']} cards into {pipeline.output_dir}")
    return 0
