import json
import random
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from interview_agent.agent import build_interview_agent
from interview_agent.config import llm_settings, vectordb_settings
from interview_agent.jd_parser import parse_jd
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from .candidate import build_candidate_llm, generate_candidate_response, get_candidate_system_prompt
from .config import test_settings
from .evaluator import evaluate_session
from .logging_config import setup_logging
from .recorder import SessionRecorder
from .schemas import QAPair, TestConfig, TestSession
from .suite import compute_summary, load_suite, resolve_suite, suite_test_config_to_test_config
from .utils import fetch_profile, format_jd, is_interview_ending

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "web"
_SUITES_DIR = Path(__file__).resolve().parent.parent.parent / "suites"

app = FastAPI(title="Interview Tester")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class StartTestRequest(BaseModel):
    domain: str = "backend"
    difficulty: str = "mid"
    candidate_level: str = "mid"
    max_rounds: int = 50
    job_description: str = ""
    profile_company: str = ""
    profile_position: str = ""
    provider: str = ""
    candidate_style: str = "cooperative"
    candidate_weaknesses: list[str] = []


@app.post("/api/test/stream")
async def stream_test(req: StartTestRequest):
    config = TestConfig(
        domain=req.domain,
        difficulty=req.difficulty,
        candidate_level=req.candidate_level,
        max_rounds=req.max_rounds,
        job_description=req.job_description,
        profile_company=req.profile_company,
        profile_position=req.profile_position,
        provider=req.provider,
        candidate_style=req.candidate_style,
        candidate_weaknesses=req.candidate_weaknesses,
    )

    async def event_generator():
        now = datetime.now(timezone.utc)
        session_id = f"test_{now.strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"

        session = TestSession(
            session_id=session_id,
            config=config,
            started_at=now.isoformat(),
        )
        recorder = SessionRecorder(session, test_settings.data_dir)
        recorder.save()

        yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'config': config.model_dump()}, ensure_ascii=False)}\n\n"

        try:
            # Parse JD if provided
            structured_jd = ""
            if req.job_description.strip():
                yield f"data: {json.dumps({'type': 'status', 'message': '正在解析岗位JD...'}, ensure_ascii=False)}\n\n"
                provider = llm_settings.get_provider()
                result = await parse_jd(req.job_description.strip(), provider)
                if result:
                    structured_jd = format_jd(result)

            # Fetch profile if provided
            structured_profile = ""
            if req.profile_company and req.profile_position:
                yield f"data: {json.dumps({'type': 'status', 'message': '正在获取面试偏好...'}, ensure_ascii=False)}\n\n"
                structured_profile = await fetch_profile(req.profile_company, req.profile_position)
                if len(structured_profile) > 2000:
                    structured_profile = structured_profile[:2000] + "\n[truncated]"

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

                yield f"data: {json.dumps({'type': 'question', 'round': round_num, 'content': question_text, 'timestamp': question_ts}, ensure_ascii=False)}\n\n"

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

                yield f"data: {json.dumps({'type': 'answer', 'round': round_num, 'content': answer_text, 'timestamp': answer_ts}, ensure_ascii=False)}\n\n"

                if is_interview_ending(question_text):
                    yield f"data: {json.dumps({'type': 'ending', 'reason': 'interview_ended'}, ensure_ascii=False)}\n\n"
                    break

                interview_messages.append(HumanMessage(content=answer_text))
                result = await agent.ainvoke({"messages": interview_messages})
                interview_messages = result["messages"]

            recorder.mark_completed()

            yield f"data: {json.dumps({'type': 'evaluating'}, ensure_ascii=False)}\n\n"

            evaluation = await evaluate_session(session)
            session.evaluation = evaluation
            recorder.save()

            yield f"data: {json.dumps({'type': 'evaluation', 'data': evaluation.model_dump()}, ensure_ascii=False)}\n\n"

        except Exception as e:
            recorder.mark_error(str(e))
            recorder.save()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/profiles")
async def list_profiles():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{vectordb_settings.base_url}/api/profiles")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {"profiles": []}


@app.get("/api/sessions")
async def list_sessions():
    data_dir = test_settings.data_dir
    if not data_dir.is_dir():
        return {"sessions": []}
    sessions = []
    for f in sorted(data_dir.glob("test_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": data.get("session_id", f.stem),
                "domain": data.get("config", {}).get("domain", ""),
                "difficulty": data.get("config", {}).get("difficulty", ""),
                "total_rounds": data.get("total_rounds", 0),
                "status": data.get("status", ""),
                "started_at": data.get("started_at", ""),
                "overall_score": (data.get("evaluation") or {}).get("overall_score", None),
            })
        except Exception:
            pass
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    safe_id = session_id.replace("..", "").replace("/", "").replace("\\", "")
    path = test_settings.data_dir / f"{safe_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Session not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


@app.get("/api/suites")
async def list_suites():
    suites = []
    if _SUITES_DIR.is_dir():
        for f in sorted(_SUITES_DIR.glob("*.yaml")):
            try:
                suite = load_suite(f)
                configs = resolve_suite(suite)
                suites.append({
                    "filename": f.name,
                    "name": suite.name,
                    "description": suite.description,
                    "test_count": len(configs),
                    "pass_threshold": suite.pass_threshold,
                })
            except Exception:
                pass
    return {"suites": suites}


class SuiteRunRequest(BaseModel):
    filename: str


@app.post("/api/suite/run")
async def run_suite_stream(req: SuiteRunRequest):
    safe_name = req.filename.replace("..", "").replace("/", "").replace("\\", "")
    suite_path = _SUITES_DIR / safe_name
    if not suite_path.is_file():
        raise HTTPException(status_code=404, detail="Suite not found")

    suite = load_suite(suite_path)
    configs = resolve_suite(suite)

    async def event_generator():
        started_at = datetime.now(timezone.utc).isoformat()
        sessions: list[TestSession] = []

        yield f"data: {json.dumps({'type': 'suite_start', 'suite_name': suite.name, 'total_tests': len(configs)}, ensure_ascii=False)}\n\n"

        for i, stc in enumerate(configs, 1):
            config = suite_test_config_to_test_config(stc)
            yield f"data: {json.dumps({'type': 'test_start', 'index': i, 'total': len(configs), 'domain': config.domain, 'difficulty': config.difficulty, 'candidate_style': config.candidate_style}, ensure_ascii=False)}\n\n"

            try:
                now = datetime.now(timezone.utc)
                session_id = f"test_{now.strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
                session = TestSession(session_id=session_id, config=config, started_at=now.isoformat())
                recorder = SessionRecorder(session, test_settings.data_dir)
                recorder.save()

                structured_jd = ""
                if config.job_description.strip():
                    provider = llm_settings.get_provider()
                    result = await parse_jd(config.job_description.strip(), provider)
                    if result:
                        structured_jd = format_jd(result)

                structured_profile = ""
                if config.profile_company and config.profile_position:
                    structured_profile = await fetch_profile(config.profile_company, config.profile_position)
                    if len(structured_profile) > 2000:
                        structured_profile = structured_profile[:2000] + "\n[truncated]"

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
                    candidate_messages.append(HumanMessage(content=question_text))
                    answer_text = await generate_candidate_response(candidate_messages, candidate_llm, candidate_prompt)
                    candidate_messages.append(AIMessage(content=answer_text))

                    qa = QAPair(
                        round=round_num,
                        question=question_text,
                        answer=answer_text,
                        question_timestamp=datetime.now(timezone.utc).isoformat(),
                        answer_timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    recorder.record_qa(qa)
                    recorder.save()

                    if is_interview_ending(question_text):
                        break

                    interview_messages.append(HumanMessage(content=answer_text))
                    result = await agent.ainvoke({"messages": interview_messages})
                    interview_messages = result["messages"]

                recorder.mark_completed()
                evaluation = await evaluate_session(session)
                session.evaluation = evaluation
                recorder.save()

                yield f"data: {json.dumps({'type': 'test_done', 'index': i, 'session_id': session_id, 'overall_score': evaluation.overall_score, 'total_rounds': session.total_rounds}, ensure_ascii=False)}\n\n"
                sessions.append(session)

            except Exception as e:
                yield f"data: {json.dumps({'type': 'test_error', 'index': i, 'error': str(e)}, ensure_ascii=False)}\n\n"
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

        yield f"data: {json.dumps({'type': 'suite_done', 'summary': summary.model_dump()}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


_INDEX_HTML = _STATIC_DIR / "index.html"


if _INDEX_HTML.is_file():
    @app.get("/")
    async def serve_index():
        return FileResponse(
            _INDEX_HTML,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )


def run() -> None:
    import uvicorn
    setup_logging()
    uvicorn.run(app, host="0.0.0.0", port=8765)
