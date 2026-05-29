"""Dev seed: default org + demo users for Phase 4 RBAC demo.

Demo credentials (all passwords: demo123):
  analyst@demo.com  — analyst role
  approver@demo.com — approver role
  admin@demo.com    — admin role
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import hash_password
from apps.api.models.organization import Organization
from apps.api.models.user import User

DEFAULT_ORG_ID = "default"
DEFAULT_ORG_SLUG = "default"

_DEMO_USERS = [
    {"id": "user-analyst", "email": "analyst@demo.com", "role": "analyst"},
    {"id": "user-approver", "email": "approver@demo.com", "role": "approver"},
    {"id": "user-admin", "email": "admin@demo.com", "role": "admin"},
]
_DEMO_PASSWORD = "demo123"


async def ensure_default_org(session: AsyncSession) -> None:
    existing = await session.scalar(
        select(Organization).where(Organization.id == DEFAULT_ORG_ID)
    )
    if existing is None:
        session.add(Organization(id=DEFAULT_ORG_ID, name="Default", slug=DEFAULT_ORG_SLUG))
        await session.commit()

    await _ensure_demo_users(session)


async def _ensure_demo_users(session: AsyncSession) -> None:
    for u in _DEMO_USERS:
        existing = await session.scalar(select(User).where(User.email == u["email"]))
        if existing is None:
            session.add(
                User(
                    id=u["id"],
                    organization_id=DEFAULT_ORG_ID,
                    email=u["email"],
                    role=u["role"],
                    password_hash=hash_password(_DEMO_PASSWORD),
                )
            )
    await session.commit()
