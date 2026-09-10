"""Shared FastAPI dependencies: current user, role guards, pagination."""
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import PermissionDeniedError

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(authorization: Annotated[str | None, Header()] = None):
    """TODO(day-1): decode the bearer token and load the user from auth.users."""
    raise NotImplementedError("Wired up in the auth module on Day 1.")


def require_roles(*roles: str):
    """Route guard:  Depends(require_roles("admin"))"""

    async def _guard(user=Depends(get_current_user)):
        if roles and getattr(user, "role", None) not in roles:
            raise PermissionDeniedError("Insufficient role for this operation.")
        return user

    return _guard


class Pagination:
    def __init__(self, page: int = 1, size: int = 25):
        self.page = max(page, 1)
        self.size = min(max(size, 1), 200)
        self.offset = (self.page - 1) * self.size
