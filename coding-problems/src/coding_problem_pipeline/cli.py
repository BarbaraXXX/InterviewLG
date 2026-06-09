from __future__ import annotations

import argparse
import json
from pathlib import Path

from coding_problem_pipeline.generator import generate_from_index_file
from coding_problem_pipeline.validator import promote_valid, validate_file

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and validate CodingProblem JSONL files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate", help="Generate CodingProblem JSONL from an index JSONL.")
    gen.add_argument("--input", type=Path, default=ROOT / "data/input/hot100_index.jsonl")
    gen.add_argument("--output", type=Path, default=ROOT / "data/generated/hot100_generated.jsonl")
    gen.add_argument("--limit", type=int, default=None)
    gen.add_argument("--offset", type=int, default=0)
    gen.add_argument("--overwrite", action="store_true")

    val = subparsers.add_parser("validate", help="Validate a CodingProblem JSONL file.")
    val.add_argument("--input", type=Path, default=ROOT / "data/generated/hot100_generated.jsonl")

    promote = subparsers.add_parser("promote", help="Write valid generated items to reviewed JSONL.")
    promote.add_argument("--input", type=Path, default=ROOT / "data/generated/hot100_generated.jsonl")
    promote.add_argument("--output", type=Path, default=ROOT / "data/reviewed/hot100_reviewed.jsonl")
    promote.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()
    if args.command == "generate":
        result = generate_from_index_file(
            root=ROOT,
            input_path=args.input,
            output_path=args.output,
            limit=args.limit,
            offset=args.offset,
            overwrite=args.overwrite,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["errors"] else 0
    if args.command == "validate":
        result = validate_file(args.input)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["invalid"] else 0
    if args.command == "promote":
        result = promote_valid(args.input, args.output, overwrite=args.overwrite)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["rejected"] else 0
    return 1
