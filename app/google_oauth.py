# app/services/google_oauth.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.models.schemas import (
    GoogleTokenResponse,
    GoogleUserInfo,
    TokenRefreshResult,
    YouTubeChannel,
)

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

# Scopes required for YouTube sentiment analysis
YOUTUBE_SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/youtube.readonly",
])


def build_authorization_url(state: str) -> str:
    """Construct the Google OAuth2 consent URL."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": YOUTUBE_SCOPES,
        "access_type": "offline",   # Required to receive a refresh_token
        "prompt": "consent",         # Force consent screen → always get refresh_token
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> GoogleTokenResponse:
    """Exchange the OAuth2 authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return GoogleTokenResponse.model_validate(response.json())


async def refresh_access_token(refresh_token: str) -> TokenRefreshResult:
    """Use a refresh token to obtain a new access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        data = response.json()

    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=data["expires_in"])
    return TokenRefreshResult(
        access_token=data["access_token"],
        expires_at=expires_at,
    )


async def get_google_user_info(access_token: str) -> GoogleUserInfo:
    """Fetch Google profile info for the authenticated user."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return GoogleUserInfo.model_validate(response.json())


async def get_youtube_channel(access_token: str) -> YouTubeChannel | None:
    """Fetch the authenticated user's YouTube channel (proves real ownership)."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            YOUTUBE_CHANNELS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"part": "snippet,statistics", "mine": "true"},
        )
        response.raise_for_status()
        data = response.json()

    items = data.get("items", [])
    if not items:
        return None

    return YouTubeChannel.model_validate(items[0])


async def revoke_token(token: str) -> None:
    """
    Revoke an OAuth token with Google.
    Non-fatal — logs a warning if revocation fails (token may already be expired).
    """
    try:
        async with httpx.AsyncClient() as client:
            await client.post(GOOGLE_REVOKE_URL, params={"token": token})
    except Exception as exc:
        logger.warning(
            "[GoogleOAuth] Token revocation failed (non-fatal, may already be expired): %s",
            exc,
        )
