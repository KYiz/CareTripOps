"""Outbound email. The console backend is for local development only."""

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger("caretrip.mailer")


def send_email(to: str, subject: str, body: str) -> None:
    if settings.email_backend == "console":
        # Development only: validate_settings forbids the console backend in production, so the
        # message (which may hold a login code) is printed for the developer to read.
        log.info("console email to *@%s | %s | %s", to.rsplit("@", 1)[-1], subject, body)
        return
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
