"""Calendar dates as travelers see them: trips, reminders and refund deadlines follow New Zealand time."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

NZ = ZoneInfo("Pacific/Auckland")


def nz_today() -> date:
    # The server runs in UTC, which is still "yesterday" for most of a New Zealand morning.
    return datetime.now(NZ).date()
