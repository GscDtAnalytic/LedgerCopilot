"""JWT auth + RBAC utilities.

Uses PyJWT (transitive dependency). Passwords are SHA-256 hashed —
adequate for a demo; production would use bcrypt via passlib.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.config import settings

_ALGORITHM = "HS256"
_TTL_HOURS = 8
_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, email: str, role: str, org_id: str) -> None:
        self.user_id = user_id
        self.email = email
        self.role = role
        self.org_id = org_id


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode()).hexdigest() == hashed


def create_token(user_id: str, email: str, role: str, org_id: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "org_id": org_id,
        "exp": datetime.now(UTC) + timedelta(hours=_TTL_HOURS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def _decode(token: str) -> CurrentUser:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token.") from exc
    return CurrentUser(
        user_id=data["sub"],
        email=data["email"],
        role=data["role"],
        org_id=data["org_id"],
    )


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return _decode(creds.credentials)


def get_optional_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser | None:
    if creds is None:
        return None
    try:
        return _decode(creds.credentials)
    except HTTPException:
        return None


def require_roles(*roles: str):
    """Dependency factory: enforces that the current user holds one of the given roles."""
    def _check(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> CurrentUser:
        user = get_current_user(creds)
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return user
    return _check
