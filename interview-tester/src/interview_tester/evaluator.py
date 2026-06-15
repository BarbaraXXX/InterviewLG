import json
import logging
import re

from interview_agent.config import llm_settings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import test_settings
from .schemas import Evaluation, TestSession

logger = logging.getLogger(__name__)


def build_evaluator_prompt(session: TestSession) -> str:
    has_jd = bool(session.config.job_description and session.config.job_description.strip())
    has_profile = bool(
        session.config.profile_company and session.config.profile_company.strip()
        and session.config.profile_position and session.config.profile_position.strip()
    )

    dim_count = 5
    dimensions = [
        "1. style_naturalness：对话自然度，面试官的提问和回应是否自然流畅",
        "2. difficulty_appropriateness：难度适当性，问题难度是否匹配设定难度和候选人水平",
        "3. follow_up_quality：追问质量，面试官根据候选人回答进行追问的质量",
        "4. topic_coverage：话题覆盖度，面试涉及的知识面广度",
        "5. overall_score：总体评分，对面试官整体表现的综合评价",
    ]

    if has_jd:
        dim_count += 1
        dimensions.append(
            f"{dim_count}. jd_relevance：JD关联度（1-10分），面试官的问题是否紧扣JD中提到的岗位要求、必需技能、技术栈和面试侧重。评0分表示完全没有利用JD信息，10分表示高度贴合JD要求。"
        )

    if has_profile:
        dim_count += 1
        dimensions.append(
            f"{dim_count}. profile_relevance：偏好匹配度（1-10分），面试官的面试风格是否与该公司该岗位的面试偏好（考查重点、面试风格、常见问题类型、区分性特征）一致。评0分表示完全没有体现Profile偏好，10分表示高度匹配。"
        )

    dim_count += 1
    dimensions.append(
        f"{dim_count}. difficulty_adaptation：难度动态调整能力（1-10分），面试官是否能根据候选人的回答质量动态调整后续问题的难度——当候选人回答出色时适当提高难度，当候选人回答薄弱时适当降低难度或换角度考查。评0分表示完全没有调整，10分表示调整得当且自然。"
    )

    config_lines = [
        f"- 面试领域：{session.config.domain}",
        f"- 设定难度：{session.config.difficulty}",
        f"- 候选人水平：{session.config.candidate_level}",
    ]
    if has_jd:
        config_lines.append(f"- 岗位描述（JD）：{session.config.job_description}")
    if has_profile:
        config_lines.append(f"- 面试偏好：公司={session.config.profile_company}，岗位={session.config.profile_position}")

    config_section = "\n".join(config_lines)
    dimensions_text = "\n".join(dimensions)

    json_fields = [
        ('  "style_naturalness": <int>'),
        ('  "difficulty_appropriateness": <int>'),
        ('  "follow_up_quality": <int>'),
        ('  "topic_coverage": <int>'),
        ('  "overall_score": <int>'),
    ]
    if has_jd:
        json_fields.append('  "jd_relevance": <int>')
    if has_profile:
        json_fields.append('  "profile_relevance": <int>')
    json_fields.append('  "difficulty_adaptation": <int>')
    json_fields.extend([
        '  "strengths": ["...", "..."]',
        '  "weaknesses": ["...", "..."]',
        '  "summary": "..."',
        '  "improvement_suggestions": ["...", "..."]',
    ])

    json_template = "{{\n" + ",\n".join(json_fields) + "\n}}"

    no_jd_note = ""
    if not has_jd:
        no_jd_note = "\n注意：本次面试未提供JD，jd_relevance请评0分（表示未使用JD，而非负面评价）。"

    no_profile_note = ""
    if not has_profile:
        no_profile_note = "\n注意：本次面试未提供Profile，profile_relevance请评0分（表示未使用Profile，而非负面评价）。"

    transcript = _build_transcript(session)

    return f"""你是一位面试评估专家，请根据以下面试记录评估面试官（AI Agent）的表现。

面试配置：
{config_section}

面试记录：
{transcript}

请从以下{dim_count}个维度评分（1-10分）：
{dimensions_text}

同时提供：
- strengths：面试官的优势（字符串列表）
- weaknesses：面试官的不足（字符串列表）
- summary：总体评价（一段话）
- improvement_suggestions：改进建议（可操作的建议列表）
{no_jd_note}{no_profile_note}
请只返回JSON，不要添加其他文字。JSON格式如下：
{json_template}"""


def _build_transcript(session: TestSession) -> str:
    lines = []
    for qa in session.qa_pairs:
        lines.append(f"[第{qa.round}轮] 面试官：{qa.question}")
        lines.append(f"[第{qa.round}轮] 候选人：{qa.answer}")
    return "\n".join(lines)


def _parse_eval_json(text: str) -> dict:
    content = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fence_match:
        content = fence_match.group(1).strip()
    return json.loads(content)


async def evaluate_session(session: TestSession) -> Evaluation:
    provider = llm_settings.get_provider()
    llm = ChatOpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=provider.model,
        temperature=test_settings.evaluator_temperature,
    )

    prompt_text = build_evaluator_prompt(session)

    messages = [
        SystemMessage(content="你是一个专业的面试评估系统，只输出JSON格式的评估结果。"),
        HumanMessage(content=prompt_text),
    ]

    try:
        response = await llm.ainvoke(messages)
        data = _parse_eval_json(response.content)
        return Evaluation(**data)
    except Exception:
        logger.warning("evaluate_session: failed to parse evaluation JSON", exc_info=True)
        return Evaluation(
            style_naturalness=0,
            difficulty_appropriateness=0,
            follow_up_quality=0,
            topic_coverage=0,
            overall_score=0,
            strengths=[],
            weaknesses=[],
            summary="评估失败：无法解析评估结果。",
            improvement_suggestions=[],
            jd_relevance=0,
            profile_relevance=0,
            difficulty_adaptation=0,
        )
