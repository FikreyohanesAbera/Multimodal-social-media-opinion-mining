# app/services/auth_repository.py
from __future__ import annotations

import secrets
from datetime import datetime
from uuid import UUID

from app.db.pool import execute, fetch, fetchrow, transaction
from app.models.auth_schemas import UserPublic


# ── Users ─────────────────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> dict | None:
    row = await fetchrow(
        "SELECT * FROM users WHERE email = $1 AND is_active = TRUE",
        email.lower(),
    )
    return dict(row) if row else None


async def get_user_by_id(user_id: UUID) -> dict | None:
    row = await fetchrow(
        "SELECT * FROM users WHERE id = $1 AND is_active = TRUE",
        user_id,
    )
    return dict(row) if row else None


async def create_user(
    email: str,
    password_hash: str,
    display_name: str | None,
) -> UserPublic:
    """
    Creates both the users row and the user_passwords row atomically.
    Returns the new user without the password hash.
    """
    async with transaction() as conn:
        user_row = await conn.fetchrow(
            """
            INSERT INTO users (email, display_name, is_active, is_verified)
            VALUES ($1, $2, TRUE, FALSE)
            RETURNING *
            """,
            email.lower(),
            display_name,
        )
        await conn.execute(
            "INSERT INTO user_passwords (user_id, password_hash) VALUES ($1, $2)",
            user_row["id"],
            password_hash,
        )

    return UserPublic.model_validate(dict(user_row))


async def get_password_hash(user_id: UUID) -> str | None:
    row = await fetchrow(
        "SELECT password_hash FROM user_passwords WHERE user_id = $1",
        user_id,
    )
    return row["password_hash"] if row else None


async def update_password_hash(user_id: UUID, new_hash: str) -> None:
    await execute(
        "UPDATE user_passwords SET password_hash = $1 WHERE user_id = $2",
        new_hash,
        user_id,
    )


async def mark_user_verified(user_id: UUID) -> None:
    await execute(
        "UPDATE users SET is_verified = TRUE WHERE id = $1",
        user_id,
    )


# ── Email Verification Tokens ─────────────────────────────────────────────────

async def create_email_verification_token(user_id: UUID) -> str:
    """Generate and store a 24-hour email verification token."""
    # Invalidate any existing unused tokens for this user first
    await execute(
        "DELETE FROM email_verification_tokens WHERE user_id = $1 AND used_at IS NULL",
        user_id,
    )
    token = secrets.token_urlsafe(48)
    await execute(
        """
        INSERT INTO email_verification_tokens (user_id, token)
        VALUES ($1, $2)
        """,
        user_id,
        token,
    )
    return token


async def consume_email_verification_token(token: str) -> UUID | None:
    """
    Validate and consume a verification token.
    Returns the user_id on success, None if invalid/expired/already used.
    """
    row = await fetchrow(
        """
        UPDATE email_verification_tokens
        SET used_at = NOW()
        WHERE token = $1
          AND expires_at > NOW()
          AND used_at IS NULL
        RETURNING user_id
        """,
        token,
    )
    return row["user_id"] if row else None


# ── Password Reset Tokens ─────────────────────────────────────────────────────

async def create_password_reset_token(user_id: UUID) -> str:
    """Generate and store a 1-hour password reset token."""
    # Invalidate any existing unused tokens
    await execute(
        "DELETE FROM password_reset_tokens WHERE user_id = $1 AND used_at IS NULL",
        user_id,
    )
    token = secrets.token_urlsafe(48)
    await execute(
        "INSERT INTO password_reset_tokens (user_id, token) VALUES ($1, $2)",
        user_id,
        token,
    )
    return token


async def consume_password_reset_token(token: str) -> UUID | None:
    """
    Validate and consume a reset token.
    Returns user_id on success, None if invalid/expired/already used.
    """
    row = await fetchrow(
        """
        UPDATE password_reset_tokens
        SET used_at = NOW()
        WHERE token = $1
          AND expires_at > NOW()
          AND used_at IS NULL
        RETURNING user_id
        """,
        token,
    )
    return row["user_id"] if row else None