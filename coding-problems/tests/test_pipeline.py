from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from coding_problem_pipeline.generator import build_user_prompt, generate_from_index_file
from coding_problem_pipeline.llm import parse_json_content
from coding_problem_pipeline.models import ProblemIndex, normalize_problem
from coding_problem_pipeline.validator import promote_valid, validate_file, validate_problem


class FakeClient:
    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "title": "反转链表",
            "difficulty": "easy",
            "importance": "hot100",
            "answer_mode": "core",
            "topics": ["linked_list", "pointer"],
            "tags": ["iteration"],
            "statement": "给定一个单链表头节点，请反转链表方向并返回新的头节点。",
            "constraints": ["链表长度范围为 0 到 5000"],
            "examples": [{"input": "head=[1,3,5]", "output": "[5,3,1]", "explanation": ""}],
            "starter_code": {"python": "class Solution:\n    def reverseList(self, head):\n        pass\n", "cpp": "class Solution {};"},
        }


class PipelineTests(unittest.TestCase):
    def test_parse_json_content_strips_fences(self) -> None:
        parsed = parse_json_content('```json\n{"ok": true}\n```')
        self.assertEqual(parsed, {"ok": True})

    def test_normalize_problem_uses_index_metadata(self) -> None:
        index = ProblemIndex.from_dict({
            "source": "leetcode_hot100",
            "source_id": "206",
            "slug": "reverse-linked-list",
            "title": "反转链表",
            "topics": ["linked_list"],
        })
        problem = normalize_problem(index, {"statement": "原创题面", "examples": [{"input": "x", "output": "y"}]})
        self.assertEqual(problem["id"], "leetcode_hot100_206_reverse_linked_list")
        self.assertEqual(problem["source_title"], "leetcode_hot100:206")

    def test_validate_problem_rejects_solution_fields(self) -> None:
        result = validate_problem({
            "id": "x",
            "title": "x",
            "difficulty": "easy",
            "importance": "hot100",
            "answer_mode": "core",
            "topics": ["array"],
            "statement": "题面",
            "examples": [{"input": "1", "output": "1"}],
            "starter_code": {"python": "pass"},
            "solution_outline": ["bad"],
        })
        self.assertFalse(result.ok)
        self.assertTrue(any("forbidden" in item for item in result.errors))

    def test_build_user_prompt_mentions_no_copy_rule(self) -> None:
        prompt = build_user_prompt(ProblemIndex.from_dict({"title": "两数之和", "source_id": "1"}))
        self.assertIn("不要复制", prompt)
        self.assertIn("starter_code", prompt)

    def test_generate_validate_and_promote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.jsonl"
            generated_path = root / "generated.jsonl"
            reviewed_path = root / "reviewed.jsonl"
            input_path.write_text(
                json.dumps(
                    {
                        "source": "leetcode_hot100",
                        "source_id": "206",
                        "slug": "reverse-linked-list",
                        "title": "反转链表",
                        "topics": ["linked_list"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = generate_from_index_file(
                root=root,
                input_path=input_path,
                output_path=generated_path,
                overwrite=True,
                client_factory=lambda: FakeClient(),
            )
            self.assertEqual(result["generated"], 1)

            validation = validate_file(generated_path)
            self.assertEqual(validation["valid"], 1)

            promoted = promote_valid(generated_path, reviewed_path, overwrite=True)
            self.assertEqual(promoted["promoted"], 1)
            row = json.loads(reviewed_path.read_text(encoding="utf-8").strip())
            self.assertNotIn("_review", row)


if __name__ == "__main__":
    unittest.main()
