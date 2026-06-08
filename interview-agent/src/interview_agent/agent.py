from typing import Literal
import logging

from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from interview_agent.config import LLMProviderConfig, llm_settings
from interview_agent.coding_tools import build_coding_tools
from interview_agent.mcp_client import get_mcp_tools
from interview_agent.prompts import build_system_prompt

logger = logging.getLogger(__name__)


def _create_llm(tools: list, provider: LLMProviderConfig) -> ChatOpenAI:
    llm = ChatOpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=provider.model,
        temperature=0.7,
        #temprature 0.7过大，但由于当前可参考数据少，如果temprature太低，每次面试都会显得一样；
    )
    if tools:
        llm = llm.bind_tools(tools)
    return llm


def _llm_call(state: MessagesState, *, llm: ChatOpenAI, system_prompt: str) -> dict:
    system = SystemMessage(content=system_prompt)
    response = llm.invoke([system] + state["messages"])
    return {"messages": [response]}


def _should_continue(state: MessagesState) -> Literal["tools", END]:
    return tools_condition(state)


async def build_interview_agent(
    domain: str,
    difficulty: str,
    structured_jd: str = "",
    structured_profile: str = "",
    provider_name: str | None = None,
    session_id: str | None = None,
) -> Runnable:
    provider = llm_settings.get_provider(provider_name)
    masked_key = (provider.api_key[:8] + "...") if len(provider.api_key) > 8 else provider.api_key
    logger.info("building agent provider=%s model=%s api_key=%s domain=%s difficulty=%s", provider_name or llm_settings.default_provider, provider.model, masked_key, domain, difficulty)
    tools = await get_mcp_tools()
    if session_id:
        tools = [*tools, *build_coding_tools(session_id)]
    llm = _create_llm(tools, provider)
    system_prompt = build_system_prompt(domain, difficulty, structured_jd, structured_profile)

    graph = StateGraph(MessagesState)

    graph.add_node(
        "interviewer",
        lambda state: _llm_call(state, llm=llm, system_prompt=system_prompt),
    )

    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges("interviewer", _should_continue, ["tools", END])
        graph.add_edge("tools", "interviewer")
    else:
        graph.add_edge("interviewer", END)

    graph.add_edge(START, "interviewer")

    return graph.compile()
