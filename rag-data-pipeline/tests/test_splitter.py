from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag_data_pipeline.splitter import write_domain_splits


class SplitterTest(unittest.TestCase):
    def test_write_domain_splits_by_primary_domain(self) -> None:
        cards = [
            {
                "id": "1",
                "domain": ["backend", "redis"],
                "topic": "Redis",
                "question": "Redis 为什么快？",
                "answer_outline": ["基于内存"],
                "followups": ["单线程为什么快？"],
                "tags": ["redis"],
                "difficulty": "mid",
                "source_url": "https://example.com/a",
                "source_title": "A",
            },
            {
                "id": "2",
                "domain": ["cpp"],
                "topic": "C++",
                "question": "什么是虚函数？",
                "answer_outline": ["支持多态"],
                "followups": [],
                "tags": ["cpp"],
                "difficulty": "",
                "source_url": "https://example.com/b",
                "source_title": "B",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "question_cards"
            manifest = write_domain_splits(cards, output_dir, source="test")

            self.assertEqual(manifest["total_cards"], 2)
            self.assertTrue((output_dir / "backend.jsonl").exists())
            self.assertTrue((output_dir / "cpp.jsonl").exists())
            backend = json.loads((output_dir / "backend.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertNotIn("answer_text", backend)


if __name__ == "__main__":
    unittest.main()

