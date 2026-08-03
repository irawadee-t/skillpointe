"""
Out-of-band delivery — real email (Resend or SMTP) and SMS (Twilio).

Both send functions are **best-effort and never raise into the request path**:
they return a small result object and log failures. When no provider is
configured they no-op with ``skipped=True`` so callers can fall back to the
in-app notification row.

Email delivery order:
  1. Resend HTTP API           — when RESEND_API_KEY is set (production).
  2. SMTP (smtp_host/smtp_port) — when configured; in APP_ENV=local this
     defaults to Supabase's local mail sink (Inbucket/Mailpit) at
     localhost:54325, so local email is REALLY sent and inspectable at
     http://localhost:54324.
  3. Skipped, honestly reported in the SendResult.

These carry security-sensitive and workflow emails (account-change codes,
team invites, scheduling requests) that must reach a real inbox — so they
can't rely on the in-app notification tray alone.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(8.0)
_RESEND_ENDPOINT = "https://api.resend.com/emails"
_FROM_NAME = "SKILLED Nation"
_FROM_ADDR = "no-reply@skillpointe.org"
_FROM_EMAIL = f"{_FROM_NAME} <{_FROM_ADDR}>"

# Supabase CLI's local mail sink (Inbucket/Mailpit) SMTP port — see
# supabase/config.toml [inbucket] smtp_port.
_LOCAL_INBUCKET_SMTP = ("localhost", 54325)


@dataclass(frozen=True)
class SendResult:
    ok: bool
    skipped: bool = False          # provider not configured
    detail: str = ""

    @property
    def delivered(self) -> bool:
        return self.ok and not self.skipped


async def send_email(
    to: str, subject: str, text: str, html: Optional[str] = None
) -> SendResult:
    """Send an email (plaintext + optional HTML alternative).

    Resend when RESEND_API_KEY is set; otherwise SMTP (explicit smtp_host, or
    the local Supabase Inbucket sink when APP_ENV=local); otherwise skipped.
    """
    s = get_settings()
    if s.resend_api_key:
        return await _send_via_resend(s.resend_api_key, to, subject, text, html)
    if s.smtp_host:
        return await _send_via_smtp(s.smtp_host, s.smtp_port or 25, to, subject, text, html)
    if s.is_local:
        host, port = _LOCAL_INBUCKET_SMTP
        return await _send_via_smtp(host, port, to, subject, text, html)
    return SendResult(ok=False, skipped=True, detail="no email provider configured")


async def _send_via_resend(
    key: str, to: str, subject: str, text: str, html: Optional[str]
) -> SendResult:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "from": _FROM_EMAIL,
                    "to": [to],
                    "subject": subject,
                    "text": text,
                    **({"html": html} if html else {}),
                },
            )
        if resp.status_code >= 400:
            logger.error("Resend send failed (%s): %s", resp.status_code, resp.text[:300])
            return SendResult(ok=False, detail=f"resend {resp.status_code}")
        return SendResult(ok=True)
    except Exception as exc:  # network/timeout — caller falls back to in-app
        logger.error("Resend send errored: %s", exc)
        return SendResult(ok=False, detail=str(exc))


def _build_mime(to: str, subject: str, text: str, html: Optional[str]) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((_FROM_NAME, _FROM_ADDR))
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="skillpointe.org")
    # Plaintext first, HTML last — clients render the last part they support.
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


async def _send_via_smtp(
    host: str, port: int, to: str, subject: str, text: str, html: Optional[str]
) -> SendResult:
    msg = _build_mime(to, subject, text, html)

    def _blocking_send() -> None:
        with smtplib.SMTP(host, port, timeout=8) as smtp:
            smtp.sendmail(_FROM_ADDR, [to], msg.as_string())

    try:
        await asyncio.to_thread(_blocking_send)
        return SendResult(ok=True)
    except Exception as exc:
        logger.error("SMTP send to %s:%s errored: %s", host, port, exc)
        return SendResult(ok=False, detail=str(exc))


async def send_sms(to: str, text: str) -> SendResult:
    """Send an SMS via Twilio. No-ops unless all three Twilio settings are set."""
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number):
        return SendResult(ok=False, skipped=True, detail="Twilio not configured")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                auth=(s.twilio_account_sid, s.twilio_auth_token),
                data={"From": s.twilio_from_number, "To": to, "Body": text},
            )
        if resp.status_code >= 400:
            logger.error("Twilio send failed (%s): %s", resp.status_code, resp.text[:300])
            return SendResult(ok=False, detail=f"twilio {resp.status_code}")
        return SendResult(ok=True)
    except Exception as exc:
        logger.error("Twilio send errored: %s", exc)
        return SendResult(ok=False, detail=str(exc))
