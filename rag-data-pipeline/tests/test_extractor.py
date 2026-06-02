from __future__ import annotations

import unittest

from rag_data_pipeline.extractor import extract_cards, extract_explicit_question, is_question_anchor
from rag_data_pipeline.html_blocks import parse_html_blocks
from rag_data_pipeline.models import NormalizedDocument


class ExtractorTest(unittest.TestCase):
    def test_detects_question_anchor(self) -> None:
        self.assertTrue(is_question_anchor("Redis 为什么这么快？"))
        self.assertTrue(is_question_anchor("讲讲 TCP 三次握手"))
        self.assertFalse(is_question_anchor("Redis 持久化"))
        self.assertTrue(is_question_anchor("String、StringBuffer、StringBuilder ：三者的区别和适用场景。"))

    def test_extract_explicit_followup_question(self) -> None:
        self.assertEqual(extract_explicit_question("为什么工具调用如此重要？因为它能访问外部工具。"), "为什么工具调用如此重要？")
        self.assertEqual(extract_explicit_question("这就是本质区别"), "")

    def test_extracts_heading_question_cards(self) -> None:
        html = """
        <html><head><title>Test Page</title></head><body>
          <nav><p>首页</p></nav>
          <h1>C++ 面试题</h1>
          <h2>C++基础</h2>
          <h3>指针和引用有什么区别？</h3>
          <p>指针可以为空，引用通常需要绑定对象。</p>
          <ul><li>指针可以重新指向其他对象。</li><li>引用初始化后不可重新绑定。</li></ul>
          <h3>虚函数表是什么？</h3>
          <p>虚函数表用于支持运行时多态。</p>
          <p>如果析构函数不是虚函数会怎么样？</p>
          <h2>上次更新: 2026-01-01</h2>
        </body></html>
        """
        title, blocks = parse_html_blocks(html)
        doc = NormalizedDocument(
            source_id="test",
            source_url="https://example.com/cpp.html",
            source_title=title,
            domain=["cpp"],
            tags=["cpp"],
            blocks=blocks,
        )
        cards = extract_cards(doc)

        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0].topic, "C++基础")
        self.assertEqual(cards[0].question, "指针和引用有什么区别？")
        self.assertIn("指针可以为空", cards[0].answer_outline[0])
        self.assertEqual(cards[1].followups, ["如果析构函数不是虚函数会怎么样？"])

    def test_extracts_inline_topic_list_item(self) -> None:
        html = """
        <html><head><title>Java</title></head><body>
          <h1>Java 面试题</h1>
          <h2>Java基础面试题</h2>
          <ul>
            <li>String、StringBuffer、StringBuilder ：三者的区别和适用场景，以及 String 不可变性的原理。</li>
          </ul>
        </body></html>
        """
        title, blocks = parse_html_blocks(html)
        doc = NormalizedDocument(
            source_id="java",
            source_url="https://example.com/java.html",
            source_title=title,
            domain=["java"],
            tags=["java"],
            blocks=blocks,
        )
        cards = extract_cards(doc)

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].question, "String、StringBuffer、StringBuilder")
        self.assertIn("三者的区别", cards[0].answer_outline[0])

    def test_skips_structural_answer_headings_as_topics(self) -> None:
        html = """
        <html><head><title>Prompt 工程实践经验</title></head><body>
          <h1>16. 如何写好 Prompt？分享下 Prompt 工程实践经验？</h1>
          <h2>💡 简要回答</h2>
          <p>Prompt 需要明确角色、任务、上下文和输出格式。</p>
          <h2>📝 详细解析</h2>
          <h3>为什么 Prompt 的好坏能决定效果的上限？</h3>
          <p>模型会强依赖输入中的约束和上下文。</p>
        </body></html>
        """
        title, blocks = parse_html_blocks(html)
        doc = NormalizedDocument(
            source_id="prompt",
            source_url="https://example.com/prompt.html",
            source_title=title,
            domain=["llm"],
            tags=["prompt"],
            blocks=blocks,
        )
        cards = extract_cards(doc)

        self.assertEqual(len(cards), 2)
        self.assertNotIn(cards[1].topic, {"简要回答", "详细解析"})
        self.assertEqual(cards[1].topic, "如何写好 Prompt？分享下 Prompt 工程实践经验？")


if __name__ == "__main__":
    unittest.main()
