from __future__ import annotations

import unittest

from rag_data_pipeline.chunker import chunk_document
from rag_data_pipeline.models import Block, NormalizedDocument


class ChunkerTest(unittest.TestCase):
    def test_chunk_document_preserves_block_ids_and_title_chain(self) -> None:
        doc = NormalizedDocument(
            source_id="agent",
            source_url="https://example.com/agent",
            source_title="Agent 面试题",
            domain=["agent"],
            tags=["agent"],
            blocks=[
                Block(kind="heading", text="Agent 面试题", level=1),
                Block(kind="heading", text="Planning", level=2),
                Block(kind="paragraph", text="Agent 为什么需要 Planning？因为复杂任务需要拆解。"),
                Block(kind="heading", text="Memory", level=2),
                Block(kind="paragraph", text="Memory 用于保存长期偏好和短期上下文。"),
            ],
        )

        chunks = chunk_document(doc, max_chars=1000)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].title_chain, ["Agent 面试题", "Planning"])
        self.assertEqual(chunks[0].blocks[0]["id"], "b0001")
        self.assertIn("[b0002]", chunks[0].text)


if __name__ == "__main__":
    unittest.main()
