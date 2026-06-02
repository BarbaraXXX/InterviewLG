from pydantic import BaseModel, Field


class InterviewProfile(BaseModel):
    company: str = Field(description="公司名称")
    position: str = Field(description="岗位名称")
    difficulty_tendency: str = Field(default="mid", description="难度倾向: junior/mid/senior")
    focus_areas: list[str] = Field(default_factory=list, description="考查重点领域列表")
    interview_style: str = Field(default="", description="面试风格描述，Agent学习此风格")
    question_types: list[str] = Field(default_factory=list, description="常见问题类型，如['原理题','系统设计','场景题']")
    key_traits: list[str] = Field(default_factory=list, description="区分性特征，如['偏底层','算法题少','追细节']")
    source_count: int = Field(default=0, description="聚合来源面经数量")


class InterviewExperience(BaseModel):
    company: str = Field(description="公司名称", max_length=128)
    position: str = Field(description="岗位名称", max_length=128)
    raw_text: str = Field(default="", description="面经原始文本，任意格式，可以是博客文章、笔记、回忆帖等", max_length=100000)


class QuestionCard(BaseModel):
    id: str = Field(description="稳定 QuestionCard ID", max_length=128)
    domain: list[str] = Field(default_factory=list, description="领域标签，如 backend/redis")
    topic: str = Field(default="", description="知识点主题", max_length=256)
    question: str = Field(description="面试问题", max_length=2000)
    answer_outline: list[str] = Field(default_factory=list, description="答案要点")
    followups: list[str] = Field(default_factory=list, description="追问")
    tags: list[str] = Field(default_factory=list, description="检索标签")
    difficulty: str = Field(default="", description="难度: junior/mid/senior")
    source_url: str = Field(default="", description="来源 URL", max_length=2000)
    source_title: str = Field(default="", description="来源标题", max_length=512)


class QuestionCardSearchRequest(BaseModel):
    query: str = Field(description="检索 query", min_length=1, max_length=4000)
    domain: list[str] = Field(default_factory=list, description="可选领域过滤")
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0)
