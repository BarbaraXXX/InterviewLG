"""Context assembly for one interview-agent LLM turn."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from interview_agent.config import context_settings
from interview_agent.interview_state import format_state_context
from interview_agent.memory import summarize_running_context
from interview_agent.rag import build_rag_query, format_rag_context, search_interview_cards
from interview_agent.stage_controller import format_stage_control_context

logger = logging.getLogger(__name__)


LoadMessages = Callable[[str], Awaitable[list[BaseMessage]]]
LoadState = Callable[[str], Awaitable[dict | None]]
LoadMemoryContext = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class AgentInput:
    messages: list[BaseMessage]
    rag_cards: list[dict]
    rag_context: str
    state_context: str
    running_summary_context: str
    user_memory_context: str
    memory_context: str
    stage_control_context: str


async def build_agent_input(
    *,
    session_id: str,
    domain: str,
    difficulty: str,
    display_message: str,
    context_message: str,
    load_messages: LoadMessages,
    load_state: LoadState | None = None,
    load_user_memory_context: LoadMemoryContext | None = None,
    load_memory_context: LoadMemoryContext | None = None,
) -> AgentInput:
    """Build the message list sent into the agent graph for a single turn.

    The display message is what gets persisted in chat history. The optional
    context message replaces the latest human message only for this model turn,
    which is used for large payloads such as coding submissions.
    """

    messages = await load_messages(session_id)
    try:
        running_summary_context, messages = await summarize_running_context(
            session_id=session_id,
            messages=messages,
            trigger_tokens=context_settings.recent_messages_trigger_tokens,
            keep_tokens=context_settings.recent_messages_keep_tokens,
            max_summary_tokens=context_settings.running_summary_max_tokens,
        )
    except Exception:
        logger.warning("running summary failed session=%s", session_id, exc_info=True)
        running_summary_context = ""
    run_messages = messages
    if running_summary_context:
        run_messages = [SystemMessage(content=running_summary_context), *run_messages]
    if context_message and run_messages:
        last_human_index = next(
            (idx for idx in range(len(run_messages) - 1, -1, -1) if isinstance(run_messages[idx], HumanMessage)),
            -1,
        )
        if last_human_index >= 0:
            run_messages = [
                *run_messages[:last_human_index],
                HumanMessage(content=context_message),
                *run_messages[last_human_index + 1:],
            ]

    state_context = ""
    user_memory_context = ""
    memory_context = ""
    stage_control_context = ""
    if load_state is not None:
        state = await load_state(session_id)
        state_context = format_state_context(state)
        if state_context:
            run_messages = [*run_messages, SystemMessage(content=state_context)]
        if load_user_memory_context is not None:
            user_memory_context = await load_user_memory_context(session_id)
            if user_memory_context:
                run_messages = [*run_messages, SystemMessage(content=user_memory_context)]
        if load_memory_context is not None:
            memory_context = await load_memory_context(session_id)
            if memory_context:
                run_messages = [*run_messages, SystemMessage(content=memory_context)]
        stage_control_context = format_stage_control_context(state)
        if stage_control_context:
            run_messages = [*run_messages, SystemMessage(content=stage_control_context)]

    rag_query = build_rag_query(domain, difficulty, context_message or display_message, run_messages)
    rag_cards = await search_interview_cards(rag_query, domain)
    rag_context = format_rag_context(rag_cards)
    if rag_context:
        run_messages = [*run_messages, SystemMessage(content=rag_context)]

    return AgentInput(
        messages=run_messages,
        rag_cards=rag_cards,
        rag_context=rag_context,
        state_context=state_context,
        running_summary_context=running_summary_context,
        user_memory_context=user_memory_context,
        memory_context=memory_context,
        stage_control_context=stage_control_context,
    )
