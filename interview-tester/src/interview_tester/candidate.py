import logging

from interview_agent.config import llm_settings
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import test_settings

logger = logging.getLogger(__name__)

_VALID_STYLES = {"cooperative", "weak", "evasive", "overconfident", "specific_weakness"}

_STYLE_PROMPTS: dict[str, str] = {
    "weak": (
        "你的回答应该刻意表现得比较薄弱：回答浅显、不够完整，遇到深入问题时含糊其辞，"
        "对复杂概念理解表面化。偶尔会说'这个我不太确定'或'这个我没有深入研究过'。"
        "注意不要完全不回答，而是给出质量较低的回答。"
    ),
    "evasive": (
        "你的回答风格是回避正题：经常绕弯子不直接回答问题，试图用模糊的表述蒙混过关，"
        "喜欢转移话题到自己熟悉的领域。比如面试官问A，你会先说一些相关但不是核心的内容，"
        "然后试图把话题引向B。"
    ),
    "overconfident": (
        "你是一个非常自信的候选人，甚至有些过度自信：对不确定的内容也会很自信地给出错误答案，"
        "夸大自己的项目经验和能力，经常说'这个我很熟悉'但实际回答可能有错误。"
        "不要故意给完全无关的答案，而是给出听起来合理但实际有错误的回答。"
    ),
}


def build_candidate_llm(candidate_level: str, provider_name: str = "") -> ChatOpenAI:
    provider = llm_settings.get_provider(provider_name) if provider_name else llm_settings.get_provider()
    return ChatOpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=provider.model,
        temperature=test_settings.candidate_temperature,
    )


def get_candidate_system_prompt(
    domain: str,
    candidate_level: str,
    candidate_style: str = "cooperative",
    candidate_weaknesses: list[str] | None = None,
) -> str:
    # Fallback: unknown style or specific_weakness without weaknesses → cooperative
    if candidate_style not in _VALID_STYLES:
        logger.warning("Unknown candidate_style=%r, falling back to 'cooperative'", candidate_style)
        candidate_style = "cooperative"
    if candidate_style == "specific_weakness" and not candidate_weaknesses:
        logger.warning("candidate_style='specific_weakness' but no weaknesses provided, falling back to 'cooperative'")
        candidate_style = "cooperative"

    level_map = {
        "junior": "1-3年",
        "mid": "3-5年",
        "senior": "5年以上",
    }
    experience = level_map.get(candidate_level, "3-5年")

    level_guidance = {
        "junior": (
            "你的回答应该比较简单直接，展示基础知识的掌握，但不需要涉及太深层的架构设计。"
            "偶尔可以对一些高级问题表现出不太确定。"
        ),
        "mid": (
            "你的回答应该展示扎实的技术功底和实际项目经验，能够深入分析问题，"
            "但偶尔在某些前沿领域或复杂架构问题上可以表现出需要思考。"
        ),
        "senior": (
            "你的回答应该深入且全面，展示丰富的架构设计经验和技术决策能力，"
            "能够从多个维度分析问题，给出系统性的解决方案。"
        ),
    }
    guidance = level_guidance.get(candidate_level, level_guidance["mid"])

    style_prompt = ""
    if candidate_style == "specific_weakness" and candidate_weaknesses:
        weaknesses_str = "、".join(candidate_weaknesses)
        style_prompt = (
            "你在大部分领域表现正常，但在特定领域有明显弱点。"
            f"以下是你不擅长的领域：{weaknesses_str}。"
            "当面试官问及这些领域时，你的回答应该表现出明显的不确定、理解浅薄或含糊不清。"
            "其他领域则正常回答。"
        )
    elif candidate_style in _STYLE_PROMPTS:
        style_prompt = _STYLE_PROMPTS[candidate_style]

    parts = [
        f"你是一名正在参加{domain}领域技术面试的候选人，拥有{experience}工作经验。\n",
        guidance,
    ]
    if style_prompt:
        parts.append(style_prompt)
    parts.append(
        "\n面试规则：\n"
        "- 以自然的方式回答面试官的问题，像一个真实的候选人\n"
        "- 保持角色，永远不要打破模拟，不要提及自己是AI或语言模型\n"
        "- 不要反问面试官问题，只回答并等待下一个问题\n"
        "- 回答的深度和广度应该符合你的经验水平\n"
        f"- 你面试的领域是{domain}，请展示该领域的相关技术知识\n"
    )

    return "\n\n".join(parts)


async def generate_candidate_response(
    messages: list[BaseMessage],
    candidate_llm: ChatOpenAI,
    candidate_prompt: str,
) -> str:
    system = SystemMessage(content=candidate_prompt)
    response = await candidate_llm.ainvoke([system] + messages)
    return response.content
