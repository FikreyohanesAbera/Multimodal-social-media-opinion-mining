# app/services/token_refresh.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.models.schemas import SocialAccountInternal
from app.services.google_oauth import refresh_access_token
from app.services.social_account_repository import (
    get_social_account_with_tokens,
    update_access_token,
)

logger = logging.getLogger(__name__)

# Refresh proactively if token expires within this window
TOKEN_EXPIRY_BUFFER = timedelta(minutes=5)


def _is_token_expired(expires_at: datetime | None) -> bool:
    """Return True if the token is expired or expires within the buffer window."""
    if expires_at is None:
        return False  # No expiry set — assume valid
    now = datetime.now(tz=timezone.utc)
    return expires_at - now < TOKEN_EXPIRY_BUFFER


async def get_valid_access_token(account_id: UUID, user_id: UUID) -> str:
    """
    Return a valid access token for the given social account.
    Automatically refreshes if the token is expired or about to expire.

    Raises:
        ValueError: if the account is not found or inactive.
        RuntimeError: if the token is expired and no refresh token is available.
    """
    account = await get_social_account_with_tokens(account_id, user_id)

    if account is None:
        raise ValueError(f"Social account {account_id} not found or inactive.")

    if not _is_token_expired(account.expires_at):
        return account.access_token

    # Token expired — attempt refresh
    if not account.refresh_token:
        raise RuntimeError(
            "Access token expired and no refresh token is available. "
            "The user must reconnect their account."
        )

    logger.info("[TokenRefresh] Refreshing token for account %s", account_id)

    result = await refresh_access_token(account.refresh_token)
    await update_access_token(account_id, result.access_token, result.expires_at)

    logger.info(
        "[TokenRefresh] Token refreshed for account %s, expires at %s",
        account_id,
        result.expires_at.isoformat(),
    )
    return result.access_token


async def refresh_expiring_tokens(accounts: list[SocialAccountInternal]) -> None:
    """
    Proactively refresh all tokens expiring within the next hour.
    Designed to be called from a scheduled background task / cron job.
    """
    one_hour = timedelta(hours=1)
    now = datetime.now(tz=timezone.utc)

    candidates = [
        a for a in accounts
        if a.refresh_token
        and a.expires_at is not None
        and (a.expires_at - now) < one_hour
        and a.is_active
    ]

    logger.info(
        "[TokenRefresh] Proactively refreshing %d expiring tokens", len(candidates)
    )

    async def _refresh_one(account: SocialAccountInternal) -> None:
        try:
            result = await refresh_access_token(account.refresh_token)  # type: ignore[arg-type]
            await update_access_token(account.id, result.access_token, result.expires_at)
            logger.info("[TokenRefresh] ✓ Refreshed account %s", account.id)
        except Exception as exc:
            logger.error(
                "[TokenRefresh] ✗ Failed to refresh account %s: %s", account.id, exc
            )

    await asyncio.gather(*[_refresh_one(a) for a in candidates])
