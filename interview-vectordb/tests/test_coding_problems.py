import json

from interview_vectordb.coding_problems import CodingProblemStore, load_coding_problems_from_path
from interview_vectordb.embeddings import DeterministicEmbeddingProvider
from interview_vectordb.schema import CodingProblem, CodingProblemExample


def _problem(problem_id: str, *, answer_mode: str = "core") -> CodingProblem:
    return CodingProblem(
        id=problem_id,
        title="反转链表",
        difficulty="easy",
        importance="hot100",
        answer_mode=answer_mode,
        topics=["linked_list", "pointer"],
        tags=["iteration"],
        statement="给定一个单链表的头节点 head，请反转链表并返回新的头节点。",
        constraints=["链表节点数量范围为 0 到 5000"],
        examples=[CodingProblemExample(input="head=[1,2,3]", output="[3,2,1]")],
        starter_code={"python": "class Solution:\n    def reverseList(self, head):\n        pass\n"},
    )


def test_import_and_search_coding_problems(isolate_env):
    store = CodingProblemStore(
        isolate_env / "coding_problems" / "coding_problems.sqlite3",
        DeterministicEmbeddingProvider(64),
    )

    stats = store.import_problems([_problem("reverse-list"), _problem("reverse-list")])

    assert stats == {"imported": 1, "deduped": 1}
    assert store.count() == 1

    results = store.search(
        "链表反转",
        difficulty=["easy"],
        importance=["hot100"],
        answer_mode=["core"],
        topics=["linked_list"],
    )

    assert len(results) == 1
    assert results[0]["id"] == "reverse-list"
    assert results[0]["examples"][0]["output"] == "[3,2,1]"


def test_search_coding_problems_filters_and_excludes(isolate_env):
    store = CodingProblemStore(
        isolate_env / "coding_problems" / "coding_problems.sqlite3",
        DeterministicEmbeddingProvider(64),
    )
    store.import_problems([_problem("core-problem"), _problem("acm-problem", answer_mode="acm")])

    acm_results = store.search("链表", answer_mode=["acm"])
    assert [item["id"] for item in acm_results] == ["acm-problem"]

    excluded = store.search("链表", exclude_ids=["core-problem", "acm-problem"])
    assert excluded == []


def test_coding_problem_stats(isolate_env):
    store = CodingProblemStore(
        isolate_env / "coding_problems" / "coding_problems.sqlite3",
        DeterministicEmbeddingProvider(64),
    )
    store.import_problems([_problem("reverse-list")])

    assert store.stats()["difficulty"] == {"easy": 1}
    assert store.stats()["importance"] == {"hot100": 1}
    assert store.stats()["answer_mode"] == {"core": 1}
    assert store.stats()["topics"]["linked_list"] == 1


def test_load_coding_problems_from_jsonl(isolate_env):
    path = isolate_env / "problems.jsonl"
    path.write_text(
        json.dumps(_problem("reverse-list").model_dump(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    problems = load_coding_problems_from_path(path)

    assert len(problems) == 1
    assert problems[0].id == "reverse-list"
