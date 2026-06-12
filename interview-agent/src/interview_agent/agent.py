from typing import Literal
import logging

from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from interview_agent.context import AgentInput
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


class InterviewGraphState(MessagesState, total=False):
    agent_input: AgentInput
    stage: str
    control_actions: tuple[str, ...]
    context_sections: dict[str, str]


def _prepare_context(state: InterviewGraphState) -> dict:
    agent_input = state.get("agent_input")
    messages = agent_input.messages if agent_input is not None else state.get("messages", [])
    context_sections = {}
    if agent_input is not None:
        context_sections = {
            "state": agent_input.state_context,
            "running_summary": agent_input.running_summary_context,
            "user_memory": agent_input.user_memory_context,
            "session_memory": agent_input.memory_context,
            "stage_control": agent_input.stage_control_context,
            "rag": agent_input.rag_context,
        }
    logger.debug(
        "graph prepare_context messages=%d sections=%s",
        len(messages),
        ",".join(key for key, value in context_sections.items() if value),
    )
    return {"messages": messages, "context_sections": context_sections}


def _route_turn(state: InterviewGraphState) -> dict:
    agent_input = state.get("agent_input")
    stage = "unknown"
    actions: tuple[str, ...] = ()
    if agent_input is not None and agent_input.stage_control_context:
        stage = "controlled"
        actions = ("follow_stage_control",)
    logger.debug("graph route_turn stage=%s actions=%s", stage, actions)
    return {"stage": stage, "control_actions": actions}


def _llm_call(state: InterviewGraphState, *, llm: ChatOpenAI, system_prompt: str) -> dict:
    system = SystemMessage(content=system_prompt)
    response = llm.invoke([system] + state.get("messages", []))
    return {"messages": [response]}


def _should_continue(state: InterviewGraphState) -> Literal["tools", END]:
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

    graph = StateGraph(InterviewGraphState)

    graph.add_node("prepare_context", _prepare_context)
    graph.add_node("route_turn", _route_turn)

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

    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "route_turn")
    graph.add_edge("route_turn", "interviewer")

    return graph.compile()
