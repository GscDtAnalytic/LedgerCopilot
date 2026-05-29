"""Dev seed: ensure the default organization exists.

Called at API startup in development. Phase 4 replaces this with proper
per-tenant onboarding. This is the only place the "default" org_id is created.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.organization import Organization

DEFAULT_ORG_ID = "default"
DEFAULT_ORG_SLUG = "default"


async def ensure_default_org(session: AsyncSession) -> None:
    existing = await session.scalar(
        select(Organization).where(Organization.id == DEFAULT_ORG_ID)
    )
    if existing is None:
        session.add(Organization(id=DEFAULT_ORG_ID, name="Default", slug=DEFAULT_ORG_SLUG))
        await session.commit()
