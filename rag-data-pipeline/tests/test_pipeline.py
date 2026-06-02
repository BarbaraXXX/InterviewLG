from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from rag_data_pipeline.pipeline import Pipeline


class PipelineTest(unittest.TestCase):
    def test_split_falls_back_when_enriched_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources_path = root / "sources.json"
            data_dir = root / "data"
            output_dir = data_dir / "output" / "question_cards"
            extracted_dir = data_dir / "extracted"
            enriched_dir = data_dir / "enriched"
            extracted_dir.mkdir(parents=True)
            enriched_dir.mkdir(parents=True)
            sources_path.write_text('{"sources": []}', encoding="utf-8")

            cards = [
                {"id": "1", "domain": ["llm"], "topic": "A", "question": "Q1", "source_url": "u1"},
                {"id": "2", "domain": ["llm"], "topic": "B", "question": "Q2", "source_url": "u2"},
            ]
            (extracted_dir / "llm.jsonl").write_text(
                "\n".join(json.dumps(card, ensure_ascii=False) for card in cards) + "\n",
                encoding="utf-8",
            )
            (enriched_dir / "question_cards.jsonl").write_text(
                json.dumps(cards[0], ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            pipeline = Pipeline(sources_path=sources_path, data_dir=data_dir, output_dir=output_dir)
            manifest = pipeline.split()

            self.assertEqual(manifest["total_cards"], 2)
            self.assertTrue(manifest["source"].startswith("extracted"))

    def test_split_falls_back_when_enriched_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources_path = root / "sources.json"
            data_dir = root / "data"
            output_dir = data_dir / "output" / "question_cards"
            extracted_dir = data_dir / "extracted"
            enriched_dir = data_dir / "enriched"
            extracted_dir.mkdir(parents=True)
            enriched_dir.mkdir(parents=True)
            sources_path.write_text('{"sources": []}', encoding="utf-8")

            extracted = extracted_dir / "llm.jsonl"
            enriched = enriched_dir / "question_cards.jsonl"
            cards = [
                {"id": "1", "domain": ["llm"], "topic": "new", "question": "Q1", "source_url": "u1"},
            ]
            extracted.write_text(json.dumps(cards[0], ensure_ascii=False) + "\n", encoding="utf-8")
            enriched.write_text(json.dumps({**cards[0], "topic": "old"}, ensure_ascii=False) + "\n", encoding="utf-8")
            os.utime(enriched, (1, 1))
            os.utime(extracted, (2, 2))

            pipeline = Pipeline(sources_path=sources_path, data_dir=data_dir, output_dir=output_dir)
            manifest = pipeline.split()
            output = json.loads((output_dir / "llm.jsonl").read_text(encoding="utf-8"))

            self.assertEqual(manifest["source"], "extracted (enriched stale)")
            self.assertEqual(output["topic"], "new")


if __name__ == "__main__":
    unittest.main()
