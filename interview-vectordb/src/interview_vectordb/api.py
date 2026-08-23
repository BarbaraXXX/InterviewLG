import json
import logging
import re

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from interview_vectordb.coding_problems import CodingProblemStore
from interview_vectordb.config import embedding_settings, security_settings
from interview_vectordb.db import _CODING_PROBLEMS_DB_PATH, _EXPERIENCES_DIR, _QUESTION_CARDS_DB_PATH, ProfileDB
from interview_vectordb.embeddings import EmbeddingCompatibilityError, build_embedding_provider
from interview_vectordb.question_cards import QuestionCardStore
from interview_vectordb.schema import CodingProblemSearchRequest, InterviewExperience, QuestionCardSearchRequest

logger = logging.getLogger(__name__)

api_app = FastAPI(title="Interview VectorDB API")

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=security_settings.get_cors_origins(),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

_db = ProfileDB()
_question_card_store = QuestionCardStore(_QUESTION_CARDS_DB_PATH, build_embedding_provider(embedding_settings))
_coding_problem_store = CodingProblemStore(_CODING_PROBLEMS_DB_PATH, build_embedding_provider(embedding_settings))

_MAX_IMPORT_BATCH = 500
_PATH_SEGMENT_RE = re.compile(r'^[\w\u4e00-\u9fff\s\-().&+,]+$')


def _validate_path_segment(value: str, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        logger.warning("Invalid path segment %s: empty value", name)
        raise HTTPException(status_code=400, detail=f"{name} must not be empty")
    if ".." in stripped or len(stripped) > 128:
        logger.warning("Invalid path segment %s: %r", name, stripped)
        raise HTTPException(status_code=400, detail=f"Invalid {name}")
    return stripped


async def require_admin_token(x_admin_token: str = Header(default="")) -> None:
    expected = security_settings.admin_token.strip()
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@api_app.get("/healthz")
async def healthz():
    checks = {
        "question_cards": _question_card_store.embedding_readiness(),
        "coding_problems": _coding_problem_store.embedding_readiness(),
    }
    if not all(check["ready"] for check in checks.values()):
        return JSONResponse(status_code=503, content={"ok": False, "checks": checks})
    return {"ok": True}


@api_app.get("/api/profiles")
async def list_profiles() -> dict:
    logger.info("GET /api/profiles")
    profiles = _db.list_profiles()
    return {
        "profiles": [
            {
                "key": f"{p.company}_{p.position}",
                "company": p.company,
                "position": p.position,
                "difficulty_tendency": p.difficulty_tendency,
                "focus_areas": p.focus_areas,
                "key_traits": p.key_traits,
                "source_count": p.source_count,
            }
            for p in profiles
        ]
    }


@api_app.get("/api/profiles/{company}/{position}")
async def get_profile(company: str, position: str) -> dict:
    company = _validate_path_segment(company, "company")
    position = _validate_path_segment(position, "position")
    logger.info("GET /api/profiles/%s/%s", company, position)
    profile = _db.get_profile(company, position)
    if profile is None:
        profile = _db.get_or_generate_profile(company, position)
    return profile.model_dump()


@api_app.delete("/api/profiles/{company}/{position}", dependencies=[Depends(require_admin_token)])
async def delete_profile(company: str, position: str) -> dict:
    company = _validate_path_segment(company, "company")
    position = _validate_path_segment(position, "position")
    logger.info("DELETE /api/profiles/%s/%s", company, position)
    _db.delete_profile(company, position)
    return {"deleted": f"{company}_{position}"}


@api_app.post("/api/profiles/{company}/{position}/generate", dependencies=[Depends(require_admin_token)])
async def generate_profile(company: str, position: str) -> dict:
    company = _validate_path_segment(company, "company")
    position = _validate_path_segment(position, "position")
    logger.info("POST /api/profiles/%s/%s/generate", company, position)
    profile = _db.generate_profile(company, position)
    if profile:
        _db.save_profile(profile)
        return profile.model_dump()
    logger.warning("generate_profile: no experiences for %s/%s", company, position)
    return {"error": "No experiences found for this company/position"}


@api_app.get("/api/experiences/count")
async def experiences_count() -> dict:
    logger.info("GET /api/experiences/count")
    counts: dict[str, int] = {}
    for path in _EXPERIENCES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            key = f"{data.get('company', '')}_{data.get('position', '')}"
            counts[key] = counts.get(key, 0) + 1
        except Exception as e:
            logger.warning("Failed to read experience file %s: %s", path, e)
    return {"counts": counts}


@api_app.post("/api/experiences/import", dependencies=[Depends(require_admin_token)])
async def import_experiences(experiences: list[InterviewExperience]) -> dict:
    logger.info("POST /api/experiences/import count=%d", len(experiences))
    if len(experiences) > _MAX_IMPORT_BATCH:
        logger.warning("Import rejected: %d > max %d", len(experiences), _MAX_IMPORT_BATCH)
        raise HTTPException(status_code=400, detail=f"Max { _MAX_IMPORT_BATCH} experiences per request")
    ids = _db.add_experiences(experiences)
    logger.info("Imported %d experiences", len(ids))
    return {"imported": len(ids), "ids": ids}


@api_app.post("/api/question-cards/search")
async def search_question_cards(request: QuestionCardSearchRequest) -> dict:
    logger.info(
        "POST /api/question-cards/search domain=%s top_k=%d query_len=%d",
        request.domain,
        request.top_k,
        len(request.query),
    )
    try:
        cards = _question_card_store.search(
            request.query,
            domain=request.domain,
            top_k=request.top_k,
            min_score=request.min_score,
        )
    except EmbeddingCompatibilityError as exc:
        logger.error("question card search blocked: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"cards": cards}


@api_app.get("/api/question-cards/stats")
async def question_cards_stats() -> dict:
    logger.info("GET /api/question-cards/stats")
    return {
        "count": _question_card_store.count(),
        "domains": _question_card_store.domain_counts(),
    }


@api_app.post("/api/coding-problems/search")
async def search_coding_problems(request: CodingProblemSearchRequest) -> dict:
    logger.info(
        "POST /api/coding-problems/search difficulty=%s importance=%s answer_mode=%s top_k=%d query_len=%d",
        request.difficulty,
        request.importance,
        request.answer_mode,
        request.top_k,
        len(request.query),
    )
    try:
        problems = _coding_problem_store.search(
            request.query,
            difficulty=request.difficulty,
            importance=request.importance,
            answer_mode=request.answer_mode,
            topics=request.topics,
            exclude_ids=request.exclude_ids,
            top_k=request.top_k,
            min_score=request.min_score,
        )
    except EmbeddingCompatibilityError as exc:
        logger.error("coding problem search blocked: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"problems": problems}


@api_app.get("/api/coding-problems/stats")
async def coding_problems_stats() -> dict:
    logger.info("GET /api/coding-problems/stats")
    return {
        "count": _coding_problem_store.count(),
        **_coding_problem_store.stats(),
    }


@api_app.get("/api/coding-problems/{problem_id}")
async def get_coding_problem(problem_id: str) -> dict:
    problem_id = _validate_path_segment(problem_id, "problem_id")
    logger.info("GET /api/coding-problems/%s", problem_id)
    problem = _coding_problem_store.get(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Coding problem not found")
    return {"problem": problem}
