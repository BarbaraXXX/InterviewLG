import asyncio

from langchain_core.messages import HumanMessage

from interview_agent.agent import build_interview_agent
from interview_agent.config import llm_settings, mcp_settings
from interview_agent.logging_config import setup_logging
from interview_agent.prompts import PRESET_DOMAINS


async def run() -> None:
    print("=== 模拟技术面试 ===")
    provider = llm_settings.get_provider()
    print(f"模型: {provider.model} @ {provider.base_url}")

    if mcp_settings.server_urls:
        print(f"MCP 服务器: {mcp_settings.server_urls}")
    else:
        print("MCP 服务器: 未配置（纯 LLM 模式）")

    print(f"\n可选领域: {', '.join(PRESET_DOMAINS.keys())}，或输入自定义领域")
    domain = input("面试领域: ").strip() or "backend"

    print("目标岗位: campus_intern（校招实习） / campus_fulltime（校招正式岗）")
    difficulty = input("目标岗位 [campus_fulltime]: ").strip() or "campus_fulltime"

    print(f"\n领域: {domain} | 目标岗位: {difficulty}")
    print("输入 'quit' 或 'exit' 结束面试\n")

    agent = await build_interview_agent(domain, difficulty)
    messages: list = []

    while True:
        user_input = input("你: ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            print("\n面试结束，感谢参与！")
            break

        messages.append(HumanMessage(content=user_input))
        result = await agent.ainvoke({"messages": messages})
        messages = result["messages"]

        ai_msg = messages[-1]
        print(f"\n面试官: {ai_msg.content}\n")


def main() -> None:
    setup_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
