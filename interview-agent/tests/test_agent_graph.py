from interview_agent import agent as agent_module
from interview_agent.agent import build_interview_agent


async def test_interview_agent_graph_contains_control_nodes(monkeypatch):
    async def fake_tools():
        return []

    monkeypatch.setattr(agent_module, "get_mcp_tools", fake_tools)

    graph = await build_interview_agent("backend", "campus_fulltime")
    graph_repr = graph.get_graph()

    assert "prepare_context" in graph_repr.nodes
    assert "route_turn" in graph_repr.nodes
    assert "interviewer" in graph_repr.nodes
