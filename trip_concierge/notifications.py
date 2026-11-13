"""Itinerary email — dry-run by default; never sends without explicit opt-in.

By default the message is written to outbox/ and returned as a dry run, so the
agent can draft without any risk of sending. Only when TRIP_CONCIERGE_EMAIL_SEND=1
and the SMTP_* env vars are set does it actually send. The agent drafts; a human
chooses to send for real.
"""

import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

_OUTBOX = Path(__file__).resolve().parent.parent / "outbox"


def _build(to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = os.getenv("SMTP_FROM", "trip-concierge@example.com")
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_itinerary(to: str, subject: str, body: str) -> dict:
    """Send an itinerary email, or dry-run it (the default).

    Dry-run unless TRIP_CONCIERGE_EMAIL_SEND=1 and SMTP_HOST are set; a dry run
    writes the message to outbox/ and sends nothing.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text itinerary.

    Returns:
        A dict describing the outcome (status "dry_run" or "sent").
    """
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
