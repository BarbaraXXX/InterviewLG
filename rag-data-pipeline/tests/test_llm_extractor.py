from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag_data_pipeline.llm_extractor import extract_all, normalize_chunk_cards


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json_prompt(self, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        return self.payload


class LlmExtractorTest(unittest.TestCase):
    def test_normalize_chunk_cards_accepts_multiple_cards(self) -> None:
        chunk = sample_chunk()
        payload = {
            "cards": [
                {
                    "domain": ["agent"],
                    "topic": "📝 详细解析",
                    "question": "1. Agent 为什么需要 Planning？",
                    "answer_outline": ["复杂任务需要拆解", "规划能降低执行混乱"],
                    "followups": ["Planning 失败时怎么兜底？"],
                    "tags": ["planning"],
                    "difficulty": "mid",
                    "evidence_block_ids": ["b0001", "b0002"],
                    "followups_source": "generated",
                },
                {
                    "domain": ["agent"],
                    "topic": "Agent 记忆",
                    "question": "Agent Memory 有什么作用？",
                    "answer_outline": ["保存上下文"],
                    "followups": [],
                    "tags": ["memory"],
                    "difficulty": "junior",
                    "evidence_block_ids": ["b0003"],
                    "followups_source": "source",
                },
            ]
        }

        cards = normalize_chunk_cards(chunk, payload)

        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["question"], "Agent 为什么需要 Planning？")
        self.assertEqual(cards[0]["topic"], "Planning")
        self.assertEqual(cards[0]["evidence_block_ids"], ["b0001", "b0002"])

    def test_normalize_chunk_cards_rejects_cards_without_evidence(self) -> None:
        cards = normalize_chunk_cards(
            sample_chunk(),
            {"cards": [{"question": "Agent 是什么？", "evidence_block_ids": []}]},
        )

        self.assertEqual(cards, [])

    def test_extract_all_writes_public_and_audit_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunks_dir = root / "chunks"
            extracted_dir = root / "extracted"
            audit_dir = root / "audit"
            cache_dir = root / "cache"
            chunks_dir.mkdir()
            chunk = sample_chunk()
            (chunks_dir / "agent.jsonl").write_text(
                json.dumps(chunk, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            client = FakeClient(
                {
                    "cards": [
                        {
                            "domain": ["agent"],
                            "topic": "Agent Planning",
                            "question": "Agent 为什么需要 Planning？",
                            "answer_outline": ["复杂任务需要拆解"],
                            "followups": ["如何评估规划结果？"],
                            "tags": ["agent", "planning"],
                            "difficulty": "mid",
                            "evidence_block_ids": ["b0001"],
                            "followups_source": "generated",
                        }
                    ]
                }
            )

            stats = extract_all(chunks_dir, extracted_dir, audit_dir, cache_dir, client)
            public = json.loads((extracted_dir / "agent.jsonl").read_text(encoding="utf-8"))
            audit = json.loads((audit_dir / "agent.jsonl").read_text(encoding="utf-8"))

            self.assertEqual(stats["cards"], 1)
            self.assertEqual(stats["requested"], 1)
            self.assertEqual(client.calls, 1)
            self.assertNotIn("evidence_block_ids", public)
            self.assertEqual(audit["evidence_block_ids"], ["b0001"])


def sample_chunk() -> dict:
    return {
        "id": "chunk_1",
        "source_id": "agent",
        "source_url": "https://example.com/agent",
        "source_title": "Agent 面试题",
        "domain_hint": ["agent"],
        "tags_hint": ["agent"],
        "title_chain": ["Agent 面试题", "Planning"],
        "blocks": [
            {"id": "b0001", "kind": "heading", "level": 2, "text": "Planning"},
            {"id": "b0002", "kind": "paragraph", "level": 0, "text": "Agent 为什么需要 Planning？"},
            {"id": "b0003", "kind": "paragraph", "level": 0, "text": "Memory 用于保存上下文。"},
        ],
        "text": "[b0001] ## Planning\n[b0002] Agent 为什么需要 Planning？",
    }


if __name__ == "__main__":
    unittest.main()
