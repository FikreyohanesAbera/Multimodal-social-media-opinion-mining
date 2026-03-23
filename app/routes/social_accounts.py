# app/routes/social_accounts.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.middleware.auth import CurrentUser, get_current_user_id
from app.models.schemas import (
    ConnectAccountResult,
    DisconnectResponse,
    ListAccountsResponse,
    SocialAccountPublic,
)
from app.services.google_oauth import (
    build_authorization_url,
    exchange_code_for_tokens,
    get_google_user_info,
    get_youtube_channel,
    revoke_token,
)
from app.services.social_account_repository import (
    create_oauth_state,
    disconnect_social_account,
    get_user_social_accounts,
    upsert_social_account,
    validate_and_consume_oauth_state,
)
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Social Accounts"])


# ─────────────────────────────────────────────────────────────────────────────
# GET /social-accounts
# List all connected social accounts for the authenticated user
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/social-accounts",
    response_model=ListAccountsResponse,
    summary="List connected social accounts",
)
async def list_social_accounts(
    user_id: UUID = CurrentUser,
) -> ListAccountsResponse:
    accounts = await get_user_social_accounts(user_id)
    return ListAccountsResponse(data=accounts, count=len(accounts))


# ─────────────────────────────────────────────────────────────────────────────
# GET /social-accounts/youtube/connect
# Start the YouTube OAuth2 flow — redirects user to Google
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/social-accounts/youtube/connect",
    summary="Initiate YouTube OAuth2 flow",
    response_class=RedirectResponse,
)
async def connect_youtube(user_id: UUID = CurrentUser) -> RedirectResponse:
    state = await create_oauth_state(user_id)
    auth_url = build_authorization_url(state)

    logger.info("[OAuth] Redirecting user %s to Google OAuth", user_id)
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


# ─────────────────────────────────────────────────────────────────────────────
# GET /auth/youtube/callback
# Google redirects here after the user grants (or denies) permission
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/auth/youtube/callback",
    summary="Google OAuth2 callback — do not call directly",
    include_in_schema=False,   # Hide from OpenAPI docs — only Google calls this
)
async def youtube_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    frontend = settings.frontend_url

    def redirect_error(reason: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"{frontend}/settings/accounts?error={reason}",
            status_code=status.HTTP_302_FOUND,
        )

    # User denied access on Google's consent screen
    if error:
        logger.warning("[OAuth] User denied access: %s", error)
        return redirect_error("access_denied")

    if not code or not state:
        return redirect_error("invalid_callback")

    # Validate CSRF state — resolves to the user who initiated the flow
    user_id = await validate_and_consume_oauth_state(state)
    if user_id is None:
        logger.warning("[OAuth] Invalid or expired state token")
        return redirect_error("invalid_state")

    try:
        # Exchange authorization code → tokens
        tokens = await exchange_code_for_tokens(code)

        expires_at = (
            datetime.now(tz=timezone.utc) + timedelta(seconds=tokens.expires_in)
            if tokens.expires_in
            else None
        )

        # Fetch Google profile + YouTube channel in parallel
        user_info, channel = await asyncio.gather(
            get_google_user_info(tokens.access_token),
            get_youtube_channel(tokens.access_token),
        )

        if channel is None:
            logger.warning("[OAuth] No YouTube channel found for user %s", user_id)
            return redirect_error("no_youtube_channel")

        # Resolve avatar URL (prefer YouTube thumbnail, fall back to Google picture)
        thumbnails = channel.snippet.thumbnails
        avatar_url: str | None = None
        if thumbnails:
            avatar_url = (
                (thumbnails.medium and thumbnails.medium.url)
                or (thumbnails.default and thumbnails.default.url)
            )
        if not avatar_url:
            avatar_url = user_info.picture

        # Persist the account + tokens (upsert handles reconnect gracefully)
        result = await upsert_social_account(
            user_id=user_id,
            platform_user_id=channel.id,
            platform_username=channel.snippet.customUrl or channel.snippet.title,
            platform_email=user_info.email,
            avatar_url=avatar_url,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type or "Bearer",
            scope=tokens.scope,
            expires_at=expires_at,
        )

        action = "connected" if result.is_new else "reconnected"
        logger.info(
            "[OAuth] YouTube account %s for user %s: channel=%s",
            action, user_id, channel.id,
        )

        return RedirectResponse(
            url=f"{frontend}/settings/accounts?success={action}&platform=youtube",
            status_code=status.HTTP_302_FOUND,
        )

    except Exception as exc:
        logger.exception("[OAuth] Callback failed for user %s: %s", user_id, exc)
        return redirect_error("server_error")


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /social-accounts/{account_id}
# Disconnect (revoke + soft-delete) a social account
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/social-accounts/{account_id}",
    response_model=DisconnectResponse,
    summary="Disconnect a social account",
)
async def disconnect_account(
    account_id: UUID,
    user_id: UUID = CurrentUser,
) -> DisconnectResponse:
    # Atomically clear tokens + mark inactive; get back the tokens to revoke
    tokens = await disconnect_social_account(account_id, user_id)

    if tokens is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found or already disconnected.",
        )

    # Revoke with Google in the background — don't block the response
    token_to_revoke = tokens.get("access_token") or tokens.get("refresh_token")
    if token_to_revoke:
        asyncio.create_task(revoke_token(token_to_revoke))

    logger.info("[OAuth] Account %s disconnected for user %s", account_id, user_id)

    return DisconnectResponse(message="Social account disconnected successfully.")
