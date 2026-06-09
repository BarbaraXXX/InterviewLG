from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from coding_problem_pipeline.env import load_llm_settings
from coding_problem_pipeline.jsonl import read_jsonl, write_jsonl
from coding_problem_pipeline.llm import LLMClient
from coding_problem_pipeline.models import ProblemIndex, normalize_problem
from coding_problem_pipeline.validator import validate_problem

SYSTEM_PROMPT = """你是一个用于生成模拟面试手撕题库的离线数据助手。
你的任务是根据题目索引生成原创中文 CodingProblem JSON。

硬性要求：
- 不要复制任何刷题平台题面、示例、约束、官方模板或题解原文。
- 不要输出标准答案、解题思路、复杂度分析、评分点或评价标准。
- 只生成题目本体：题面、约束、样例、空的 starter code。
- 题目语义应与输入标题代表的经典题型一致，不能改变核心考查点。
- examples 不要使用平台官方原样例，自己构造简洁样例。
- starter_code 只能是空函数/类模板，不能包含解法。
- 只输出一个 JSON 对象，不要输出 Markdown。
"""


def generate_from_index_file(
    *,
    root: Path,
    input_path: Path,
    output_path: Path,
    limit: int | None = None,
    offset: int = 0,
    overwrite: bool = False,
    client_factory: Callable[[], LLMClient] | None = None,
) -> dict:
    rows = read_jsonl(input_path)
    indexes = [ProblemIndex.from_dict(row) for row in rows]
    selected = indexes[offset:]
    if limit is not None:
        selected = selected[:limit]

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output_path}. Use --overwrite to replace it.")

    client = client_factory() if client_factory is not None else LLMClient(load_llm_settings(root))
    generated: list[dict] = []
    errors: list[dict] = []
    for index in selected:
        try:
            raw = client.complete_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_user_prompt(index),
            )
            problem = normalize_problem(index, raw)
            validation = validate_problem(problem)
            generated.append(
                {
                    **problem,
                    "_review": {
                        "status": "pending",
                        "source": index.source,
                        "source_id": index.source_id,
                        "slug": index.slug,
                        "warnings": validation.warnings,
                    },
                }
            )
            if validation.errors:
                errors.append({"id": problem.get("id"), "errors": validation.errors})
        except Exception as exc:
            errors.append({"source_id": index.source_id, "title": index.title, "errors": [str(exc)]})

    write_jsonl(output_path, generated)
    return {
        "input": len(rows),
        "selected": len(selected),
        "generated": len(generated),
        "errors": errors,
        "output": str(output_path),
    }


def build_user_prompt(index: ProblemIndex) -> str:
    payload = {
        "source": index.source,
        "source_id": index.source_id,
        "slug": index.slug,
        "title": index.title,
        "difficulty": index.difficulty,
        "importance": index.importance,
        "answer_mode": index.answer_mode,
        "topics": index.topics,
        "tags": index.tags,
    }
    return f"""请根据以下题目索引生成一个 CodingProblem JSON。

题目索引：
{json.dumps(payload, ensure_ascii=False, indent=2)}

输出字段必须是：
{{
  "id": "稳定 ID，可使用 source/source_id/slug 组合",
  "title": "中文题目标题",
  "difficulty": "easy|medium|hard",
  "importance": "hot100|high|normal",
  "answer_mode": "core|acm",
  "topics": ["主题标签"],
  "tags": ["检索标签"],
  "statement": "原创中文题面，不复制平台原文",
  "constraints": ["约束条件"],
  "examples": [
    {{"input": "输入示例", "output": "输出示例", "explanation": "可为空"}}
  ],
  "starter_code": {{
    "python": "空模板",
    "cpp": "空模板"
  }},
  "source_url": "",
  "source_title": "{index.source}:{index.source_id}"
}}

补充要求：
- core 模式提供函数/类方法模板；acm 模式提供 stdin/stdout main 模板。
- 至少提供 python 和 cpp starter_code。
- statement、constraints、examples 必须自洽，候选人只看这些内容也能答题。
- 不要复制任何平台原题面、官方样例、官方约束、官方模板或题解。
- 不要写“参考 LeetCode/力扣”等展示给用户的文字。
"""
