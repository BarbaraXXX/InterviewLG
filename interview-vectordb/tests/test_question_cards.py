import json

from interview_vectordb.embeddings import DeterministicEmbeddingProvider
from interview_vectordb.question_cards import QuestionCardStore, build_search_text, load_question_cards_from_path
from interview_vectordb.schema import QuestionCard


def test_build_search_text_contains_key_fields():
    card = sample_card("1", ["backend", "redis"], "Redis 数据结构", "讲一下 Redis zset 跳表")

    text = build_search_text(card)

    assert "redis" in text
    assert "Redis 数据结构" in text
    assert "跳表" in text


def test_load_question_cards_from_jsonl(tmp_path):
    path = tmp_path / "cards.jsonl"
    card = sample_card("1", ["backend", "redis"], "Redis", "Redis 为什么快？")
    path.write_text(json.dumps(card.model_dump(), ensure_ascii=False) + "\n", encoding="utf-8")

    cards = load_question_cards_from_path(path)

    assert len(cards) == 1
    assert cards[0].question == "Redis 为什么快？"


def test_question_card_store_import_and_search(tmp_path):
    store = QuestionCardStore(tmp_path / "cards.sqlite3", DeterministicEmbeddingProvider(dimensions=64))
    cards = [
        sample_card("redis", ["backend", "redis"], "Redis 数据结构", "讲一下 Redis zset 跳表"),
        sample_card("tcp", ["backend", "network"], "TCP 握手", "为什么 TCP 需要三次握手？"),
    ]

    stats = store.import_cards(cards, batch_size=2)
    results = store.search("redis zset 跳表", domain=["redis"], top_k=3)

    assert stats["imported"] == 2
    assert store.count() == 2
    assert store.domain_counts()["redis"] == 1
    assert len(results) == 1
    assert results[0]["id"] == "redis"


def sample_card(card_id: str, domain: list[str], topic: str, question: str) -> QuestionCard:
    return QuestionCard(
        id=card_id,
        domain=domain,
        topic=topic,
        question=question,
        answer_outline=["核心知识点"],
        followups=["进一步追问？"],
        tags=domain,
        difficulty="mid",
        source_url="https://example.com",
        source_title="Example",
    )
