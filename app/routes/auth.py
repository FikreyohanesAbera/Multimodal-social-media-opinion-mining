# app/routes/auth.py
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.middleware.auth import CurrentUser
from app.models.auth_schemas import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserPublic,
    VerifyEmailRequest,
)
from app.services.auth_repository import (
    consume_email_verification_token,
    consume_password_reset_token,
    create_email_verification_token,
    create_password_reset_token,
    create_user,
    get_password_hash,
    get_user_by_email,
    get_user_by_id,
    mark_user_verified,
    update_password_hash,
)
from app.services.email import send_password_reset_email, send_verification_email
from app.services.password import hash_password, verify_password
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/register
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user with email + password",
)
async def register(body: RegisterRequest, request: Request) -> AuthResponse:
    # Reject if email already exists — use a generic message to avoid enumeration
    existing = await get_user_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    pw_hash = hash_password(body.password)
    user = await create_user(
        email=body.email,
        password_hash=pw_hash,
        display_name=body.display_name,
    )

    # Issue email verification token and send welcome email
    token = await create_email_verification_token(user.id)
    await send_verification_email(to=str(user.email), token=token)

    # Log user in immediately
    request.session["userId"] = str(user.id)

    logger.info("[Auth] New user registered: %s", user.id)
    return AuthResponse(
        message="Account created. Please check your email to verify your address.",
        user=user,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/login
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in with email + password",
)
async def login(body: LoginRequest, request: Request) -> AuthResponse:
    user_row = await get_user_by_email(body.email)

    # Always run the hash check — prevents timing-based email enumeration
    dummy_hash = "$2b$12$notarealhashXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    stored_hash = user_row["password_hash"] if user_row else None

    # Fetch the password hash separately (not in the users join, so we
    # always incur the same DB round-trip cost regardless of whether the
    # user exists)
    if user_row:
        stored_hash = await get_password_hash(user_row["id"])

    hash_to_check = stored_hash or dummy_hash
    password_ok = verify_password(body.password, hash_to_check)

    if not user_row or not stored_hash or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    request.session["userId"] = str(user_row["id"])
    user = UserPublic.model_validate(user_row)

    logger.info("[Auth] User logged in: %s", user.id)
    return AuthResponse(message="Logged in successfully.", user=user)


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/logout
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/logout",
    response_model=AuthResponse,
    summary="Log out and clear session",
)
async def logout(request: Request) -> AuthResponse:
    request.session.clear()
    return AuthResponse(message="Logged out successfully.")


# ─────────────────────────────────────────────────────────────────────────────
# GET /auth/me
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get the current authenticated user",
)
async def me(user_id: UUID = CurrentUser) -> MeResponse:
    user_row = await get_user_by_id(user_id)
    if not user_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return MeResponse(user=UserPublic.model_validate(user_row))


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/verify-email
# Called when the user clicks the link in their verification email
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/verify-email",
    response_model=AuthResponse,
    summary="Verify email address using token from email",
)
async def verify_email(body: VerifyEmailRequest) -> AuthResponse:
    user_id = await consume_email_verification_token(body.token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link. Please request a new one.",
        )

    await mark_user_verified(user_id)
    logger.info("[Auth] Email verified for user: %s", user_id)
    return AuthResponse(message="Email verified successfully. Your account is now active.")


# ─────────────────────────────────────────────────────────────────────────────
# GET /auth/verify-email  (link from email clicks here)
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/verify-email",
    summary="Email verification link handler — redirects to frontend",
    include_in_schema=False,
)
async def verify_email_link(token: str) -> RedirectResponse:
    """
    The email link points here. We verify the token and redirect to the
    frontend with a success or error param.
    """
    user_id = await consume_email_verification_token(token)
    frontend = settings.frontend_url

    if not user_id:
        return RedirectResponse(
            url=f"{frontend}/verify-email?error=invalid_token",
            status_code=status.HTTP_302_FOUND,
        )

    await mark_user_verified(user_id)
    logger.info("[Auth] Email verified via link for user: %s", user_id)
    return RedirectResponse(
        url=f"{frontend}/verify-email?success=true",
        status_code=status.HTTP_302_FOUND,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/resend-verification
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/resend-verification",
    response_model=AuthResponse,
    summary="Resend email verification link",
)
async def resend_verification(user_id: UUID = CurrentUser) -> AuthResponse:
    user_row = await get_user_by_id(user_id)

    if not user_row:
        raise HTTPException(status_code=404, detail="User not found.")

    if user_row["is_verified"]:
        return AuthResponse(message="Your email is already verified.")

    token = await create_email_verification_token(user_id)
    await send_verification_email(to=user_row["email"], token=token)

    return AuthResponse(message="Verification email resent. Please check your inbox.")


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/forgot-password
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/forgot-password",
    response_model=AuthResponse,
    summary="Request a password reset email",
)
async def forgot_password(body: ForgotPasswordRequest) -> AuthResponse:
    user_row = await get_user_by_email(body.email)

    # Always return the same response — prevents email enumeration
    generic = AuthResponse(
        message="If an account with that email exists, you'll receive a reset link shortly."
    )

    if not user_row:
        return generic

    token = await create_password_reset_token(user_row["id"])
    await send_password_reset_email(to=user_row["email"], token=token)

    logger.info("[Auth] Password reset requested for user: %s", user_row["id"])
    return generic


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/reset-password
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/reset-password",
    response_model=AuthResponse,
    summary="Reset password using token from email",
)
async def reset_password(body: ResetPasswordRequest) -> AuthResponse:
    user_id = await consume_password_reset_token(body.token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link. Please request a new one.",
        )

    new_hash = hash_password(body.new_password)
    await update_password_hash(user_id, new_hash)

    logger.info("[Auth] Password reset completed for user: %s", user_id)
    return AuthResponse(message="Password reset successfully. You can now log in.")


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/change-password  (authenticated)
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/change-password",
    response_model=AuthResponse,
    summary="Change password (requires current password)",
)
async def change_password(
    body: ChangePasswordRequest,
    user_id: UUID = CurrentUser,
) -> AuthResponse:
    stored_hash = await get_password_hash(user_id)

    if not stored_hash or not verify_password(body.current_password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    new_hash = hash_password(body.new_password)
    await update_password_hash(user_id, new_hash)

    logger.info("[Auth] Password changed for user: %s", user_id)
    return AuthResponse(message="Password changed successfully.")