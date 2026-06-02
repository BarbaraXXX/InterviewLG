from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from rag_data_pipeline.enricher import enrich_all, normalize_llm_card, parse_json_content


class FailingClient:
    def complete_json(self, card: dict) -> dict:
        raise AssertionError("cached enrichment should not call the client")


class EnricherTest(unittest.TestCase):
    def test_normalize_llm_card_preserves_safe_defaults(self) -> None:
        original = {
            "domain": ["backend", "redis"],
            "topic": "Redis",
            "question": "Redis 为什么快？",
            "tags": ["redis"],
            "difficulty": "",
        }
        candidate = {
            "domain": "backend",
            "topic": "Redis 性能",
            "question": "Redis 为什么这么快？",
            "answer_outline": ["基于内存", "IO 多路复用"],
            "followups": ["Redis 单线程为什么还能快？"],
            "tags": ["redis", "performance", "redis"],
            "difficulty": "expert",
        }

        normalized = normalize_llm_card(original, candidate)

        self.assertEqual(normalized["domain"], ["backend", "redis"])
        self.assertEqual(normalized["difficulty"], "")
        self.assertEqual(normalized["tags"], ["redis", "performance"])
        self.assertEqual(normalized["answer_outline"], ["基于内存", "IO 多路复用"])

    def test_normalize_llm_card_rejects_structural_topic(self) -> None:
        original = {
            "domain": ["llm"],
            "topic": "如何写好 Prompt？分享下 Prompt 工程实践经验？",
            "question": "为什么 Prompt 的好坏能决定效果的上限？",
            "tags": ["prompt"],
            "difficulty": "",
        }
        candidate = {
            "topic": "📝 详细解析",
            "question": "为什么 Prompt 的好坏能决定效果的上限？",
            "answer_outline": ["输入质量决定输出质量"],
            "followups": ["如何验证 Prompt 效果？"],
            "tags": ["prompt", "llm"],
            "difficulty": "mid",
        }

        normalized = normalize_llm_card(original, candidate)

        self.assertEqual(normalized["topic"], "如何写好 Prompt？分享下 Prompt 工程实践经验？")

    def test_enrich_all_normalizes_cached_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extracted_dir = root / "extracted"
            enriched_dir = root / "enriched"
            cache_dir = root / "cache"
            extracted_dir.mkdir()
            cache_dir.mkdir()
            card = {
                "id": "card-1",
                "domain": ["llm"],
                "topic": "如何写好 Prompt？分享下 Prompt 工程实践经验？",
                "question": "为什么 Prompt 的好坏能决定效果的上限？",
                "answer_outline": [],
                "followups": [],
                "tags": ["prompt"],
                "difficulty": "",
                "source_url": "https://example.com/prompt",
                "source_title": "Prompt",
            }
            cached = {
                "domain": ["llm"],
                "topic": "📝 详细解析",
                "question": card["question"],
                "answer_outline": ["输入质量决定输出质量"],
                "followups": ["如何验证 Prompt 效果？"],
                "tags": ["prompt", "llm"],
                "difficulty": "mid",
            }
            (extracted_dir / "llm.jsonl").write_text(
                json.dumps(card, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (cache_dir / "card-1.json").write_text(
                json.dumps(cached, ensure_ascii=False),
                encoding="utf-8",
            )

            stats = enrich_all(extracted_dir, enriched_dir, cache_dir, FailingClient())
            enriched = json.loads((enriched_dir / "question_cards.jsonl").read_text(encoding="utf-8"))
            rewritten_cache = json.loads((cache_dir / "card-1.json").read_text(encoding="utf-8"))

            self.assertEqual(stats["requested"], 0)
            self.assertEqual(enriched["topic"], card["topic"])
            self.assertEqual(rewritten_cache["topic"], card["topic"])

    def test_parse_json_content_accepts_code_fence(self) -> None:
        parsed = parse_json_content('```json\n{"difficulty":"mid"}\n```')
        self.assertEqual(parsed, {"difficulty": "mid"})

    def test_parse_json_content_extracts_object(self) -> None:
        parsed = parse_json_content('这里是结果：{"difficulty":"junior"}')
        self.assertEqual(parsed, {"difficulty": "junior"})


if __name__ == "__main__":
    unittest.main()
