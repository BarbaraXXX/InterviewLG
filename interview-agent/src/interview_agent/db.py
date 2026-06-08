"""SQLite database layer for users, sessions, and messages."""

import logging
import os
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.getenv("INTERVIEW_AGENT_DATA_DIR", Path.cwd() / "data"))
_DB_PATH = _DATA_DIR / "interview.db"

_TTL_SECONDS = 3600
_MAX_MESSAGES_PER_SESSION = 200
_MAX_SESSIONS_AFTER_RETENTION = 50
_MAX_SESSIONS_BEFORE_RETENTION = 55
_MAX_RESUMES_PER_USER = 3


async def get_db() -> aiosqlite.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(_DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                domain TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                structured_jd TEXT NOT NULL DEFAULT '',
                structured_profile TEXT NOT NULL DEFAULT '',
                resume_title_snapshot TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                projects TEXT NOT NULL DEFAULT '',
                skills TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_interview_configs (
                user_id INTEGER PRIMARY KEY,
                domain TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                job_description TEXT NOT NULL DEFAULT '',
                profile_company TEXT NOT NULL DEFAULT '',
                profile_position TEXT NOT NULL DEFAULT '',
                resume_id INTEGER,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'ai')),
                content TEXT NOT NULL,
                seq INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS coding_tasks (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                language TEXT NOT NULL,
                starter_code TEXT NOT NULL DEFAULT '',
                constraints_json TEXT NOT NULL DEFAULT '[]',
                examples_json TEXT NOT NULL DEFAULT '[]',
                draft_language TEXT,
                draft_code TEXT,
                submitted_language TEXT,
                submitted_code TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                submitted_at TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS session_states (
                session_id TEXT PRIMARY KEY,
                target TEXT NOT NULL DEFAULT 'campus_fulltime',
                stage TEXT NOT NULL DEFAULT 'opening',
                stage_round INTEGER NOT NULL DEFAULT 0,
                total_round INTEGER NOT NULL DEFAULT 0,
                current_topic TEXT NOT NULL DEFAULT '',
                topic_status TEXT NOT NULL DEFAULT 'not_started',
                covered_topics TEXT NOT NULL DEFAULT '[]',
                pending_focus TEXT NOT NULL DEFAULT '',
                last_user_quality TEXT NOT NULL DEFAULT '',
                stage_goal_status TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(id, user_id);
            CREATE INDEX IF NOT EXISTS idx_resumes_user ON resumes(user_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_coding_tasks_session ON coding_tasks(session_id, created_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_coding_tasks_one_active
                ON coding_tasks(session_id) WHERE status = 'active';
        """)
        await _ensure_column(db, "sessions", "resume_title_snapshot", "TEXT NOT NULL DEFAULT ''")
        await _ensure_column(db, "coding_tasks", "draft_language", "TEXT")
        await _ensure_column(db, "coding_tasks", "draft_code", "TEXT")
        await _ensure_column(db, "session_states", "current_topic", "TEXT NOT NULL DEFAULT ''")
        await _ensure_column(db, "session_states", "topic_status", "TEXT NOT NULL DEFAULT 'not_started'")
        await _ensure_column(db, "session_states", "stage_goal_status", "TEXT NOT NULL DEFAULT '{}'")
        await db.commit()
        logger.info("database initialized at %s", _DB_PATH)
    finally:
        await db.close()


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, definition: str) -> None:
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        rows = await cursor.fetchall()
    if any(row["name"] == column for row in rows):
        return
    await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# ── users ──────────────────────────────────────────────────────────


async def create_user(username: str, password_hash: str) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        await db.commit()
        user_id = cursor.lastrowid
        logger.info("user created id=%d username=%s", user_id, username)
        return user_id
    finally:
        await db.close()


async def get_user_by_username(username: str) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def get_user_by_id(user_id: int) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


# ── sessions ───────────────────────────────────────────────────────


async def create_session(
    session_id: str,
    user_id: int,
    username: str,
    domain: str,
    difficulty: str,
    structured_jd: str = "",
    structured_profile: str = "",
    resume_title_snapshot: str = "",
) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO sessions "
            "(id, user_id, username, domain, difficulty, structured_jd, structured_profile, resume_title_snapshot) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                user_id,
                username,
                domain,
                difficulty,
                structured_jd,
                structured_profile,
                resume_title_snapshot,
            ),
        )
        await db.execute(
            "INSERT INTO session_states (session_id, target) VALUES (?, ?)",
            (session_id, difficulty),
        )
        await db.commit()
        logger.info("session created id=%s user=%s", session_id, username)
    finally:
        await db.close()


async def get_session_state(session_id: str) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT session_id, target, stage, stage_round, total_round, covered_topics, "
            "current_topic, topic_status, pending_focus, last_user_quality, stage_goal_status, updated_at "
            "FROM session_states WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def ensure_session_state(session_id: str, target: str = "campus_fulltime") -> dict:
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO session_states (session_id, target) VALUES (?, ?)",
            (session_id, target),
        )
        await db.commit()
    finally:
        await db.close()

    row = await get_session_state(session_id)
    if row is None:
        raise RuntimeError("Session state was not persisted")
    return row


async def set_session_state_stage(session_id: str, stage: str) -> dict | None:
    row = await get_session_state(session_id)
    if row is None:
        return None
    if row["stage"] == stage:
        return row

    db = await get_db()
    try:
        await db.execute(
            "UPDATE session_states SET stage = ?, stage_round = 0, updated_at = datetime('now') WHERE session_id = ?",
            (stage, session_id),
        )
        await db.commit()
    finally:
        await db.close()
    return await get_session_state(session_id)


async def update_session_state_control(
    session_id: str,
    *,
    stage: str | None = None,
    current_topic: str | None = None,
    topic_status: str | None = None,
    covered_topics: str | None = None,
    pending_focus: str | None = None,
    last_user_quality: str | None = None,
    stage_goal_status: str | None = None,
) -> dict | None:
    row = await get_session_state(session_id)
    if row is None:
        return None

    next_stage = stage if stage is not None else row["stage"]
    stage_round = 0 if stage is not None and stage != row["stage"] else row["stage_round"]

    db = await get_db()
    try:
        await db.execute(
            "UPDATE session_states SET "
            "stage = ?, stage_round = ?, current_topic = ?, topic_status = ?, covered_topics = ?, "
            "pending_focus = ?, last_user_quality = ?, stage_goal_status = ?, updated_at = datetime('now') "
            "WHERE session_id = ?",
            (
                next_stage,
                stage_round,
                current_topic if current_topic is not None else row["current_topic"],
                topic_status if topic_status is not None else row["topic_status"],
                covered_topics if covered_topics is not None else row["covered_topics"],
                pending_focus if pending_focus is not None else row["pending_focus"],
                last_user_quality if last_user_quality is not None else row["last_user_quality"],
                stage_goal_status if stage_goal_status is not None else row["stage_goal_status"],
                session_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    return await get_session_state(session_id)


async def advance_session_state(
    session_id: str,
    target: str,
    *,
    has_active_coding_task: bool = False,
    is_coding_submission: bool = False,
) -> dict:
    row = await ensure_session_state(session_id, target)
    old_stage = row["stage"]
    total_round = int(row["total_round"]) + 1

    stage = old_stage
    if has_active_coding_task or (old_stage == "coding" and is_coding_submission):
        stage = "coding"
    elif old_stage == "coding":
        stage = "technical"
    elif old_stage == "opening" and total_round >= 1:
        stage = "project"

    stage_round = 1 if stage != old_stage else int(row["stage_round"]) + 1

    db = await get_db()
    try:
        await db.execute(
            "UPDATE session_states SET target = ?, stage = ?, stage_round = ?, total_round = ?, "
            "updated_at = datetime('now') WHERE session_id = ?",
            (target, stage, stage_round, total_round, session_id),
        )
        await db.commit()
    finally:
        await db.close()

    updated = await get_session_state(session_id)
    if updated is None:
        raise RuntimeError("Session state was not persisted")
    return updated


async def get_session(session_id: str) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, user_id, username, domain, difficulty, structured_jd, structured_profile, "
            "resume_title_snapshot, status, created_at, ended_at FROM sessions WHERE id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def get_session_for_user(session_id: str, user_id: int) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, user_id, username, domain, difficulty, structured_jd, structured_profile, "
            "resume_title_snapshot, status, created_at, ended_at FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def update_session_status(session_id: str, status: str) -> None:
    db = await get_db()
    try:
        ended_at = "datetime('now')" if status == "completed" else None
        if ended_at:
            await db.execute(
                f"UPDATE sessions SET status = ?, ended_at = {ended_at} WHERE id = ?",
                (status, session_id),
            )
        else:
            await db.execute(
                "UPDATE sessions SET status = ? WHERE id = ?",
                (status, session_id),
            )
        await db.commit()
    finally:
        await db.close()


async def trim_user_sessions(
    user_id: int,
    keep: int = _MAX_SESSIONS_AFTER_RETENTION,
    trigger: int = _MAX_SESSIONS_BEFORE_RETENTION,
) -> list[str]:
    db = await get_db()
    try:
        async with db.execute("SELECT COUNT(*) AS cnt FROM sessions WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            session_count = row["cnt"] if row else 0
        if session_count < trigger:
            return []

        async with db.execute(
            "SELECT id FROM sessions WHERE user_id = ? "
            "ORDER BY datetime(created_at) DESC, rowid DESC LIMIT -1 OFFSET ?",
            (user_id, keep),
        ) as cursor:
            rows = await cursor.fetchall()
            session_ids = [row["id"] for row in rows]
        if not session_ids:
            return []
        await db.executemany(
            "DELETE FROM sessions WHERE id = ?",
            [(session_id,) for session_id in session_ids],
        )
        await db.commit()
        logger.info("trimmed %d old sessions for user_id=%s", len(session_ids), user_id)
        return session_ids
    finally:
        await db.close()


async def list_user_sessions(user_id: int, limit: int = 20) -> list[dict]:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT s.id, s.domain, s.difficulty, s.resume_title_snapshot, s.status, s.created_at, s.ended_at, "
            "COUNT(m.id) AS message_count "
            "FROM sessions s "
            "LEFT JOIN messages m ON m.session_id = s.id "
            "WHERE s.user_id = ? "
            "GROUP BY s.id "
            "ORDER BY s.created_at DESC LIMIT ?",
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()


async def expire_stale_sessions() -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE sessions SET status = 'expired', ended_at = datetime('now') "
            "WHERE status = 'active' AND "
            f"datetime(created_at, '+{_TTL_SECONDS} seconds') < datetime('now')"
        )
        await db.commit()
        expired = cursor.rowcount
        if expired:
            logger.info("marked %d stale sessions expired", expired)
        return expired
    finally:
        await db.close()


async def delete_session(session_id: str) -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        logger.info("session deleted id=%s", session_id)
    finally:
        await db.close()


async def delete_session_for_user(session_id: str, user_id: int) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("session deleted id=%s user_id=%s", session_id, user_id)
        return deleted
    finally:
        await db.close()


async def delete_sessions_for_user(session_ids: list[str], user_id: int) -> list[str]:
    unique_ids = list(dict.fromkeys(session_ids))
    if not unique_ids:
        return []

    db = await get_db()
    try:
        placeholders = ",".join("?" for _ in unique_ids)
        async with db.execute(
            f"SELECT id FROM sessions WHERE user_id = ? AND id IN ({placeholders})",
            (user_id, *unique_ids),
        ) as cursor:
            rows = await cursor.fetchall()
            owned_ids = [row["id"] for row in rows]

        if not owned_ids:
            return []

        await db.executemany(
            "DELETE FROM sessions WHERE id = ? AND user_id = ?",
            [(session_id, user_id) for session_id in owned_ids],
        )
        await db.commit()
        logger.info("sessions deleted count=%d user_id=%s", len(owned_ids), user_id)
        return owned_ids
    finally:
        await db.close()


# ── resumes ────────────────────────────────────────────────────────


async def list_user_resumes(user_id: int) -> list[dict]:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, user_id, title, projects, skills, created_at, updated_at "
            "FROM resumes WHERE user_id = ? ORDER BY datetime(updated_at) DESC, id DESC",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()


async def count_user_resumes(user_id: int) -> int:
    db = await get_db()
    try:
        async with db.execute("SELECT COUNT(*) AS cnt FROM resumes WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
    finally:
        await db.close()


async def get_resume_for_user(resume_id: int, user_id: int) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, user_id, title, projects, skills, created_at, updated_at "
            "FROM resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def create_resume(user_id: int, title: str, projects: str, skills: str) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO resumes (user_id, title, projects, skills) VALUES (?, ?, ?, ?)",
            (user_id, title, projects, skills),
        )
        await db.commit()
        resume_id = cursor.lastrowid
        logger.info("resume created id=%s user_id=%s", resume_id, user_id)
    finally:
        await db.close()

    resume = await get_resume_for_user(int(resume_id), user_id)
    if resume is None:
        raise RuntimeError("Resume was not persisted")
    return resume


async def update_resume(resume_id: int, user_id: int, title: str, projects: str, skills: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE resumes SET title = ?, projects = ?, skills = ?, updated_at = datetime('now') "
            "WHERE id = ? AND user_id = ?",
            (title, projects, skills, resume_id, user_id),
        )
        await db.commit()
        if cursor.rowcount <= 0:
            return None
        logger.info("resume updated id=%s user_id=%s", resume_id, user_id)
    finally:
        await db.close()
    return await get_resume_for_user(resume_id, user_id)


async def delete_resume_for_user(resume_id: int, user_id: int) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("resume deleted id=%s user_id=%s", resume_id, user_id)
        return deleted
    finally:
        await db.close()


# ── interview configs ──────────────────────────────────────────────


async def get_user_interview_config(user_id: int) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT user_id, domain, difficulty, job_description, profile_company, profile_position, resume_id, updated_at "
            "FROM user_interview_configs WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def upsert_user_interview_config(
    user_id: int,
    domain: str,
    difficulty: str,
    job_description: str,
    profile_company: str,
    profile_position: str,
    resume_id: int | None,
) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO user_interview_configs "
            "(user_id, domain, difficulty, job_description, profile_company, profile_position, resume_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "domain = excluded.domain, "
            "difficulty = excluded.difficulty, "
            "job_description = excluded.job_description, "
            "profile_company = excluded.profile_company, "
            "profile_position = excluded.profile_position, "
            "resume_id = excluded.resume_id, "
            "updated_at = datetime('now')",
            (user_id, domain, difficulty, job_description, profile_company, profile_position, resume_id),
        )
        await db.commit()
        logger.info("interview config saved user_id=%s", user_id)
    finally:
        await db.close()


# ── messages ───────────────────────────────────────────────────────


async def create_coding_task(
    task_id: str,
    session_id: str,
    title: str,
    description: str,
    language: str,
    starter_code: str,
    constraints_json: str,
    examples_json: str,
) -> dict:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO coding_tasks "
            "(id, session_id, title, description, language, starter_code, constraints_json, examples_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, session_id, title, description, language, starter_code, constraints_json, examples_json),
        )
        await db.commit()
        logger.info("coding task created id=%s session=%s", task_id, session_id)
    finally:
        await db.close()

    task = await get_coding_task(task_id)
    if task is None:
        raise RuntimeError("Coding task was not persisted")
    return task


async def get_coding_task(task_id: str) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, session_id, title, description, language, starter_code, constraints_json, examples_json, "
            "draft_language, draft_code, submitted_language, submitted_code, status, created_at, submitted_at "
            "FROM coding_tasks WHERE id = ?",
            (task_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def get_active_coding_task(session_id: str) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, session_id, title, description, language, starter_code, constraints_json, examples_json, "
            "draft_language, draft_code, submitted_language, submitted_code, status, created_at, submitted_at "
            "FROM coding_tasks WHERE session_id = ? AND status = 'active' "
            "ORDER BY datetime(created_at) DESC LIMIT 1",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def list_session_coding_tasks(session_id: str) -> list[dict]:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, session_id, title, description, language, starter_code, constraints_json, examples_json, "
            "draft_language, draft_code, submitted_language, submitted_code, status, created_at, submitted_at "
            "FROM coding_tasks WHERE session_id = ? ORDER BY datetime(created_at) ASC, rowid ASC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_coding_task_for_user(task_id: str, user_id: int) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT t.id, t.session_id, t.title, t.description, t.language, t.starter_code, "
            "t.constraints_json, t.examples_json, t.draft_language, t.draft_code, t.submitted_language, t.submitted_code, "
            "t.status, t.created_at, t.submitted_at "
            "FROM coding_tasks t "
            "JOIN sessions s ON s.id = t.session_id "
            "WHERE t.id = ? AND s.user_id = ?",
            (task_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await db.close()


async def submit_coding_task_for_user(task_id: str, user_id: int, language: str, code: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE coding_tasks SET submitted_language = ?, submitted_code = ?, status = 'submitted', "
            "submitted_at = datetime('now') "
            "WHERE id = ? AND status = 'active' AND session_id IN (SELECT id FROM sessions WHERE user_id = ?)",
            (language, code, task_id, user_id),
        )
        await db.commit()
        if cursor.rowcount <= 0:
            return None
        logger.info("coding task submitted id=%s user_id=%s", task_id, user_id)
    finally:
        await db.close()

    return await get_coding_task_for_user(task_id, user_id)


async def save_coding_task_draft_for_user(task_id: str, user_id: int, language: str, code: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE coding_tasks SET draft_language = ?, draft_code = ? "
            "WHERE id = ? AND status = 'active' AND session_id IN (SELECT id FROM sessions WHERE user_id = ?)",
            (language, code, task_id, user_id),
        )
        await db.commit()
        if cursor.rowcount <= 0:
            return None
        logger.info("coding task draft saved id=%s user_id=%s", task_id, user_id)
    finally:
        await db.close()

    return await get_coding_task_for_user(task_id, user_id)


async def create_message(session_id: str, role: str, content: str, seq: int) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO messages (session_id, role, content, seq) VALUES (?, ?, ?, ?)",
            (session_id, role, content, seq),
        )
        await db.commit()
    finally:
        await db.close()


async def get_session_messages(session_id: str, limit: int = _MAX_MESSAGES_PER_SESSION) -> list[dict]:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT role, content, seq, created_at FROM messages WHERE session_id = ? "
            "ORDER BY seq ASC LIMIT ?",
            (session_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_message_count(session_id: str) -> int:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
    finally:
        await db.close()


async def get_next_message_seq(session_id: str) -> int:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 as next_seq FROM messages WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row["next_seq"] if row else 0
    finally:
        await db.close()


async def trim_session_messages(session_id: str, keep: int = _MAX_MESSAGES_PER_SESSION) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM messages WHERE id IN ("
            "  SELECT id FROM messages WHERE session_id = ? "
            "  ORDER BY seq ASC LIMIT (SELECT MAX(0, COUNT(*) - ?) FROM messages WHERE session_id = ?)"
            ")",
            (session_id, keep, session_id),
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await db.close()
