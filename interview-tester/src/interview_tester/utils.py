import logging
from urllib.parse import quote

import httpx
from interview_agent.config import vectordb_settings

logger = logging.getLogger(__name__)

_END_KEYWORDS = ("面试结束", "感谢参与", "本次面试", "总结", "overall")
_MAX_JD_FIELD_LEN = 200
_MAX_JD_ITEMS = 10
_MAX_PROFILE_FIELD_LEN = 200


def is_interview_ending(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _END_KEYWORDS)


def sanitize_path_segment(value: str) -> str:
    stripped = value.strip()
    if ".." in stripped or "/" in stripped or "\\" in stripped:
        return ""
    return stripped[:128]


def format_jd(jd: object) -> str:
    parts: list[str] = []
    if v := getattr(jd, "position_title", ""):
        parts.append(f"岗位：{v[:_MAX_JD_FIELD_LEN]}")
    if v := getattr(jd, "required_experience", ""):
        parts.append(f"经验要求：{v[:_MAX_JD_FIELD_LEN]}")
    skills = getattr(jd, "required_skills", [])[:_MAX_JD_ITEMS]
    if skills:
        parts.append(f"必需技能：{', '.join(s[:_MAX_JD_FIELD_LEN] for s in skills)}")
    stack = getattr(jd, "tech_stack", [])[:_MAX_JD_ITEMS]
    if stack:
        parts.append(f"技术栈：{', '.join(s[:_MAX_JD_FIELD_LEN] for s in stack)}")
    responsibilities = getattr(jd, "key_responsibilities", [])[:_MAX_JD_ITEMS]
    if responsibilities:
        items = "\n".join(f"  - {r[:_MAX_JD_FIELD_LEN]}" for r in responsibilities)
        parts.append(f"核心职责：\n{items}")
    preferred = getattr(jd, "preferred_qualifications", [])[:_MAX_JD_ITEMS]
    if preferred:
        items = "\n".join(f"  - {q[:_MAX_JD_FIELD_LEN]}" for q in preferred)
        parts.append(f"加分项：\n{items}")
    focus = getattr(jd, "interview_focus", "")
    if focus:
        parts.append(f"面试侧重：{focus[:_MAX_JD_FIELD_LEN]}")
    return "\n".join(parts)


def format_profile(profile_data: dict) -> str:
    parts: list[str] = []
    company = profile_data.get("company", "")
    position = profile_data.get("position", "")
    if company and position:
        parts.append(f"公司：{company} / 岗位：{position}")
    diff = profile_data.get("difficulty_tendency", "")
    if diff:
        diff_labels = {"junior": "初级", "mid": "中级", "senior": "高级"}
        parts.append(f"难度倾向：{diff_labels.get(diff, diff)}")
    focus = profile_data.get("focus_areas", [])
    if focus:
        parts.append(f"考查重点：{', '.join(str(f)[:_MAX_PROFILE_FIELD_LEN] for f in focus[:10])}")
    style = profile_data.get("interview_style", "")
    if style:
        parts.append(f"面试风格：{style[:500]}")
    qtypes = profile_data.get("question_types", [])
    if qtypes:
        parts.append(f"常见问题类型：{', '.join(str(t)[:_MAX_PROFILE_FIELD_LEN] for t in qtypes[:10])}")
    traits = profile_data.get("key_traits", [])
    if traits:
        parts.append(f"区分性特征：{', '.join(str(t)[:_MAX_PROFILE_FIELD_LEN] for t in traits[:10])}")
    source_count = profile_data.get("source_count", 0)
    if source_count:
        parts.append(f"（基于{source_count}份面经分析）")
    return "\n".join(parts)


async def fetch_profile(company: str, position: str) -> str:
    safe_company = sanitize_path_segment(company)
    safe_position = sanitize_path_segment(position)
    if not safe_company or not safe_position:
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=20),
            follow_redirects=False,
        ) as client:
            resp = await client.get(
                f"{vectordb_settings.base_url}/api/profiles/{quote(safe_company, safe='')}/{quote(safe_position, safe='')}"
            )
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, dict):
                    logger.warning("fetch_profile: unexpected payload type for %s/%s", safe_company, safe_position)
                    return ""
                return format_profile(data)
            logger.warning(
                "fetch_profile: non-200 response for %s/%s (status=%s)",
                safe_company, safe_position, resp.status_code,
            )
    except Exception:
        logger.warning("fetch_profile: request failed for %s/%s", safe_company, safe_position, exc_info=True)
    return ""
