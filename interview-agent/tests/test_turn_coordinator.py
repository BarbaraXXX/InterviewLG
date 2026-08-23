import pytest

from interview_agent.turn_coordinator import SessionTurnBusyError, SessionTurnCoordinator


async def test_turn_coordinator_rejects_overlapping_turn_and_releases_after_exit():
    coordinator = SessionTurnCoordinator()

    async with coordinator.turn("session-1"):
        with pytest.raises(SessionTurnBusyError):
            async with coordinator.turn("session-1"):
                pass

    async with coordinator.turn("session-1"):
        assert coordinator.is_busy("session-1") is True


async def test_turn_coordinator_releases_after_exception():
    coordinator = SessionTurnCoordinator()

    with pytest.raises(RuntimeError):
        async with coordinator.turn("session-1"):
            raise RuntimeError("stream failed")

    assert coordinator.is_busy("session-1") is False
