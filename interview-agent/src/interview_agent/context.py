"""Context assembly for one interview-agent LLM turn."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from interview_agent.interview_state import format_state_context
from interview_agent.rag import build_rag_query, format_rag_context, search_interview_cards
from interview_agent.stage_controller import format_stage_control_context


LoadMessages = Callable[[str], Awaitable[list[BaseMessage]]]
LoadState = Callable[[str], Awaitable[dict | None]]


@dataclass(frozen=True)
class AgentInput:
    messages: list[BaseMessage]
    rag_cards: list[dict]
    rag_context: str
    state_context: str
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
) -> AgentInput:
    """Build the message list sent into the agent graph for a single turn.

    The display message is what gets persisted in chat history. The optional
    context message replaces the latest human message only for this model turn,
    which is used for large payloads such as coding submissions.
    """

    messages = await load_messages(session_id)
    run_messages = messages
    if context_message and run_messages:
        run_messages = [*run_messages[:-1], HumanMessage(content=context_message)]

    state_context = ""
    stage_control_context = ""
    if load_state is not None:
        state = await load_state(session_id)
        state_context = format_state_context(state)
        if state_context:
            run_messages = [*run_messages, SystemMessage(content=state_context)]
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
        stage_control_context=stage_control_context,
    )
