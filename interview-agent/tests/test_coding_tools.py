import json

from interview_agent import coding_tools as coding_tools_module
from interview_agent.coding_tools import build_coding_tools
from interview_agent.db import create_session, create_user, get_coding_task, init_db


def _tool_by_name(name: str):
    tools = build_coding_tools("sid-code-tools")
    return next(tool for tool in tools if tool.name == name)


async def test_create_coding_task_from_problem_records_source(isolate_env, monkeypatch):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-code-tools", user_id, "alice", "backend", "campus_fulltime")

    async def fake_get_problem(problem_id: str) -> dict:
        return {
            "id": problem_id,
            "title": "反转链表",
            "statement": "给定一个单链表头节点，请反转链表并返回新的头节点。",
            "constraints": ["链表长度范围为 0 到 5000"],
            "examples": [{"input": "head=[1,3,5]", "output": "[5,3,1]"}],
            "starter_code": {
                "python": "class Solution:\n    def reverseList(self, head):\n        pass\n",
                "cpp": "class Solution {\npublic:\n    ListNode* reverseList(ListNode* head) {\n        return nullptr;\n    }\n};\n",
            },
        }

    monkeypatch.setattr(coding_tools_module, "get_coding_problem", fake_get_problem)
    tool = _tool_by_name("create_coding_task_from_problem")

    result = json.loads(await tool.ainvoke({"problem_id": "hot100_206", "language": "python"}))

    assert result["ok"] is True
    task = await get_coding_task(result["task_id"])
    assert task is not None
    assert task["title"] == "反转链表"
    assert task["source_problem_id"] == "hot100_206"
    assert task["source_problem_title"] == "反转链表"
    starter_code_map = json.loads(task["starter_code_json"])
    assert "python" in starter_code_map
    assert "cpp" in starter_code_map


async def test_search_coding_problems_excludes_used_problem_ids(isolate_env, monkeypatch):
    await init_db()
    user_id = await create_user("alice", "hash")
    await create_session("sid-code-tools", user_id, "alice", "backend", "campus_fulltime")

    async def fake_get_problem(problem_id: str) -> dict:
        return {
            "id": problem_id,
            "title": "两数之和",
            "statement": "给定数组和目标值，返回两个数下标。",
            "starter_code": {"python": "class Solution:\n    pass\n"},
        }

    seen_exclude_ids = []

    async def fake_search(**kwargs):
        seen_exclude_ids.extend(kwargs["exclude_ids"])
        return [
            {
                "id": "hot100_1",
                "title": "两数之和",
                "difficulty": "easy",
                "importance": "hot100",
                "answer_mode": "core",
                "topics": ["array", "hash_table"],
                "statement": "给定数组和目标值，返回两个数下标。",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(coding_tools_module, "get_coding_problem", fake_get_problem)
    monkeypatch.setattr(coding_tools_module, "client_search_coding_problems", fake_search)

    create_tool = _tool_by_name("create_coding_task_from_problem")
    await create_tool.ainvoke({"problem_id": "hot100_1", "language": "python"})

    search_tool = _tool_by_name("search_coding_problems")
    result = json.loads(await search_tool.ainvoke({"query": "数组 哈希", "difficulty": ["easy"]}))

    assert result["ok"] is True
    assert result["problems"][0]["id"] == "hot100_1"
    assert seen_exclude_ids == ["hot100_1"]
    assert result["excluded_problem_ids"] == ["hot100_1"]
