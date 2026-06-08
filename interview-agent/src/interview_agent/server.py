import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from interview_agent.auth import authenticate, get_current_user, register
from interview_agent.config import auth_settings, llm_settings, server_settings, vectordb_settings
from interview_agent.context import build_agent_input
from interview_agent.db import (
    advance_session_state,
    count_user_resumes,
    create_resume,
    delete_resume_for_user,
    get_active_coding_task,
    get_coding_task_for_user,
    get_resume_for_user,
    get_session_for_user,
    get_session_messages,
    get_session_state,
    get_user_interview_config,
    get_user_by_username,
    init_db,
    list_session_coding_tasks,
    list_user_resumes,
    list_user_sessions,
    save_coding_task_draft_for_user,
    submit_coding_task_for_user,
    update_resume,
    upsert_user_interview_config,
)
from interview_agent.logging_config import setup_logging
from interview_agent.memory import load_memory_context
from interview_agent.migrate import migrate_users_if_needed
from interview_agent.prompts import PRESET_DOMAINS
from interview_agent.session import session_manager
from interview_agent.state_updater import record_turn_state

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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
    difficulty: str = "campus_fulltime"
    job_description: str = ""
    profile_company: str = ""
    profile_position: str = ""
    resume_id: int | None = None


def _sanitize_path_segment(value: str) -> str:
    stripped = value.strip()
    if ".." in stripped or "/" in stripped or "\\" in stripped:
        return ""
    return stripped[:128]


class ChatRequest(BaseModel):
    session_id: str
    message: str
    context_message: str = ""


class DeleteSessionsRequest(BaseModel):
    session_ids: list[str]


class ResumeProjectRequest(BaseModel):
    name: str
    description: str


class ResumeRequest(BaseModel):
    title: str
    projects: list[ResumeProjectRequest]
    skills: str = ""


class CodingTaskSubmitRequest(BaseModel):
    language: str
    code: str


class CodingTaskDraftRequest(BaseModel):
    language: str
    code: str


_MAX_JD_FIELD_LEN = 200
_MAX_JD_ITEMS = 10
_MAX_RESUMES_PER_USER = 3
_MAX_RESUME_TITLE_LEN = 60
_MAX_RESUME_PROJECTS = 5
_MAX_RESUME_PROJECT_NAME_LEN = 80
_MAX_RESUME_PROJECT_DESCRIPTION_LEN = 2000
_MAX_RESUME_SKILLS_LEN = 2000
_SUPPORTED_CODING_LANGUAGES = {"python", "javascript", "typescript", "java", "cpp", "go"}
_MAX_CODE_SUBMISSION_LEN = 20000
_MAX_CONTEXT_MESSAGE_LEN = 40000


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
        diff_labels = {
            "campus_intern": "校招实习",
            "campus_fulltime": "校招正式岗",
            "junior": "校招实习",
            "mid": "校招正式岗",
            "senior": "校招正式岗",
        }
        parts.append(f"目标岗位倾向：{diff_labels.get(diff, diff)}")

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
_MAX_SESSION_PROFILE_SIZE = 6000


def _serialize_session(session: dict) -> dict:
    return {
        "id": session["id"],
        "domain": session["domain"],
        "difficulty": session["difficulty"],
        "resume_title_snapshot": session.get("resume_title_snapshot", ""),
        "status": session["status"],
        "created_at": session["created_at"],
        "ended_at": session["ended_at"],
    }


def _serialize_resume(resume: dict) -> dict:
    return {
        "id": resume["id"],
        "title": resume["title"],
        "projects": _parse_resume_projects(resume["projects"]),
        "skills": resume["skills"],
        "created_at": resume["created_at"],
        "updated_at": resume["updated_at"],
    }


def _serialize_interview_config(config: dict | None) -> dict | None:
    if config is None:
        return None
    return {
        "domain": config["domain"],
        "difficulty": config["difficulty"],
        "job_description": config["job_description"],
        "profile_company": config["profile_company"],
        "profile_position": config["profile_position"],
        "resume_id": config["resume_id"],
        "updated_at": config["updated_at"],
    }


def _parse_json_list(value: str) -> list:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _serialize_coding_task(task: dict | None) -> dict | None:
    if task is None:
        return None
    return {
        "id": task["id"],
        "session_id": task["session_id"],
        "title": task["title"],
        "description": task["description"],
        "language": task["language"],
        "starter_code": task["starter_code"],
        "constraints": _parse_json_list(task["constraints_json"]),
        "examples": _parse_json_list(task["examples_json"]),
        "draft_language": task["draft_language"],
        "draft_code": task["draft_code"],
        "submitted_language": task["submitted_language"],
        "submitted_code": task["submitted_code"],
        "status": task["status"],
        "created_at": task["created_at"],
        "submitted_at": task["submitted_at"],
    }


def _clean_coding_language(language: str) -> str:
    normalized = language.strip().lower()
    aliases = {"js": "javascript", "ts": "typescript", "c++": "cpp", "golang": "go"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in _SUPPORTED_CODING_LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported coding language")
    return normalized


def _build_code_submission_context(task: dict, language: str, code: str) -> str:
    constraints = _parse_json_list(task["constraints_json"])
    examples = _parse_json_list(task["examples_json"])
    parts = [
        "用户提交了一道手撕代码题答案。",
        f"题目：{task['title']}",
        f"语言：{language}",
        f"题目描述：\n{task['description']}",
    ]
    if constraints:
        parts.append("约束：\n" + "\n".join(f"- {item}" for item in constraints))
    if examples:
        example_lines = []
        for idx, example in enumerate(examples, start=1):
            if not isinstance(example, dict):
                continue
            line = f"{idx}. 输入：{example.get('input', '')}\n   输出：{example.get('output', '')}"
            explanation = example.get("explanation", "")
            if explanation:
                line += f"\n   说明：{explanation}"
            example_lines.append(line)
        if example_lines:
            parts.append("示例：\n" + "\n".join(example_lines))
    parts.append(f"用户代码：\n```{language}\n{code}\n```")
    parts.append(
        "请作为技术面试官评价这份代码的思路、复杂度、边界条件和代码质量，"
        "然后根据表现继续追问或进入下一环节。"
    )
    return "\n\n".join(parts)


def _parse_resume_projects(raw_projects: str) -> list[dict]:
    stripped = raw_projects.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return [{"name": "项目经验", "description": stripped}]
    if not isinstance(parsed, list):
        return []

    projects = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        if name or description:
            projects.append({"name": name or "未命名项目", "description": description})
    return projects


def _clean_resume_projects(projects: list[ResumeProjectRequest]) -> list[dict]:
    if len(projects) < 1:
        raise HTTPException(status_code=400, detail="At least one project is required")
    if len(projects) > _MAX_RESUME_PROJECTS:
        raise HTTPException(status_code=400, detail="Too many resume projects")

    cleaned = []
    for project in projects:
        name = project.name.strip()
        description = project.description.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Resume project name is required")
        if not description:
            raise HTTPException(status_code=400, detail="Resume project description is required")
        if len(name) > _MAX_RESUME_PROJECT_NAME_LEN:
            raise HTTPException(status_code=400, detail="Resume project name too long")
        if len(description) > _MAX_RESUME_PROJECT_DESCRIPTION_LEN:
            raise HTTPException(status_code=400, detail="Resume project description too long")
        cleaned.append({"name": name, "description": description})
    return cleaned


def _clean_resume_request(req: ResumeRequest) -> tuple[str, str, str]:
    title = req.title.strip()
    projects = _clean_resume_projects(req.projects)
    skills = req.skills.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Resume title is required")
    if len(title) > _MAX_RESUME_TITLE_LEN:
        raise HTTPException(status_code=400, detail="Resume title too long")
    if len(skills) > _MAX_RESUME_SKILLS_LEN:
        raise HTTPException(status_code=400, detail="Resume skills too long")
    projects_json = json.dumps(projects, ensure_ascii=False)
    return title, projects_json, skills


def _format_resume_context(resume: dict) -> str:
    parts = [
        "候选人简历上下文：",
        f"简历名称：{resume['title']}",
    ]
    projects = _parse_resume_projects(resume["projects"])
    if projects:
        project_lines = []
        for idx, project in enumerate(projects, start=1):
            project_lines.append(
                f"{idx}. 项目名称：{project['name']}\n"
                f"   项目描述：{project['description']}"
            )
        parts.append("项目经验：\n" + "\n\n".join(project_lines))
    if resume["skills"]:
        parts.append(f"技能特长：\n{resume['skills']}")
    return "\n\n".join(parts)


def _combine_profile_context(profile_context: str, resume_context: str) -> str:
    parts = []
    if profile_context:
        parts.append(f"公司岗位画像：\n{profile_context}")
    if resume_context:
        parts.append(resume_context)
    return "\n\n".join(parts)


@app.get("/api/resumes")
async def list_resumes(username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    resumes = await list_user_resumes(user["id"])
    return {"resumes": [_serialize_resume(resume) for resume in resumes]}


@app.post("/api/resumes")
async def create_resume_api(req: ResumeRequest, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    if await count_user_resumes(user["id"]) >= _MAX_RESUMES_PER_USER:
        raise HTTPException(status_code=409, detail="最多只能保存 3 份简历")
    title, projects, skills = _clean_resume_request(req)
    resume = await create_resume(user["id"], title, projects, skills)
    return {"resume": _serialize_resume(resume)}


@app.put("/api/resumes/{resume_id}")
async def update_resume_api(resume_id: int, req: ResumeRequest, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    title, projects, skills = _clean_resume_request(req)
    resume = await update_resume(resume_id, user["id"], title, projects, skills)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"resume": _serialize_resume(resume)}


@app.delete("/api/resumes/{resume_id}")
async def delete_resume_api(resume_id: int, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    deleted = await delete_resume_for_user(resume_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"ok": True}


@app.get("/api/interview-config/last")
async def get_last_interview_config(username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    config = await get_user_interview_config(user["id"])
    return {"config": _serialize_interview_config(config)}


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

    user = await get_user_by_username(username)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    user_id = user["id"]

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

    resume_title_snapshot = ""
    resume_context = ""
    if req.resume_id is not None:
        resume = await get_resume_for_user(req.resume_id, user_id)
        if resume is None:
            raise HTTPException(status_code=404, detail="Resume not found")
        resume_title_snapshot = resume["title"]
        resume_context = _format_resume_context(resume)

    structured_profile = _combine_profile_context(structured_profile, resume_context)
    if len(structured_profile) > _MAX_SESSION_PROFILE_SIZE:
        structured_profile = structured_profile[:_MAX_SESSION_PROFILE_SIZE] + "\n[truncated]"

    session_id = await session_manager.create(
        req.domain,
        req.difficulty,
        username,
        user_id,
        structured_jd,
        structured_profile,
        resume_title_snapshot,
    )
    await upsert_user_interview_config(
        user_id=user_id,
        domain=req.domain.strip(),
        difficulty=req.difficulty.strip(),
        job_description=req.job_description.strip(),
        profile_company=req.profile_company.strip(),
        profile_position=req.profile_position.strip(),
        resume_id=req.resume_id,
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


@app.delete("/api/sessions")
async def delete_sessions(req: DeleteSessionsRequest, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    session_ids = [session_id.strip() for session_id in dict.fromkeys(req.session_ids) if session_id.strip()]
    if len(session_ids) > 100:
        raise HTTPException(status_code=400, detail="Too many sessions to delete")
    deleted = await session_manager.delete_many(session_ids, username, user["id"])
    return {"deleted": deleted}


@app.get("/api/sessions/{session_id}")
async def get_session_detail(session_id: str, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    session = await get_session_for_user(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_session_messages(session_id)
    coding_tasks = await list_session_coding_tasks(session_id)
    return {
        "session": _serialize_session(session),
        "messages": messages,
        "coding_tasks": [_serialize_coding_task(task) for task in coding_tasks],
    }


@app.get("/api/sessions/{session_id}/coding-task/active")
async def get_active_session_coding_task(session_id: str, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    session = await get_session_for_user(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    task = await get_active_coding_task(session_id)
    return {"task": _serialize_coding_task(task)}


@app.get("/api/sessions/{session_id}/coding-tasks")
async def list_session_coding_task_api(session_id: str, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    session = await get_session_for_user(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tasks = await list_session_coding_tasks(session_id)
    return {"tasks": [_serialize_coding_task(task) for task in tasks]}


@app.post("/api/coding-tasks/{task_id}/submit")
async def submit_coding_task(task_id: str, req: CodingTaskSubmitRequest, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    existing = await get_coding_task_for_user(task_id, user["id"])
    if existing is None:
        raise HTTPException(status_code=404, detail="Coding task not found")
    if existing["status"] != "active":
        raise HTTPException(status_code=409, detail="Coding task has already been submitted")

    language = _clean_coding_language(req.language)
    code = req.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code is required")
    if len(code) > _MAX_CODE_SUBMISSION_LEN:
        raise HTTPException(status_code=400, detail="Code submission too long")

    task = await submit_coding_task_for_user(task_id, user["id"], language, code)
    if task is None:
        raise HTTPException(status_code=409, detail="Coding task has already been submitted")
    return {
        "task": _serialize_coding_task(task),
        "context_message": _build_code_submission_context(task, language, code),
    }


@app.put("/api/coding-tasks/{task_id}/draft")
async def save_coding_task_draft(task_id: str, req: CodingTaskDraftRequest, username: str = Depends(get_current_user)) -> dict:
    user = await _get_current_user_row(username)
    existing = await get_coding_task_for_user(task_id, user["id"])
    if existing is None:
        raise HTTPException(status_code=404, detail="Coding task not found")
    if existing["status"] != "active":
        raise HTTPException(status_code=409, detail="Submitted coding task cannot be edited")

    language = _clean_coding_language(req.language)
    if len(req.code) > _MAX_CODE_SUBMISSION_LEN:
        raise HTTPException(status_code=400, detail="Code draft too long")
    task = await save_coding_task_draft_for_user(task_id, user["id"], language, req.code)
    if task is None:
        raise HTTPException(status_code=409, detail="Submitted coding task cannot be edited")
    return {"task": _serialize_coding_task(task)}


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
    if len(req.context_message) > _MAX_CONTEXT_MESSAGE_LEN:
        raise HTTPException(status_code=400, detail="Context message too long")

    user = await _get_current_user_row(username)

    ses = await session_manager.get_or_rebuild_agent(req.session_id, username, user["id"])
    if ses is None:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info("chat_stream start user=%s session=%s msg_len=%d", username, req.session_id, len(req.message))

    display_message = req.message.strip()
    context_message = req.context_message.strip()
    await session_manager.append_message(req.session_id, "user", display_message)
    active_coding_task = await get_active_coding_task(req.session_id)
    await advance_session_state(
        req.session_id,
        ses.difficulty,
        has_active_coding_task=active_coding_task is not None,
        is_coding_submission=bool(context_message),
    )
    agent_input = await build_agent_input(
        session_id=req.session_id,
        domain=ses.domain,
        difficulty=ses.difficulty,
        display_message=display_message,
        context_message=context_message,
        load_messages=session_manager.load_messages,
        load_state=get_session_state,
        load_memory_context=load_memory_context,
    )
    if agent_input.rag_context:
        logger.info(
            "rag context injected session=%s cards=%d chars=%d",
            req.session_id,
            len(agent_input.rag_cards),
            len(agent_input.rag_context),
        )

    async def record_interview_state_safely(user_message: str, agent_reply: str) -> None:
        try:
            await record_turn_state(
                session_id=req.session_id,
                user_message=user_message,
                agent_reply=agent_reply,
            )
        except Exception:
            logger.warning("interview state update failed session=%s", req.session_id, exc_info=True)

    async def event_generator():
        full_content = ""
        async for event in ses.agent.astream_events(
            {"messages": agent_input.messages},
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
            asyncio.create_task(record_interview_state_safely(context_message or display_message, full_content))
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
