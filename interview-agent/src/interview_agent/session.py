import logging
import uuid
from collections import OrderedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable

from interview_agent.agent import build_interview_agent
from interview_agent.db import (
    create_message,
    create_session,
    delete_session_for_user,
    delete_sessions_for_user,
    expire_stale_sessions,
    get_next_message_seq,
    get_session_for_user,
    get_session_messages,
    trim_session_messages,
    trim_user_sessions,
    update_session_status,
)

logger = logging.getLogger(__name__)

_MAX_AGENTS = 100
_MAX_MESSAGES_PER_SESSION = 200


class InterviewSession:
    """Thin wrapper: agent (in-memory) + metadata from DB."""

    def __init__(self, agent: Runnable, domain: str, difficulty: str, username: str) -> None:
        self.agent = agent
        self.domain = domain
        self.difficulty = difficulty
        self.username = username


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
    ) -> str:
        await expire_stale_sessions()
        self._evict_agents()

        agent = await build_interview_agent(domain, difficulty, structured_jd, structured_profile)
        session_id = uuid.uuid4().hex

        await create_session(
            session_id=session_id,
            user_id=user_id,
            username=username,
            domain=domain,
            difficulty=difficulty,
            structured_jd=structured_jd,
            structured_profile=structured_profile,
        )

        self._agents[session_id] = InterviewSession(agent, domain, difficulty, username)
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
    ) -> InterviewSession | None:
        ses = self.get_agent(session_id, username)
        if ses is not None:
            return ses

        row = await get_session_for_user(session_id, user_id)
        if row is None or row["status"] != "active":
            return None

        agent = await build_interview_agent(
            row["domain"],
            row["difficulty"],
            row["structured_jd"],
            row["structured_profile"],
        )
        ses = InterviewSession(agent, row["domain"], row["difficulty"], username)
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

    async def append_message(self, session_id: str, role: str, content: str) -> None:
        seq = await get_next_message_seq(session_id)
        await create_message(session_id, role, content, seq)
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
