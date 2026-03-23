# app/services/social_account_repository.py
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from app.db.pool import execute, fetch, fetchrow, transaction
from app.models.schemas import ConnectAccountResult, SocialAccountInternal, SocialAccountPublic

logger = logging.getLogger(__name__)


# ── OAuth State (CSRF Protection) ─────────────────────────────────────────────

async def create_oauth_state(user_id: UUID) -> str:
    """
    Generate and persist a one-time CSRF state token for the OAuth flow.
    Expires after 10 minutes (enforced in DB via oauth_states.expires_at).
    """
    state = secrets.token_hex(32)

    await execute(
        "INSERT INTO oauth_states (state, user_id, platform) VALUES ($1, $2, 'youtube')",
        state,
        user_id,
    )

    # Fire-and-forget cleanup of expired states
    try:
        await execute("DELETE FROM oauth_states WHERE expires_at < NOW()")
    except Exception:
        pass  # Non-critical

    return state


async def validate_and_consume_oauth_state(state: str) -> UUID | None:
    """
    Validate the CSRF state and return the owning user_id.
    Deletes the state after validation — one-time use only.
    Returns None if the state is invalid or expired.
    """
    row = await fetchrow(
        """
        DELETE FROM oauth_states
        WHERE state = $1 AND expires_at > NOW()
        RETURNING user_id
        """,
        state,
    )
    return row["user_id"] if row else None


# ── Social Account CRUD ───────────────────────────────────────────────────────

async def upsert_social_account(
    *,
    user_id: UUID,
    platform_user_id: str,
    platform_username: str | None,
    platform_email: str | None,
    avatar_url: str | None,
    access_token: str,
    refresh_token: str | None,
    token_type: str,
    scope: str | None,
    expires_at: datetime | None,
) -> ConnectAccountResult:
    """
    Insert or update a social account after successful OAuth.
    - First connect: inserts a new row.
    - Reconnect: updates tokens and re-activates if it was disconnected.
    - Preserves existing refresh_token if Google doesn't return a new one.
    """
    async with transaction() as conn:
        existing = await conn.fetchrow(
            """
            SELECT id FROM social_accounts
            WHERE user_id = $1 AND platform = 'youtube' AND platform_user_id = $2
            """,
            user_id,
            platform_user_id,
        )
        is_new = existing is None

        row = await conn.fetchrow(
            """
            INSERT INTO social_accounts (
                user_id, platform, platform_user_id, platform_username,
                platform_email, avatar_url,
                access_token, refresh_token, token_type, scope, expires_at,
                is_active, connected_at, last_refreshed_at
            ) VALUES (
                $1, 'youtube', $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                TRUE, NOW(), NOW()
            )
            ON CONFLICT (user_id, platform, platform_user_id) DO UPDATE SET
                access_token      = EXCLUDED.access_token,
                refresh_token     = COALESCE(EXCLUDED.refresh_token, social_accounts.refresh_token),
                token_type        = EXCLUDED.token_type,
                scope             = EXCLUDED.scope,
                expires_at        = EXCLUDED.expires_at,
                platform_username = EXCLUDED.platform_username,
                platform_email    = EXCLUDED.platform_email,
                avatar_url        = EXCLUDED.avatar_url,
                is_active         = TRUE,
                connected_at      = CASE
                                      WHEN social_accounts.is_active = FALSE THEN NOW()
                                      ELSE social_accounts.connected_at
                                    END,
                last_refreshed_at = NOW(),
                disconnected_at   = NULL
            RETURNING
                id, user_id, platform, platform_user_id, platform_username,
                platform_email, avatar_url, token_type, scope, expires_at,
                is_active, connected_at, last_refreshed_at, disconnected_at,
                created_at, updated_at
            """,
            user_id, platform_user_id, platform_username, platform_email, avatar_url,
            access_token, refresh_token, token_type, scope, expires_at,
        )

    account = SocialAccountPublic.model_validate(dict(row))
    return ConnectAccountResult(account=account, is_new=is_new)


async def get_user_social_accounts(user_id: UUID) -> list[SocialAccountPublic]:
    """Return all active social accounts for a user — tokens excluded."""
    rows = await fetch(
        """
        SELECT
            id, user_id, platform, platform_user_id, platform_username,
            platform_email, avatar_url, token_type, scope, expires_at,
            is_active, connected_at, last_refreshed_at, disconnected_at,
            created_at, updated_at
        FROM social_accounts
        WHERE user_id = $1 AND is_active = TRUE
        ORDER BY connected_at DESC
        """,
        user_id,
    )
    return [SocialAccountPublic.model_validate(dict(r)) for r in rows]


async def get_social_account_with_tokens(
    account_id: UUID, user_id: UUID
) -> SocialAccountInternal | None:
    """
    Fetch a social account including tokens — for internal use only.
    Never expose SocialAccountInternal directly to API responses.
    """
    row = await fetchrow(
        "SELECT * FROM social_accounts WHERE id = $1 AND user_id = $2 AND is_active = TRUE",
        account_id,
        user_id,
    )
    return SocialAccountInternal.model_validate(dict(row)) if row else None


async def update_access_token(
    account_id: UUID, access_token: str, expires_at: datetime
) -> None:
    """Persist a refreshed access token."""
    await execute(
        """
        UPDATE social_accounts
        SET access_token = $1, expires_at = $2, last_refreshed_at = NOW()
        WHERE id = $3
        """,
        access_token,
        expires_at,
        account_id,
    )


async def disconnect_social_account(
    account_id: UUID, user_id: UUID
) -> dict | None:
    """
    Soft-disconnect: marks the account inactive and clears tokens.
    Returns the pre-wipe tokens so the caller can revoke them with Google.
    Returns None if the account was not found or already disconnected.
    """
    row = await fetchrow(
        """
        UPDATE social_accounts
        SET
            is_active       = FALSE,
            disconnected_at = NOW(),
            access_token    = '',
            refresh_token   = NULL
        WHERE id = $1 AND user_id = $2 AND is_active = TRUE
        RETURNING access_token, refresh_token
        """,
        account_id,
        user_id,
    )
    return dict(row) if row else None
