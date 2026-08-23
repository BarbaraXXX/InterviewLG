import logging
import uuid
from collections import OrderedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable

from interview_agent.agent import build_interview_agent
from interview_agent.db import (
    append_message_with_next_seq,
    create_message,
    create_session,
    delete_session_for_user,
    delete_sessions_for_user,
    expire_stale_sessions,
    get_session_for_user,
    get_session_messages,
    trim_session_messages,
    trim_user_sessions,
    update_session_status,
)

logger = logging.getLogger(__name__)

_MAX_AGENTS = 100
_MAX_MESSAGES_PER_SESSION = 200
OPENING_MESSAGE = (
    "你好，我是本场模拟面试官。请先做一个简短的自我介绍，"
    "可以包括你的技术方向、项目经历，以及希望本次重点考查的内容。"
)


class InterviewSession:
    """Thin wrapper: agent (in-memory) + metadata from DB."""

    def __init__(
        self,
        agent: Runnable,
        domain: str,
        difficulty: str,
        username: str,
        question_rationale_enabled: bool = False,
    ) -> None:
        self.agent = agent
        self.domain = domain
        self.difficulty = difficulty
        self.username = username
        self.question_rationale_enabled = question_rationale_enabled


class SessionManager:
    def __init__(self) -> None:
        self._agents: OrderedDict[str, InterviewSession] = OrderedDict()

    def _evict_agents(self) -> None:
        while len(self._agents) > _MAX_AGENTS:
            oldest_id, _ = self._agents.popitem(last=False)
            logger.info("agent evicted (max agents) session=%s", oldest_id)

    async def create(
        self,
        domain: str,
        difficulty: str,
        username: str,
        user_id: int,
        structured_jd: str = "",
        structured_profile: str = "",
        resume_title_snapshot: str = "",
        question_rationale_enabled: bool = False,
        blueprint: dict | None = None,
    ) -> str:
        await expire_stale_sessions()
        self._evict_agents()

        session_id = uuid.uuid4().hex
        agent = await build_interview_agent(
            domain,
            difficulty,
            structured_jd,
            structured_profile,
            session_id=session_id,
            enable_question_rationale=question_rationale_enabled,
        )

        await create_session(
            session_id=session_id,
            user_id=user_id,
            username=username,
            domain=domain,
            difficulty=difficulty,
            structured_jd=structured_jd,
            structured_profile=structured_profile,
            resume_title_snapshot=resume_title_snapshot,
            blueprint=blueprint,
        )
        await create_message(session_id, "ai", OPENING_MESSAGE, 0)

        self._agents[session_id] = InterviewSession(agent, domain, difficulty, username, question_rationale_enabled)
        trimmed_ids = await trim_user_sessions(user_id)
        for trimmed_id in trimmed_ids:
            self._agents.pop(trimmed_id, None)
        self._evict_agents()
        logger.info("session created id=%s user=%s domain=%s difficulty=%s", session_id, username, domain, difficulty)
        return session_id

    def get_agent(self, session_id: str, username: str | None = None) -> InterviewSession | None:
        ses = self._agents.get(session_id)
        if ses is None:
            return None
        if username is not None and ses.username != username:
            return None
        self._agents.move_to_end(session_id)
        return ses

    async def get_or_rebuild_agent(
        self,
        session_id: str,
        username: str,
        user_id: int,
        question_rationale_enabled: bool = False,
    ) -> InterviewSession | None:
        ses = self.get_agent(session_id, username)
        if ses is not None and ses.question_rationale_enabled == question_rationale_enabled:
            return ses

        row = await get_session_for_user(session_id, user_id)
        if row is None or row["status"] != "active":
            return None

        agent = await build_interview_agent(
            row["domain"],
            row["difficulty"],
            row["structured_jd"],
            row["structured_profile"],
            session_id=session_id,
            enable_question_rationale=question_rationale_enabled,
        )
        ses = InterviewSession(agent, row["domain"], row["difficulty"], username, question_rationale_enabled)
        self._agents[session_id] = ses
        self._evict_agents()
        logger.info("agent rebuilt from db session=%s user=%s", session_id, username)
        return ses

    async def load_messages(self, session_id: str) -> list[BaseMessage]:
        rows = await get_session_messages(session_id, _MAX_MESSAGES_PER_SESSION)
        messages: list[BaseMessage] = []
        for r in rows:
            if r["role"] == "user":
                messages.append(HumanMessage(content=r["content"]))
            elif r["role"] == "ai":
                messages.append(AIMessage(content=r["content"]))
        return messages

    async def append_message(self, session_id: str, role: str, content: str, *, trim: bool = True) -> int:
        seq = await append_message_with_next_seq(session_id, role, content)
        if trim:
            await trim_session_messages(session_id, _MAX_MESSAGES_PER_SESSION)
        return seq

    async def trim_messages(self, session_id: str) -> None:
        await trim_session_messages(session_id, _MAX_MESSAGES_PER_SESSION)

    async def end_session(self, session_id: str) -> None:
        await update_session_status(session_id, "completed")
        self._agents.pop(session_id, None)

    async def pause_session(self, session_id: str) -> None:
        await update_session_status(session_id, "paused")
        self._agents.pop(session_id, None)

    async def resume_session(self, session_id: str, username: str, user_id: int) -> InterviewSession | None:
        row = await get_session_for_user(session_id, user_id)
        if row is None or row["status"] != "paused":
            return None

        agent = await build_interview_agent(
            row["domain"],
            row["difficulty"],
            row["structured_jd"],
            row["structured_profile"],
            session_id=session_id,
        )
        await update_session_status(session_id, "active")
        ses = InterviewSession(agent, row["domain"], row["difficulty"], username)
        self._agents[session_id] = ses
        self._evict_agents()
        logger.info("session resumed id=%s user=%s", session_id, username)
        return ses

    async def delete(self, session_id: str, username: str, user_id: int) -> bool:
        ses = self._agents.get(session_id)
        if ses is not None and ses.username == username:
            self._agents.pop(session_id, None)
        deleted = await delete_session_for_user(session_id, user_id)
        logger.info("session delete requested id=%s user=%s deleted=%s", session_id, username, deleted)
        return deleted

    async def delete_many(self, session_ids: list[str], username: str, user_id: int) -> int:
        deleted_ids = await delete_sessions_for_user(session_ids, user_id)
        for session_id in deleted_ids:
            ses = self._agents.get(session_id)
            if ses is not None and ses.username == username:
                self._agents.pop(session_id, None)
        logger.info("session batch delete requested user=%s deleted=%d", username, len(deleted_ids))
        return len(deleted_ids)


session_manager = SessionManager()
