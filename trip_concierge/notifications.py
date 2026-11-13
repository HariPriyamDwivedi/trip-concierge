"""Itinerary email — dry-run by default; never sends without explicit opt-in.

Sends for real only when the traveller opted in: either by signing in to the Mail
connector (Gmail / Outlook via accounts.py, send-only scope), or server-wide with
TRIP_CONCIERGE_EMAIL_SEND=1 and SMTP_* settings. Otherwise the message is written
to outbox/ and returned as a dry run, so the agent can draft without any risk.
"""

import base64
import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from google.adk.tools.tool_context import ToolContext

from . import accounts

_OUTBOX = Path(__file__).resolve().parent.parent / "outbox"


def _build(to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = os.getenv("SMTP_FROM", "trip-concierge@example.com")
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


_ONE_ADDRESS = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+")


def _send_with_account(provider: str, token: str, sender: str, to: str, subject: str, body: str) -> None:
    if provider == "google":
        msg = _build(to, subject, body)
        msg.replace_header("From", sender)
        raw = base64.urlsafe_b64encode(bytes(msg)).decode()
        accounts.api_request("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", token, {"raw": raw})
    else:
        accounts.api_request(
            "POST",
            "https://graph.microsoft.com/v1.0/me/sendMail",
            token,
            {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
                "saveToSentItems": True,
            },
        )


def send_itinerary(to: str, subject: str, body: str, tool_context: Optional[ToolContext] = None) -> dict:
    """Send an itinerary email, or dry-run it (the default).

    Sends from the traveller's own account when the Mail connector is signed in;
    otherwise dry-runs (writes to outbox/, sends nothing) unless
    TRIP_CONCIERGE_EMAIL_SEND=1 and SMTP_HOST are set.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text itinerary.

    Returns:
        A dict describing the outcome (status "dry_run" or "sent").
    """
    if tool_context is not None:
        try:
            account = accounts.access_token(tool_context.state, "mail")
        except Exception as exc:
            return {"error": f"Mail sign-in problem: {exc}"}
        if account:
            if not _ONE_ADDRESS.fullmatch(to.strip()):
                return {"error": "give exactly one valid recipient email address"}
            provider, token, sender = account
            try:
                _send_with_account(provider, token, sender, to.strip(), subject, body)
            except Exception as exc:
                return {"error": f"Couldn't send with {accounts.PROVIDERS[provider]['label']}: {exc}"}
            return {"status": "sent", "to": to.strip(), "subject": subject, "from": sender}

    msg = _build(to, subject, body)

    if os.getenv("TRIP_CONCIERGE_EMAIL_SEND") != "1":
        _OUTBOX.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        path = _OUTBOX / f"{stamp}.eml"
        path.write_bytes(bytes(msg))
        return {"status": "dry_run", "to": to, "subject": subject, "saved_to": str(path)}

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port) as server:
        server.starttls(context=ssl.create_default_context())
        if os.getenv("SMTP_USER"):
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)
    return {"status": "sent", "to": to, "subject": subject}
