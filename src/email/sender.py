"""
Email sender using SMTP (Gmail compatible).

Usage:
    from src.email.sender import send_report_email
    await send_report_email(
        to_addresses=["owner@store.com"],
        subject="Weekly Analytics Report",
        html_body="<html>...</html>",
    )
"""

import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _get_smtp_config() -> dict:
    """Load SMTP configuration from environment."""
    load_dotenv()
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_addr": os.getenv("EMAIL_FROM", ""),
    }


def send_report_email_sync(
    to_addresses: list[str],
    subject: str,
    html_body: str,
    plain_text: str | None = None,
) -> bool:
    """
    Send an email synchronously via SMTP.

    Returns True if sent successfully, False otherwise.
    """
    config = _get_smtp_config()

    if not config["user"] or not config["password"]:
        logger.warning("SMTP credentials not configured. Skipping email send.")
        logger.info(f"Would have sent to: {to_addresses}")
        logger.info(f"Subject: {subject}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["from_addr"] or config["user"]
    msg["To"] = ", ".join(to_addresses)

    # Plain text fallback
    if plain_text:
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))

    # HTML body
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(config["host"], config["port"]) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config["user"], config["password"])
            server.sendmail(
                config["from_addr"] or config["user"],
                to_addresses,
                msg.as_string(),
            )
        logger.info(f"Email sent to {to_addresses}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


async def send_report_email(
    to_addresses: list[str],
    subject: str,
    html_body: str,
    plain_text: str | None = None,
) -> bool:
    """Async wrapper around the sync email sender."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        send_report_email_sync,
        to_addresses,
        subject,
        html_body,
        plain_text,
    )
