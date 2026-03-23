# app/models/schemas.py
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


# ── Social Account ────────────────────────────────────────────────────────────

class SocialAccountPublic(BaseModel):
    """Safe public representation — no tokens exposed."""
    id: UUID
    user_id: UUID
    platform: str
    platform_user_id: str
    platform_username: str | None
    platform_email: str | None
    avatar_url: str | None
    token_type: str
    scope: str | None
    expires_at: datetime | None
    is_active: bool
    connected_at: datetime
    last_refreshed_at: datetime | None
    disconnected_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SocialAccountInternal(SocialAccountPublic):
    """Internal representation that includes tokens — never send to client."""
    access_token: str
    refresh_token: str | None


# ── API Responses ─────────────────────────────────────────────────────────────

class ListAccountsResponse(BaseModel):
    success: bool = True
    data: list[SocialAccountPublic]
    count: int


class DisconnectResponse(BaseModel):
    success: bool = True
    message: str


class HealthResponse(BaseModel):
    status: str
    db: str
    timestamp: datetime


# ── Google OAuth ──────────────────────────────────────────────────────────────

class GoogleTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int
    token_type: str
    scope: str
    id_token: str | None = None


class GoogleUserInfo(BaseModel):
    sub: str                  # Google's stable user ID
    email: EmailStr
    email_verified: bool
    name: str
    picture: str


class YouTubeThumbnail(BaseModel):
    url: str


class YouTubeThumbnails(BaseModel):
    default: YouTubeThumbnail | None = None
    medium: YouTubeThumbnail | None = None
    high: YouTubeThumbnail | None = None


class YouTubeSnippet(BaseModel):
    title: str
    description: str | None = None
    customUrl: str | None = None
    thumbnails: YouTubeThumbnails | None = None


class YouTubeStatistics(BaseModel):
    subscriberCount: str | None = None
    videoCount: str | None = None
    viewCount: str | None = None


class YouTubeChannel(BaseModel):
    id: str
    snippet: YouTubeSnippet
    statistics: YouTubeStatistics | None = None


class TokenRefreshResult(BaseModel):
    access_token: str
    expires_at: datetime


class ConnectAccountResult(BaseModel):
    account: SocialAccountPublic
    is_new: bool
