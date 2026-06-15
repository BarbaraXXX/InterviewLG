import argparse
import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

from interview_agent.agent import build_interview_agent
from interview_agent.config import llm_settings
from interview_agent.jd_parser import parse_jd
from langchain_core.messages import AIMessage, HumanMessage

from .candidate import build_candidate_llm, generate_candidate_response, get_candidate_system_prompt
from .config import test_settings
from .evaluator import evaluate_session
from .logging_config import setup_logging
from .recorder import SessionRecorder
from .schemas import QAPair, TestConfig, TestSession
from .suite import compute_summary, load_suite, resolve_suite, suite_test_config_to_test_config
from .utils import fetch_profile, format_jd, is_interview_ending

logger = logging.getLogger(__name__)


async def run_test(config: TestConfig) -> TestSession:
    now = datetime.now(timezone.utc)
    session_id = f"test_{now.strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"

    session = TestSession(
        session_id=session_id,
        config=config,
        started_at=now.isoformat(),
    )

    recorder = SessionRecorder(session, test_settings.data_dir)
    recorder.save()

    print(f"[{session_id}] 开始面试测试...")
    print(f"  领域: {config.domain} | 难度: {config.difficulty} | 候选人水平: {config.candidate_level}")

    # Parse JD if provided
    structured_jd = ""
    if config.job_description.strip():
        print("  正在解析岗位JD...")
        provider = llm_settings.get_provider()
        result = await parse_jd(config.job_description.strip(), provider)
        if result:
            structured_jd = format_jd(result)
            print(f"  JD解析完成: {getattr(result, 'position_title', 'unknown')}")

    # Fetch profile if provided
    structured_profile = ""
    if config.profile_company and config.profile_position:
        print(f"  正在获取面试偏好: {config.profile_company}/{config.profile_position}...")
        structured_profile = await fetch_profile(config.profile_company, config.profile_position)
        if structured_profile:
            print("  面试偏好获取完成")
        else:
            print("  面试偏好获取失败（vectordb 可能未启动）")

    agent = await build_interview_agent(config.domain, config.difficulty, structured_jd, structured_profile)
    candidate_llm = build_candidate_llm(config.candidate_level, config.provider)
    candidate_prompt = get_candidate_system_prompt(config.domain, config.candidate_level, config.candidate_style, config.candidate_weaknesses)

    interview_messages: list = [HumanMessage(content="你好，我准备好面试了。")]
    candidate_messages: list = []

    result = await agent.ainvoke({"messages": interview_messages})
    interview_messages = result["messages"]

    for round_num in range(1, config.max_rounds + 1):
        interviewer_msg = interview_messages[-1]
        if not isinstance(interviewer_msg, AIMessage):
            break

        question_text = interviewer_msg.content
        question_ts = datetime.now(timezone.utc).isoformat()

        candidate_messages.append(HumanMessage(content=question_text))
        answer_text = await generate_candidate_response(
            candidate_messages, candidate_llm, candidate_prompt
        )
        answer_ts = datetime.now(timezone.utc).isoformat()
        candidate_messages.append(AIMessage(content=answer_text))

        qa = QAPair(
            round=round_num,
            question=question_text,
            answer=answer_text,
            question_timestamp=question_ts,
            answer_timestamp=answer_ts,
        )
        recorder.record_qa(qa)
        recorder.save()

        print(f"  第{round_num}轮完成")

        if is_interview_ending(question_text):
            print("  检测到面试结束信号")
            break

        interview_messages.append(HumanMessage(content=answer_text))
        result = await agent.ainvoke({"messages": interview_messages})
        interview_messages = result["messages"]

    recorder.mark_completed()

    print("  正在评估面试表现...")
    evaluation = await evaluate_session(session)
    session.evaluation = evaluation

    recorder.save()

    print("\n=== 测试完成 ===")
    print(f"  会话ID: {session_id}")
    print(f"  总轮次: {session.total_rounds}")
    print(f"  总体评分: {evaluation.overall_score}/10")
    print(f"  自然度: {evaluation.style_naturalness}/10")
    print(f"  难度适当性: {evaluation.difficulty_appropriateness}/10")
    print(f"  追问质量: {evaluation.follow_up_quality}/10")
    print(f"  话题覆盖: {evaluation.topic_coverage}/10")
    print(f"  JD关联度: {evaluation.jd_relevance}/10")
    print(f"  偏好匹配度: {evaluation.profile_relevance}/10")
    print(f"  难度动态调整: {evaluation.difficulty_adaptation}/10")
    print(f"  优势: {', '.join(evaluation.strengths)}")
    print(f"  不足: {', '.join(evaluation.weaknesses)}")
    print(f"  评价: {evaluation.summary}")

    return session


async def run_suite(suite_path: str) -> None:
    suite = load_suite(Path(suite_path))
    configs = resolve_suite(suite)
    print(f"套件: {suite.name}")
    print(f"  描述: {suite.description}")
    print(f"  共 {len(configs)} 个测试配置")
    print(f"  通过阈值: overall_score >= {suite.pass_threshold}")
    print()

    started_at = datetime.now(timezone.utc).isoformat()
    sessions: list[TestSession] = []

    for i, stc in enumerate(configs, 1):
        config = suite_test_config_to_test_config(stc)
        print(f"[{i}/{len(configs)}] 运行: {config.domain}/{config.difficulty}/{config.candidate_style}")
        try:
            session = await run_test(config)
            sessions.append(session)
        except Exception as e:
            print(f"  测试失败: {e}")
            failed = TestSession(
                session_id=f"failed_{i}",
                config=config,
                started_at=datetime.now(timezone.utc).isoformat(),
                status="error",
            )
            sessions.append(failed)

    ended_at = datetime.now(timezone.utc).isoformat()
    summary = compute_summary(suite, sessions, started_at)
    summary.ended_at = ended_at

    summary_dir = test_settings.data_dir
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"suite_{suite.name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    summary_path.write_text(json.dumps(summary.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"套件结果: {summary.suite_name}")
    print(f"  总测试: {summary.total_tests}")
    print(f"  完成: {summary.completed} | 错误: {summary.errors}")
    print(f"  通过: {summary.pass_count} | 未通过: {summary.fail_count}")
    print(f"  通过率: {summary.pass_rate*100:.0f}%")
    print(f"  平均总分: {summary.avg_overall_score}/10")
    print(f"  平均JD关联度: {summary.avg_jd_relevance}/10")
    print(f"  平均偏好匹配度: {summary.avg_profile_relevance}/10")
    print(f"  平均难度调整: {summary.avg_difficulty_adaptation}/10")
    if summary.by_domain:
        print("  按领域:")
        for k, v in summary.by_domain.items():
            print(f"    {k}: 通过率 {v['pass_rate']*100:.0f}%, 均分 {v['avg_score']}/10, {v['count']}次")
    if summary.by_difficulty:
        print("  按难度:")
        for k, v in summary.by_difficulty.items():
            print(f"    {k}: 通过率 {v['pass_rate']*100:.0f}%, 均分 {v['avg_score']}/10, {v['count']}次")
    if summary.by_candidate_style:
        print("  按候选人模式:")
        for k, v in summary.by_candidate_style.items():
            print(f"    {k}: 通过率 {v['pass_rate']*100:.0f}%, 均分 {v['avg_score']}/10, {v['count']}次")
    print(f"\n结果已保存: {summary_path}")


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Interview Tester - 测试面试 Agent 的表现")
    parser.add_argument("--domain", default="backend", help="面试领域 (default: backend)")
    parser.add_argument("--difficulty", default="mid", help="面试难度 junior/mid/senior (default: mid)")
    parser.add_argument("--candidate-level", default="mid", help="候选人水平 junior/mid/senior (default: mid)")
    parser.add_argument("--max-rounds", type=int, default=50, help="最大对话轮次 (default: 50)")
    parser.add_argument("--jd", default="", help="岗位JD文本（可直接传入或用 @file.txt 从文件读取）")
    parser.add_argument("--profile-company", default="", help="面试偏好公司名")
    parser.add_argument("--profile-position", default="", help="面试偏好岗位名")
    parser.add_argument("--provider", default="", help="LLM Provider 名称（空=默认）")
    parser.add_argument("--candidate-style", default="cooperative", help="候选人行为模式 cooperative/weak/evasive/overconfident/specific_weakness (default: cooperative)")
    parser.add_argument("--weaknesses", nargs="*", default=[], help="特定弱点领域（仅 specific_weakness 模式生效）")
    parser.add_argument("--suite", default="", help="测试套件YAML文件路径（指定后忽略其他参数）")
    args = parser.parse_args()

    if args.suite:
        asyncio.run(run_suite(args.suite))
        return

    jd_text = args.jd
    if jd_text.startswith("@") and len(jd_text) > 1:
        jd_text = Path(jd_text[1:]).read_text(encoding="utf-8")

    config = TestConfig(
        domain=args.domain,
        difficulty=args.difficulty,
        candidate_level=args.candidate_level,
        max_rounds=args.max_rounds,
        job_description=jd_text,
        profile_company=args.profile_company,
        profile_position=args.profile_position,
        provider=args.provider,
        candidate_style=args.candidate_style,
        candidate_weaknesses=args.weaknesses,
    )

    session = asyncio.run(run_test(config))
    saved_path = test_settings.data_dir / f"{session.session_id}.json"
    print(f"\n结果已保存: {saved_path}")


if __name__ == "__main__":
    main()
