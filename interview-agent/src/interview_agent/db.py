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
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
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

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(id, user_id);
        """)
        await db.commit()
        logger.info("database initialized at %s", _DB_PATH)
    finally:
        await db.close()


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
) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO sessions (id, user_id, username, domain, difficulty, structured_jd, structured_profile) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_id, username, domain, difficulty, structured_jd, structured_profile),
        )
        await db.commit()
        logger.info("session created id=%s user=%s", session_id, username)
    finally:
        await db.close()


async def get_session(session_id: str) -> dict | None:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, user_id, username, domain, difficulty, structured_jd, structured_profile, "
            "status, created_at, ended_at FROM sessions WHERE id = ?",
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
            "status, created_at, ended_at FROM sessions WHERE id = ? AND user_id = ?",
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


async def list_user_sessions(user_id: int, limit: int = 20) -> list[dict]:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT s.id, s.domain, s.difficulty, s.status, s.created_at, s.ended_at, "
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


# ── messages ───────────────────────────────────────────────────────


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
