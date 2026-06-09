from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coding_problem_pipeline.jsonl import read_jsonl, write_jsonl
from coding_problem_pipeline.models import ANSWER_MODES, DIFFICULTIES, IMPORTANCE_LEVELS, SUPPORTED_LANGUAGES


@dataclass(frozen=True)
class ValidationResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_problem(problem: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    _require_text(problem, "id", errors)
    _require_text(problem, "title", errors)
    _require_text(problem, "statement", errors)

    difficulty = str(problem.get("difficulty") or "").strip()
    importance = str(problem.get("importance") or "").strip()
    answer_mode = str(problem.get("answer_mode") or "").strip()
    if difficulty not in DIFFICULTIES:
        errors.append(f"difficulty must be one of {sorted(DIFFICULTIES)}")
    if importance not in IMPORTANCE_LEVELS:
        errors.append(f"importance must be one of {sorted(IMPORTANCE_LEVELS)}")
    if answer_mode not in ANSWER_MODES:
        errors.append(f"answer_mode must be one of {sorted(ANSWER_MODES)}")

    if not _string_list(problem.get("topics")):
        errors.append("topics must contain at least one item")
    if not _string_list(problem.get("constraints")):
        warnings.append("constraints is empty")

    examples = problem.get("examples")
    if not isinstance(examples, list) or not examples:
        errors.append("examples must contain at least one item")
    else:
        for idx, example in enumerate(examples, start=1):
            if not isinstance(example, dict):
                errors.append(f"examples[{idx}] must be an object")
                continue
            if not str(example.get("input") or "").strip():
                errors.append(f"examples[{idx}].input is required")
            if not str(example.get("output") or "").strip():
                errors.append(f"examples[{idx}].output is required")

    starter_code = problem.get("starter_code")
    if not isinstance(starter_code, dict) or not starter_code:
        errors.append("starter_code must contain at least one language template")
    else:
        languages = {str(language).strip().lower() for language in starter_code if str(starter_code[language]).strip()}
        unsupported = languages - SUPPORTED_LANGUAGES
        if unsupported:
            errors.append(f"starter_code contains unsupported languages: {sorted(unsupported)}")
        if not languages.intersection({"python", "cpp"}):
            errors.append("starter_code must contain python or cpp")
        if not {"python", "cpp"}.issubset(languages):
            warnings.append("starter_code should contain both python and cpp for first batch")

    forbidden_fields = {"solution", "solution_outline", "answer", "evaluation_points", "complexity"}
    present_forbidden = forbidden_fields.intersection(problem)
    if present_forbidden:
        errors.append(f"forbidden solution-like fields present: {sorted(present_forbidden)}")

    statement = str(problem.get("statement") or "")
    for marker in ["解法如下", "参考答案", "时间复杂度", "空间复杂度"]:
        if marker in statement:
            warnings.append(f"statement contains solution-like marker: {marker}")

    return ValidationResult(errors=errors, warnings=warnings)


def validate_file(input_path: Path) -> dict:
    rows = read_jsonl(input_path)
    seen_ids: set[str] = set()
    invalid: list[dict] = []
    warning_items: list[dict] = []
    for line_no, row in enumerate(rows, start=1):
        problem_id = str(row.get("id") or "").strip()
        result = validate_problem(row)
        errors = list(result.errors)
        if problem_id:
            if problem_id in seen_ids:
                errors.append("duplicate id")
            seen_ids.add(problem_id)
        if errors:
            invalid.append({"line": line_no, "id": problem_id, "errors": errors})
        if result.warnings:
            warning_items.append({"line": line_no, "id": problem_id, "warnings": result.warnings})
    return {
        "input": str(input_path),
        "count": len(rows),
        "valid": len(rows) - len(invalid),
        "invalid": invalid,
        "warnings": warning_items,
    }


def promote_valid(input_path: Path, output_path: Path, *, overwrite: bool = False) -> dict:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output_path}. Use --overwrite to replace it.")
    rows = read_jsonl(input_path)
    promoted = []
    rejected = []
    for line_no, row in enumerate(rows, start=1):
        clean_row = {key: value for key, value in row.items() if not key.startswith("_")}
        result = validate_problem(clean_row)
        if result.ok:
            promoted.append(clean_row)
        else:
            rejected.append({"line": line_no, "id": clean_row.get("id"), "errors": result.errors})
    write_jsonl(output_path, promoted)
    return {
        "input": str(input_path),
        "output": str(output_path),
        "promoted": len(promoted),
        "rejected": rejected,
    }


def _require_text(problem: dict[str, Any], field: str, errors: list[str]) -> None:
    if not str(problem.get(field) or "").strip():
        errors.append(f"{field} is required")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
