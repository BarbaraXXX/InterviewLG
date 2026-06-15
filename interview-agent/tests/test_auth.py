from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from interview_agent import auth
from interview_agent.config import auth_settings
from interview_agent.db import get_user_by_username, init_db


def _make_request(token_cookie: str | None = None) -> Request:
    headers = []
    if token_cookie:
        headers.append((b"cookie", f"{auth_settings.cookie_name}={token_cookie}".encode()))
    return Request({"type": "http", "headers": headers})


def _make_creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_register_success(isolate_env):
    await init_db()
    await auth.register("alice", "secret123")
    user = await get_user_by_username("alice")
    assert user is not None
    assert bcrypt.checkpw(b"secret123", user["password_hash"].encode())
    assert user["password_hash"] != "secret123"


async def test_register_duplicate(isolate_env):
    await init_db()
    await auth.register("bob", "password1")
    with pytest.raises(ValueError):
        await auth.register("bob", "password2")


async def test_register_rejects_invalid_username(isolate_env):
    await init_db()
    with pytest.raises(ValueError):
        await auth.register("../bob", "password1")


async def test_authenticate_success(isolate_env):
    await init_db()
    await auth.register("carol", "mypassword")
    token = await auth.authenticate("carol", "mypassword")
    assert isinstance(token, str)
    assert token.count(".") == 2


async def test_authenticate_wrong_password(isolate_env):
    await init_db()
    await auth.register("dave", "rightpass")
    with pytest.raises(ValueError):
        await auth.authenticate("dave", "wrongpass")


async def test_authenticate_nonexistent_user(isolate_env):
    await init_db()
    with pytest.raises(ValueError):
        await auth.authenticate("ghost", "whatever")


def test_create_token_has_exp_claim(isolate_env):
    token = auth._create_token("eve")
    payload = jwt.decode(token, auth_settings.secret_key, algorithms=["HS256"])
    assert payload["sub"] == "eve"
    assert "exp" in payload


async def test_get_current_user_valid_cookie_token(isolate_env):
    await init_db()
    await auth.register("frank", "passw0rd")
    token = auth._create_token("frank")
    username = await auth.get_current_user(request=_make_request(token))
    assert username == "frank"


async def test_get_current_user_valid_bearer_fallback(isolate_env):
    await init_db()
    await auth.register("frank", "passw0rd")
    token = auth._create_token("frank")
    username = await auth.get_current_user(request=_make_request(), credentials=_make_creds(token))
    assert username == "frank"


async def test_get_current_user_expired_token(isolate_env):
    await init_db()
    await auth.register("grace", "passw0rd")
    expired_payload = {
        "sub": "grace",
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    token = jwt.encode(expired_payload, auth_settings.secret_key, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(request=_make_request(token))
    assert exc.value.status_code == 401


async def test_get_current_user_invalid_token(isolate_env):
    await init_db()
    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(request=_make_request("not.a.valid.token"))
    assert exc.value.status_code == 401


async def test_get_current_user_deleted_user(isolate_env):
    await init_db()
    await auth.register("henry", "passw0rd")
    token = auth._create_token("henry")
    user = await get_user_by_username("henry")
    assert user is not None
    # User deletion is not a product API yet; delete directly for token validation coverage.
    import aiosqlite

    from interview_agent import db as db_module

    conn = await aiosqlite.connect(str(db_module._DB_PATH))
    await conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    await conn.commit()
    await conn.close()

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(request=_make_request(token))
    assert exc.value.status_code == 401
