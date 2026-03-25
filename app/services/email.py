# app/services/email.py
"""
Email sending service.
Replace the _send() stub with your provider of choice:
  - SendGrid:  https://github.com/sendgrid/sendgrid-python
  - Resend:    https://resend.com/docs/send-with-python
  - AWS SES:   boto3 ses.send_email(...)
  - SMTP:      smtplib / aiosmtplib
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def _send(*, to: str, subject: str, html: str) -> None:
    """
    Replace this stub with your actual email provider.
    In development it logs the email to the console instead.
    """
    if settings.is_production:
        # Example using Resend:
        # import resend
        # resend.api_key = settings.resend_api_key
        # resend.Emails.send({"from": "noreply@yourdomain.com", "to": to, "subject": subject, "html": html})
        raise NotImplementedError("Wire up a real email provider for production.")
    else:
        logger.info(
            "\n─── DEV EMAIL ─────────────────────────────\n"
            "To:      %s\n"
            "Subject: %s\n"
            "Body:    %s\n"
            "────────────────────────────────────────────",
            to, subject, html,
        )


async def send_verification_email(to: str, token: str) -> None:
    verify_url = f"{settings.app_url}/auth/verify-email?token={token}"
    await _send(
        to=to,
        subject="Verify your email address",
        html=f"""
        <p>Thanks for signing up! Please verify your email address by clicking the link below.</p>
        <p><a href="{verify_url}">Verify email</a></p>
        <p>This link expires in 24 hours.</p>
        <p>If you didn't create an account, you can safely ignore this email.</p>
        """,
    )


async def send_password_reset_email(to: str, token: str) -> None:
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    await _send(
        to=to,
        subject="Reset your password",
        html=f"""
        <p>We received a request to reset your password.</p>
        <p><a href="{reset_url}">Reset password</a></p>
        <p>This link expires in 1 hour.</p>
        <p>If you didn't request this, you can safely ignore this email.</p>
        """,
    )