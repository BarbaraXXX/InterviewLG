"""Context assembly for one interview-agent LLM turn."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from interview_agent.rag import build_rag_query, format_rag_context, search_interview_cards


LoadMessages = Callable[[str], Awaitable[list[BaseMessage]]]


@dataclass(frozen=True)
class AgentInput:
    messages: list[BaseMessage]
    rag_cards: list[dict]
    rag_context: str


async def build_agent_input(
    *,
    session_id: str,
    domain: str,
    difficulty: str,
    display_message: str,
    context_message: str,
    load_messages: LoadMessages,
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

    rag_query = build_rag_query(domain, difficulty, context_message or display_message, run_messages)
    rag_cards = await search_interview_cards(rag_query, domain)
    rag_context = format_rag_context(rag_cards)
    if rag_context:
        run_messages = [*run_messages, SystemMessage(content=rag_context)]

    return AgentInput(messages=run_messages, rag_cards=rag_cards, rag_context=rag_context)
