"""Email notifications through an outbox: written with the business change, sent by the worker."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.db import CaseMember, Notification, SessionLocal, User
from app.mailer import send_email

log = logging.getLogger("caretrip.notify")
MAX_ATTEMPTS = 5

TEMPLATES = {
    "ORDER_CONFIRMED": {
        "en": ("Your trip is booked", "The {destination} trip is confirmed. Booking reference {booking_ref}. "
               "Total {amount}. Free cancellation rules are shown in the app."),
        "zh": ("你的行程已预订成功", "{destination}行程已确认，预订号 {booking_ref}，总计 {amount}。"
               "取消规则请在应用中查看。"),
    },
    "ORDER_FAILED": {
        "en": ("We could not complete your booking", "The {destination} booking could not be completed ({reason}). "
               "No money was taken; any card hold has been released. A travel advisor will follow up."),
        "zh": ("预订未能完成", "{destination}行程的预订没能完成（{reason}）。没有扣款，冻结的金额已释放，旅行顾问会联系你。"),
    },
    "ORDER_CANCELLED": {
        "en": ("Your booking was cancelled", "The {destination} booking was cancelled. Refund: {refund}."),
        "zh": ("你的预订已取消", "{destination}行程的预订已取消，退款：{refund}。"),
    },
    "CANCELLATION_FAILED": {
        "en": ("Your booking could not be cancelled yet", "The hotel did not accept the cancellation of the {destination} "
               "booking ({reason}). Your booking is still confirmed and nothing was refunded. You can try again in the "
               "app, or a travel advisor will help."),
        "zh": ("预订暂时无法取消", "酒店没有接受{destination}行程的取消请求（{reason}）。你的预订仍然有效，没有退款。"
               "你可以在应用中重试，旅行顾问也会协助你。"),
    },
    "PAYMENT_NEEDED": {
        "en": ("Please complete payment", "The {destination} trip is held for you. Open the app to pay securely; "
               "the card is only charged after the supplier confirms."),
        "zh": ("请完成付款", "{destination}行程已为你保留。请打开应用安全付款，供应商确认后才会扣款。"),
    },
    "REVIEW_NEEDED": {
        "en": ("An offer needs evidence review", "Case {case_short} has an offer whose accessibility evidence is "
               "inconclusive ({product}). Open the advisor queue to decide."),
        "zh": ("有报价需要人工核验", "行程 {case_short} 的报价（{product}）无障碍证据不足，请打开顾问审核队列处理。"),
    },
    "TRIP_REMINDER_WEEK": {
        "en": ("Your trip is one week away", "{destination} starts on {date}. You are staying at {stay} "
               "(booking {booking_ref}). Open the app to print your large-print trip card."),
        "zh": ("距离出发还有一周", "{destination}行程将于 {date} 开始，住宿：{stay}（预订号 {booking_ref}）。"
               "打开应用可以打印大字版行程卡。"),
    },
    "TRIP_REMINDER_DAY": {
        "en": ("Your trip starts tomorrow", "{destination} starts tomorrow, {date}. Stay: {stay}, booking {booking_ref}. "
               "If anything goes wrong, use Help in the app. In an emergency call 111."),
        "zh": ("明天就出发啦", "{destination}行程明天（{date}）开始，住宿：{stay}，预订号 {booking_ref}。"
               "如遇问题请在应用中点击“帮助”；紧急情况请拨打 111。"),
    },
    "HELP_REQUESTED": {
        "en": ("Help requested on a CareTrip trip", "{who} asked for help on the {destination} trip: \"{message}\". "
               "Please contact them. In an emergency call 111."),
        "zh": ("CareTrip 行程中有人请求帮助", "{who} 在{destination}行程中请求帮助：“{message}”。请尽快联系对方。紧急情况请拨打 111。"),
    },
    "MEMBER_INVITED": {
        "en": ("You have been invited to a CareTrip plan", "{inviter} invited you to a New Zealand trip as {role}. "
               "Sign in with this email address to accept."),
        "zh": ("你收到了 CareTrip 行程邀请", "{inviter} 邀请你参与一次新西兰旅行（身份：{role}）。用这个邮箱登录即可接受。"),
    },
}


def queue(session, *, to: str, template: str, language: str, payload: dict, case_id: str | None = None,
          dedupe_key: str | None = None) -> None:
    """Add an email to the outbox. With a dedupe key, a message already queued under that key is not repeated."""
    values = dict(case_id=case_id, to_email=to, template=template, payload=payload, dedupe_key=dedupe_key,
                  language=language if language in ("en", "zh") else "en")
    if dedupe_key:
        session.execute(insert(Notification).values(**values).on_conflict_do_nothing(index_elements=["dedupe_key"]))
    else:
        session.add(Notification(**values))


def queue_for_members(session, case, template: str, payload: dict, *, exclude_user_id: str | None = None,
                      dedupe: str | None = None) -> int:
    """Everyone on the trip hears about it. With `dedupe`, each person gets this message once, however often
    it is queued. Returns how many people were addressed."""
    query = select(User.email).join(CaseMember, CaseMember.user_id == User.id).where(CaseMember.case_id == case.id)
    if exclude_user_id:
        query = query.where(User.id != exclude_user_id)
    emails = session.scalars(query).all()
    for email in emails:
        queue(session, to=email, template=template, language=case.language, payload=payload, case_id=case.id,
              dedupe_key=f"{dedupe}:{email}" if dedupe else None)
    return len(emails)


def queue_for_advisors(session, case, template: str, payload: dict) -> int:
    for email in settings.advisor_emails:
        queue(session, to=email, template=template, language=case.language, payload=payload, case_id=case.id)
    return len(settings.advisor_emails)


def render(template: str, language: str, payload: dict) -> tuple[str, str]:
    subject, body = TEMPLATES[template][language]
    return subject, body.format(**{key: payload.get(key, "") for key in _fields(body)})


def _fields(text: str) -> list[str]:
    import string
    return [name for _, name, _, _ in string.Formatter().parse(text) if name]


def send_pending(limit: int = 20) -> int:
    """Send pending notifications one per transaction. The row stays locked while its email is sent, so a
    crash leaves it PENDING for the next attempt and two workers never send the same email."""
    sent = 0
    for _ in range(limit):
        with SessionLocal.begin() as session:
            row = session.scalar(select(Notification).where(Notification.status == "PENDING",
                                                            Notification.next_attempt_at <= datetime.now(timezone.utc))
                                 .order_by(Notification.id).limit(1).with_for_update(skip_locked=True))
            if not row:
                break
            row.attempts += 1
            try:
                subject, body = render(row.template, row.language, row.payload)
                send_email(row.to_email, subject, body)
            except Exception as exc:
                log.warning("notification failed", extra={"notification_id": row.id, "error_type": type(exc).__name__})
                row.last_error = type(exc).__name__[:200]
                row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=30 * 2 ** (row.attempts - 1))
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "FAILED"
            else:
                row.status, row.sent_at, row.last_error = "SENT", datetime.now(timezone.utc), None
                sent += 1
    return sent
