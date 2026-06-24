import logging
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from interview_agent.config import admin_auth_settings
from interview_agent.db import create_admin_user as db_create_admin_user
from interview_agent.db import get_admin_user_by_username, update_admin_last_login

logger = logging.getLogger(__name__)

admin_security = HTTPBearer(auto_error=False)

_USERNAME_MIN_LEN = 2
_USERNAME_MAX_LEN = 32
_PASSWORD_MIN_LEN = 8
_PASSWORD_MAX_LEN = 256
_DEFAULT_SECRET = "change-me-admin-production"


def _validate_admin_secret_configured() -> None:
    if admin_auth_settings.secret_key == _DEFAULT_SECRET:
        raise HTTPException(status_code=503, detail="Admin auth secret is not configured")


def _validate_admin_username(username: str) -> str:
    username = username.strip()
    if len(username) < _USERNAME_MIN_LEN or len(username) > _USERNAME_MAX_LEN:
        raise ValueError("Invalid admin username")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Invalid admin username")
    return username


async def create_admin_user(username: str, password: str) -> int:
    username = _validate_admin_username(username)
    if len(password) < _PASSWORD_MIN_LEN or len(password) > _PASSWORD_MAX_LEN:
        raise ValueError("Invalid admin password")
    existing = await get_admin_user_by_username(username)
    if existing is not None:
        raise ValueError("Admin username already exists")
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    return await db_create_admin_user(username, password_hash)


async def authenticate_admin(username: str, password: str) -> str:
    _validate_admin_secret_configured()
    username = username.strip()
    if len(password) > _PASSWORD_MAX_LEN:
        raise ValueError("Invalid credentials")
    admin = await get_admin_user_by_username(username)
    if admin is None or int(admin["disabled"]):
        logger.warning("admin login failed user=%s", username)
        raise ValueError("Invalid credentials")
    if not bcrypt.checkpw(password.encode(), admin["password_hash"].encode()):
        logger.warning("admin login failed user=%s", username)
        raise ValueError("Invalid credentials")
    await update_admin_last_login(username)
    logger.info("admin login success user=%s", username)
    return _create_admin_token(username)


def _create_admin_token(username: str) -> str:
    _validate_admin_secret_configured()
    expire = datetime.now(UTC) + timedelta(hours=admin_auth_settings.token_expire_hours)
    payload = {"sub": username, "typ": "admin", "exp": expire}
    return jwt.encode(payload, admin_auth_settings.secret_key, algorithm="HS256")


async def get_current_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(admin_security),
) -> str:
    token = request.cookies.get(admin_auth_settings.cookie_name)
    if not token and credentials is not None:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not authenticated")

    try:
        payload = jwt.decode(token, admin_auth_settings.secret_key, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        token_type: str | None = payload.get("typ")
        if username is None or token_type != "admin":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")
        admin = await get_admin_user_by_username(username)
        if admin is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")
        if int(admin["disabled"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin disabled")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")
