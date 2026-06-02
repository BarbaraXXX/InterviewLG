import json
import logging
import os
import uuid
from pathlib import Path

from openai import OpenAI

from interview_vectordb.schema import InterviewExperience, InterviewProfile

from .config import llm_settings

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.getenv("VECTORDB_DATA_DIR", Path.cwd() / "data"))
_PROFILES_DIR = _DATA_DIR / "profiles"
_EXPERIENCES_DIR = _DATA_DIR / "experiences"
_QUESTION_CARDS_DB_PATH = _DATA_DIR / "question_cards" / "question_cards.sqlite3"


class ProfileDB:
    def __init__(self) -> None:
        _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        _EXPERIENCES_DIR.mkdir(parents=True, exist_ok=True)
        self._client = OpenAI(
            base_url=llm_settings.base_url,
            api_key=llm_settings.api_key,
        )

    @staticmethod
    def _sanitize_key(company: str, position: str) -> str:
        key = f"{company}_{position}"
        key = key.replace("/", "_").replace("\\", "_")
        if ".." in key:
            key = key.replace("..", "_")
        return key

    def _profile_path(self, company: str, position: str) -> Path:
        return _PROFILES_DIR / f"{self._sanitize_key(company, position)}.json"

    def _experience_path(self, company: str, position: str, exp_id: str) -> Path:
        return _EXPERIENCES_DIR / f"{self._sanitize_key(company, position)}_{exp_id}.json"

    def _load_json(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_profile(self, company: str, position: str) -> InterviewProfile | None:
        path = self._profile_path(company, position)
        data = self._load_json(path)
        if data is None:
            return None
        return InterviewProfile(**data)

    def save_profile(self, profile: InterviewProfile) -> None:
        path = self._profile_path(profile.company, profile.position)
        self._save_json(path, profile.model_dump())
        logger.info("Saved profile %s/%s (source_count=%d)", profile.company, profile.position, profile.source_count)

    def list_profiles(self) -> list[InterviewProfile]:
        profiles = []
        for path in _PROFILES_DIR.glob("*.json"):
            data = self._load_json(path)
            if data:
                try:
                    profiles.append(InterviewProfile(**data))
                except Exception:
                    pass
        return profiles

    def delete_profile(self, company: str, position: str) -> None:
        path = self._profile_path(company, position)
        if path.exists():
            path.unlink()

    def get_experiences(self, company: str, position: str) -> list[InterviewExperience]:
        experiences = []
        prefix = f"{company}_{position}".replace("/", "_").replace("\\", "_")
        for path in _EXPERIENCES_DIR.glob(f"{prefix}_*.json"):
            data = self._load_json(path)
            if data:
                try:
                    experiences.append(InterviewExperience(**data))
                except Exception:
                    pass
        return experiences

    def _load_all_experiences(self) -> list[InterviewExperience]:
        experiences = []
        for path in _EXPERIENCES_DIR.glob("*.json"):
            data = self._load_json(path)
            if data:
                try:
                    experiences.append(InterviewExperience(**data))
                except Exception:
                    pass
        return experiences

    def add_experiences(self, experiences: list[InterviewExperience]) -> list[str]:
        ids = []
        for exp in experiences:
            exp_id = uuid.uuid4().hex
            path = self._experience_path(exp.company, exp.position, exp_id)
            self._save_json(path, exp.model_dump())
            ids.append(exp_id)
        return ids

    # --- LLM helpers ---

    def _call_llm(self, prompt: str, max_tokens: int = 512) -> str | None:
        try:
            response = self._client.chat.completions.create(
                model=llm_settings.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content.strip()
            # Strip markdown code fences
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            return content.strip()
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            return None

    def _parse_profile_json(self, content: str, company: str, position: str, source_count: int = 0) -> InterviewProfile | None:
        try:
            data = json.loads(content)
            return InterviewProfile(
                company=company,
                position=position,
                difficulty_tendency=data.get("difficulty_tendency", data.get("difficulty", "mid")),
                focus_areas=data.get("focus_areas", []),
                interview_style=data.get("interview_style", ""),
                question_types=data.get("question_types", []),
                key_traits=data.get("key_traits", []),
                source_count=source_count,
            )
        except Exception as e:
            logger.warning(f"Failed to parse profile JSON: {e}")
            return None

    # --- Tiered aggregation ---

    def _summarize_experience(self, exp: InterviewExperience) -> dict:
        prompt = f"""你是一个面经分析助手。请分析以下面经，提取关键信息并以JSON格式返回。

字段说明：
- focus_areas: 考查重点领域列表（字符串数组），如["系统设计","高并发","数据库原理"]
- interview_style: 面试风格描述，如"从项目经历出发逐步深入底层原理，喜欢追问实现细节"
- question_types: 常见问题类型列表，如["系统设计题","原理题","场景题"]
- key_traits: 区分性特征列表，如["偏底层","算法题少","追细节深挖"]
- difficulty_tendency: 难度倾向，junior/mid/senior

只返回JSON，不要添加其他文字。

面经内容：
{exp.raw_text}"""
        content = self._call_llm(prompt, max_tokens=512)
        if content is None:
            return {
                "focus_areas": [],
                "interview_style": "",
                "question_types": [],
                "key_traits": [],
                "difficulty_tendency": "mid",
            }
        try:
            return json.loads(content)
        except Exception as e:
            logger.warning(f"Failed to parse summary JSON: {e}")
            return {
                "focus_areas": [],
                "interview_style": "",
                "question_types": [],
                "key_traits": [],
                "difficulty_tendency": "mid",
            }

    def _generate_from_single(self, company: str, position: str, exp: InterviewExperience) -> InterviewProfile | None:
        summary = self._summarize_experience(exp)
        return InterviewProfile(
            company=company,
            position=position,
            difficulty_tendency=summary.get("difficulty_tendency", summary.get("difficulty", "mid")),
            focus_areas=summary.get("focus_areas", []),
            interview_style=summary.get("interview_style", ""),
            question_types=summary.get("question_types", []),
            key_traits=summary.get("key_traits", []),
            source_count=1,
        )

    def _merge_summaries(self, company: str, position: str, summaries: list[dict], n: int) -> InterviewProfile | None:
        summaries_text = "\n\n".join(
            f"--- 摘要 {i+1} ---\n{json.dumps(s, ensure_ascii=False)}"
            for i, s in enumerate(summaries)
        )
        prompt = f"""你是一个面经分析助手。以下是{company} {position}岗位的{n}份面经摘要，请综合分析生成面试官画像。

字段说明：
- difficulty_tendency: 难度倾向，junior/mid/senior
- focus_areas: 综合考查重点领域（高频出现者优先）
- interview_style: 综合面试风格描述（合并共同特征，保留独特特征）
- question_types: 综合常见问题类型
- key_traits: 区分性特征（出现2次以上的特征优先）

只返回JSON，不要添加其他文字。

面经摘要：
{summaries_text}"""
        content = self._call_llm(prompt, max_tokens=768)
        if content is None:
            return InterviewProfile(company=company, position=position, source_count=n)
        return self._parse_profile_json(content, company, position, source_count=n)

    def _final_merge(self, company: str, position: str, group_merges: list[InterviewProfile], total_n: int) -> InterviewProfile | None:
        summaries_text = "\n\n".join(
            f"--- 分组画像 {i+1} ---\n{json.dumps(p.model_dump(), ensure_ascii=False)}"
            for i, p in enumerate(group_merges)
        )
        prompt = f"""你是一个面经分析助手。以下是{company} {position}岗位的{total_n}份面经经过分组聚合后的画像，请综合分析生成最终面试官画像。

字段说明：
- difficulty_tendency: 难度倾向，junior/mid/senior
- focus_areas: 综合考查重点领域（高频出现者优先）
- interview_style: 综合面试风格描述（合并共同特征，保留独特特征）
- question_types: 综合常见问题类型
- key_traits: 区分性特征（出现2次以上的特征优先）

只返回JSON，不要添加其他文字。

分组画像：
{summaries_text}"""
        content = self._call_llm(prompt, max_tokens=768)
        if content is None:
            return InterviewProfile(company=company, position=position, source_count=total_n)
        return self._parse_profile_json(content, company, position, source_count=total_n)

    def generate_profile(self, company: str, position: str) -> InterviewProfile | None:
        experiences = self.get_experiences(company, position)
        if not experiences:
            logger.info("generate_profile: no experiences for %s/%s", company, position)
            return None

        n = len(experiences)
        logger.info("generate_profile: %s/%s n=%d", company, position, n)

        if n == 1:
            return self._generate_from_single(company, position, experiences[0])
        elif n <= 5:
            summaries = [self._summarize_experience(exp) for exp in experiences]
            return self._merge_summaries(company, position, summaries, n)
        else:
            summaries = [self._summarize_experience(exp) for exp in experiences]
            groups = [summaries[i:i+5] for i in range(0, len(summaries), 5)]
            group_merges = [self._merge_summaries(company, position, g, len(g)) for g in groups]
            valid_merges = [m for m in group_merges if m is not None]
            if not valid_merges:
                return InterviewProfile(company=company, position=position, source_count=n)
            if len(valid_merges) == 1:
                valid_merges[0].source_count = n
                return valid_merges[0]
            return self._final_merge(company, position, valid_merges, n)

    def get_or_generate_profile(self, company: str, position: str) -> InterviewProfile:
        profile = self.get_profile(company, position)
        if profile:
            return profile

        experiences = self.get_experiences(company, position)
        if not experiences:
            return InterviewProfile(company=company, position=position)

        profile = self.generate_profile(company, position)
        if profile:
            self.save_profile(profile)
        else:
            profile = InterviewProfile(company=company, position=position)

        return profile

    def batch_generate_profiles(self) -> dict[str, InterviewProfile]:
        experiences_by_key: dict[str, list[InterviewExperience]] = {}
        for exp in self._load_all_experiences():
            key = (exp.company, exp.position)
            experiences_by_key.setdefault(key, []).append(exp)

        results = {}
        for (company, position), exps in experiences_by_key.items():
            profile = self.get_profile(company, position)
            if profile is None:
                profile = self.generate_profile(company, position)
                if profile:
                    self.save_profile(profile)
            if profile:
                results[f"{company}_{position}"] = profile
        return results
