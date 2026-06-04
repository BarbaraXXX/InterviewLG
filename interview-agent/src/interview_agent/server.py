import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import SystemMessage
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from interview_agent.auth import authenticate, get_current_user, register
from interview_agent.config import auth_settings, llm_settings, server_settings, vectordb_settings
from interview_agent.db import get_session_for_user, get_session_messages, get_user_by_username, init_db, list_user_sessions
from interview_agent.logging_config import setup_logging
from interview_agent.migrate import migrate_users_if_needed
from interview_agent.prompts import PRESET_DOMAINS
from interview_agent.rag import build_rag_query, format_rag_context, search_interview_cards
from interview_agent.session import session_manager

logger = logging.getLogger(__name__)

_APP_ROOT = Path(os.getenv("INTERVIEW_AGENT_APP_ROOT", Path.cwd()))
_STATIC_DIR = _APP_ROOT / "web" / "dist"

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if auth_settings.secret_key == "change-me-in-production":
        raise RuntimeError(
            "AUTH_SECRET_KEY is still the default 'change-me-in-production'. "
            "Set a strong secret key via AUTH_SECRET_KEY in your .env file."
        )
    await init_db()
    await migrate_users_if_needed()
    yield


app = FastAPI(title="Interview Agent", lifespan=_lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

setup_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=server_settings.get_cors_origins(),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

_MAX_MESSAGE_LEN = 4000


class RegisterRequest(BaseModel):
    username: str
    password: str
    invite_code: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=auth_settings.cookie_name,
        value=token,
        max_age=auth_settings.token_expire_hours * 3600,
        httponly=True,
        secure=auth_settings.cookie_secure,
        samesite=auth_settings.cookie_samesite,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=auth_settings.cookie_name,
        httponly=True,
        secure=auth_settings.cookie_secure,
        samesite=auth_settings.cookie_samesite,
        path="/",
    )


@app.post("/api/auth/register")
@limiter.limit("5/minute")
async def api_register(request: Request, response: Response, req: RegisterRequest) -> dict:
    username = req.username.strip()
    if len(username) < 2 or len(username) > 32:
        raise HTTPException(status_code=400, detail="Username must be 2-32 characters")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Username may only contain letters, numbers, underscores, and hyphens")
    if len(req.password) < 6 or len(req.password) > 256:
        raise HTTPException(status_code=400, detail="Password too short")
    valid_codes = auth_settings.get_invite_codes()
    if valid_codes and not req.invite_code.strip():
        raise HTTPException(status_code=400, detail="Invite code is required")
    try:
        await register(username, req.password, req.invite_code)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = await authenticate(username, req.password)
    _set_auth_cookie(response, token)
    return {"username": username}


@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def api_login(request: Request, response: Response, req: LoginRequest) -> dict:
    try:
        token = await authenticate(req.username, req.password)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _set_auth_cookie(response, token)
    return {"username": req.username.strip()}


@app.post("/api/auth/logout")
async def api_logout(response: Response) -> dict:
    _clear_auth_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
async def api_me(username: str = Depends(get_current_user)) -> dict:
    return {"username": username}


class CreateSessionRequest(BaseModel):
    domain: str
    difficulty: str = "mid"
    job_description: str = ""
    profile_company: str = ""
    profile_position: str = ""


def _sanitize_path_segment(value: str) -> str:
    stripped = value.strip()
    if ".." in stripped or "/" in stripped or "\\" in stripped:
        return ""
    return stripped[:128]


class ChatRequest(BaseModel):
    session_id: str
    message: str


_MAX_JD_FIELD_LEN = 200
_MAX_JD_ITEMS = 10


def _format_jd(jd: object) -> str:
    parts: list[str] = []
    if v := getattr(jd, "position_title", ""):
        parts.append(f"岗位：{v[:_MAX_JD_FIELD_LEN]}")
    if v := getattr(jd, "required_experience", ""):
        parts.append(f"经验要求：{v[:_MAX_JD_FIELD_LEN]}")
    skills = getattr(jd, "required_skills", [])[:_MAX_JD_ITEMS]
    if skills:
        parts.append(f"必需技能：{', '.join(s[:_MAX_JD_FIELD_LEN] for s in skills)}")
    stack = getattr(jd, "tech_stack", [])[:_MAX_JD_ITEMS]
    if stack:
        parts.append(f"技术栈：{', '.join(s[:_MAX_JD_FIELD_LEN] for s in stack)}")
    responsibilities = getattr(jd, "key_responsibilities", [])[:_MAX_JD_ITEMS]
    if responsibilities:
        items = "\n".join(f"  - {r[:_MAX_JD_FIELD_LEN]}" for r in responsibilities)
        parts.append(f"核心职责：\n{items}")
    preferred = getattr(jd, "preferred_qualifications", [])[:_MAX_JD_ITEMS]
    if preferred:
        items = "\n".join(f"  - {q[:_MAX_JD_FIELD_LEN]}" for q in preferred)
        parts.append(f"加分项：\n{items}")
    focus = getattr(jd, "interview_focus", "")
    if focus:
        parts.append(f"面试侧重：{focus[:_MAX_JD_FIELD_LEN]}")
    return "\n".join(parts)


_MAX_PROFILE_FIELD_LEN = 200


def _format_profile(profile_data: dict) -> str:
    parts: list[str] = []
    company = profile_data.get("company", "")
    position = profile_data.get("position", "")
    if company and position:
        parts.append(f"公司：{company} / 岗位：{position}")

    diff = profile_data.get("difficulty_tendency", "")
    if diff:
        diff_labels = {"junior": "初级", "mid": "中级", "senior": "高级"}
        parts.append(f"难度倾向：{diff_labels.get(diff, diff)}")

    focus = profile_data.get("focus_areas", [])
    if focus:
        parts.append(f"考查重点：{', '.join(str(f)[:_MAX_PROFILE_FIELD_LEN] for f in focus[:10])}")

    style = profile_data.get("interview_style", "")
    if style:
        parts.append(f"面试风格：{style[:500]}")

    qtypes = profile_data.get("question_types", [])
    if qtypes:
        parts.append(f"常见问题类型：{', '.join(str(t)[:_MAX_PROFILE_FIELD_LEN] for t in qtypes[:10])}")

    traits = profile_data.get("key_traits", [])
    if traits:
        parts.append(f"区分性特征：{', '.join(str(t)[:_MAX_PROFILE_FIELD_LEN] for t in traits[:10])}")

    source_count = profile_data.get("source_count", 0)
    if source_count:
        parts.append(f"（基于{source_count}份面经分析）")

    return "\n".join(parts)


async def _fetch_profile(company: str, position: str) -> str:
    safe_company = _sanitize_path_segment(company)
    safe_position = _sanitize_path_segment(position)
    if not safe_company or not safe_position:
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=20),
            follow_redirects=False,
        ) as client:
            from urllib.parse import quote
            resp = await client.get(
                f"{vectordb_settings.base_url}/api/profiles/{quote(safe_company, safe='')}/{quote(safe_position, safe='')}"
            )
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, dict):
                    return ""
                return _format_profile(data)
    except Exception:
        logger.warning("profile fetch failed company=%s position=%s", safe_company, safe_position, exc_info=True)
    return ""


@app.get("/api/domains")
async def list_domains() -> dict:
    return {"presets": list(PRESET_DOMAINS.keys())}


@app.get("/api/providers")
async def list_providers(username: str = Depends(get_current_user)) -> dict:
    providers = llm_settings.get_providers()
    return {
        "default": llm_settings.default_provider,
        "available": list(providers.keys()),
    }


@app.get("/api/profiles")
async def list_profiles(username: str = Depends(get_current_user)) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{vectordb_settings.base_url}/api/profiles")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        logger.warning("vectordb list_profiles failed", exc_info=True)
    return {"profiles": []}


_MAX_PROFILE_SIZE = 2000


def _serialize_session(session: dict) -> dict:
    return {
        "id": session["id"],
        "domain": session["domain"],
        "difficulty": session["difficulty"],
        "status": session["status"],
        "created_at": session["created_at"],
        "ended_at": session["ended_at"],
    }


@app.post("/api/sessions")
async def create_session(
    req: CreateSessionRequest, username: str = Depends(get_current_user)
) -> dict:
    if len(req.domain) > 64:
        raise HTTPException(status_code=400, detail="Domain name too long")
    if len(req.job_description) > 4000:
        raise HTTPException(status_code=400, detail="Job description too long")
    if len(req.profile_company) > 128 or len(req.profile_position) > 128:
        raise HTTPException(status_code=400, detail="Profile company/position too long")

    structured_jd = ""
    if req.job_description.strip():
        from interview_agent.jd_parser import parse_jd

        provider = llm_settings.get_provider()
        result = await parse_jd(req.job_description.strip(), provider)
        if result:
            structured_jd = _format_jd(result)

    structured_profile = ""
    if req.profile_company and req.profile_position:
        structured_profile = await _fetch_profile(req.profile_company, req.profile_position)
    if len(structured_profile) > _MAX_PROFILE_SIZE:
        structured_profile = structured_profile[:_MAX_PROFILE_SIZE] + "\n[truncated]"

    user = await get_user_by_username(username)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    user_id = user["id"]

    session_id = await session_manager.create(
        req.domain, req.difficulty, username, user_id, structured_jd, structured_profile,
    )
    logger.info(
        "create_session user=%s session=%s domain=%s difficulty=%s jd_len=%d profile_len=%d",
        username, session_id, req.domain, req.difficulty, len(structured_jd), len(structured_profile),
    )
    return {"session_id": session_id}


async def _get_current_user_row(username: str) -> dict:
    user = await get_user_by_username(username)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@app.get("/api/sessions")
async def list_sessions(username: str = Depends(get_current_user), limit: int = 20) -> dict:
    user = await _get_current_user_row(username)
    safe_limit = max(1, min(limit, 100))
    sessions = await list_user_sessions(user["id"], safe_limit)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session_detail(session_id: str, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    session = await get_session_for_user(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_session_messages(session_id)
    return {
        "session": _serialize_session(session),
        "messages": messages,
    }


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: str, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    session = await get_session_for_user(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await session_manager.end_session(session_id)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/pause")
async def pause_session(session_id: str, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    session = await get_session_for_user(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Only active sessions can be paused")
    await session_manager.pause_session(session_id)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/resume")
async def resume_session(session_id: str, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    session = await get_session_for_user(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "paused":
        raise HTTPException(status_code=409, detail="Only paused sessions can be resumed")
    resumed = await session_manager.resume_session(session_id, username, user["id"])
    if resumed is None:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = await get_session_for_user(session_id, user["id"])
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_session_messages(session_id)
    return {
        "session": _serialize_session(updated),
        "messages": messages,
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, username: str = Depends(get_current_user)):
    if len(req.message) > _MAX_MESSAGE_LEN:
        raise HTTPException(status_code=400, detail="Message too long")

    user = await _get_current_user_row(username)

    ses = await session_manager.get_or_rebuild_agent(req.session_id, username, user["id"])
    if ses is None:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info("chat_stream start user=%s session=%s msg_len=%d", username, req.session_id, len(req.message))

    await session_manager.append_message(req.session_id, "user", req.message)
    messages = await session_manager.load_messages(req.session_id)
    rag_query = build_rag_query(ses.domain, ses.difficulty, req.message, messages)
    rag_cards = await search_interview_cards(rag_query, ses.domain)
    rag_context = format_rag_context(rag_cards)
    run_messages = messages
    if rag_context:
        run_messages = [*messages, SystemMessage(content=rag_context)]
        logger.info("rag context injected session=%s cards=%d chars=%d", req.session_id, len(rag_cards), len(rag_context))

    async def event_generator():
        full_content = ""
        async for event in ses.agent.astream_events(
            {"messages": run_messages},
            version="v2",
        ):
            kind = event.get("event")
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if hasattr(chunk, "content") and chunk.content:
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        full_content += text
                        yield f"data: {json.dumps({'type': 'token', 'content': text}, ensure_ascii=False)}\n\n"
            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name}, ensure_ascii=False)}\n\n"
            elif kind == "on_tool_end":
                yield f"data: {json.dumps({'type': 'tool_end'}, ensure_ascii=False)}\n\n"

        if full_content:
            await session_manager.append_message(req.session_id, "ai", full_content)
        logger.info("chat_stream end user=%s session=%s reply_len=%d", username, req.session_id, len(full_content))
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str, username: str = Depends(get_current_user)
) -> dict:
    user = await _get_current_user_row(username)
    deleted = await session_manager.delete(session_id, username, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


if _STATIC_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = (_STATIC_DIR / full_path).resolve()
        if not str(file_path).startswith(str(_STATIC_DIR.resolve())):
            raise HTTPException(status_code=404)
        if file_path.is_file():
            headers = {}
            if file_path.name == "index.html":
                headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return FileResponse(file_path, headers=headers)
        return FileResponse(
            _STATIC_DIR / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )


def run() -> None:
    import uvicorn

    setup_logging()
    uvicorn.run(app, host=server_settings.host, port=server_settings.port)
