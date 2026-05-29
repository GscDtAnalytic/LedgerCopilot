"""POST /api/v1/auth/login — JWT authentication.

Demo users are seeded in apps/api/seed.py.
  analyst@demo.com  / demo123  — can read cases, submit reviews
  approver@demo.com / demo123  — can approve/reject (incl. high-value)
  admin@demo.com    / demo123  — full access + executive dashboard
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, create_token, get_current_user, verify_password
from apps.api.database import get_session
from apps.api.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str
    org_id: str


class MeResponse(BaseModel):
    user_id: str
    email: str
    role: str
    org_id: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    token = create_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        org_id=user.organization_id,
    )
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        role=user.role,
        org_id=user.organization_id,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        org_id=user.org_id,
    )
