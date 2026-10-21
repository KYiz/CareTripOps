"""Outbound text messages. The console backend is for local development only."""

import logging

import httpx

from app import config

log = logging.getLogger("caretrip.sms")


def sms_enabled() -> bool:
    return config.settings.sms_backend != "off"


def send_sms(to: str, body: str) -> None:
    settings = config.settings
    if settings.sms_backend == "console":
        # validate_settings forbids this in production; the message may hold a sign-in code.
        log.info("console sms to ***%s | %s", to[-3:], body)
        return
    if settings.sms_backend != "twilio":
        raise RuntimeError("Text messages are switched off")
    response = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        data={"To": to, "From": settings.twilio_from, "Body": body}, timeout=10)
    response.raise_for_status()
