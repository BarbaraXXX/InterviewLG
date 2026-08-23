"""Per-session coordination for interview turns."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class SessionTurnBusyError(RuntimeError):
    """Raised when another turn is already running for the same session."""


class SessionTurnCoordinator:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def is_busy(self, session_id: str) -> bool:
        lock = self._locks.get(session_id)
        return bool(lock and lock.locked())

    async def acquire(self, session_id: str) -> None:
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        if lock.locked():
            raise SessionTurnBusyError(f"Interview turn already in progress for session {session_id}")
        await lock.acquire()

    def release(self, session_id: str) -> None:
        lock = self._locks.get(session_id)
        if lock is None:
            return
        if lock.locked():
            lock.release()
        self._locks.pop(session_id, None)

    @asynccontextmanager
    async def turn(self, session_id: str):
        await self.acquire(session_id)
        try:
            yield
        finally:
            self.release(session_id)


session_turn_coordinator = SessionTurnCoordinator()
