# app/middleware/auth.py
from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status


def get_current_user_id(request: Request) -> UUID:
    """
    FastAPI dependency that extracts and validates the authenticated user's ID
    from the session.

    Replace the session lookup here with your JWT decode / cookie validation
    logic as needed.

    Raises:
        HTTPException 401: if the session has no userId (unauthenticated).
    """
    user_id: str | None = request.session.get("userId")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You must be logged in to perform this action.",
        )

    try:
        return UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session — please log in again.",
        )


# Convenient shorthand for route dependencies
CurrentUser = Depends(get_current_user_id)
