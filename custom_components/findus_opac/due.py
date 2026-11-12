"""How urgent a loan is and how close a library card is to expiry.

Sensors, binary sensors, the digest and the card all need the same thresholds, so they
live here once instead of being recomputed in each of them.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from .client import Loan
from .const import CARD_EXPIRY_WARN_DAYS

DueStatus = Literal["overdue", "today", "soon", "later"]
CardExpiry = Literal["expired", "soon", "ok"]


def due_status(loan: Loan, today: date, soon_days: int) -> DueStatus:
    """overdue < 0 days left, today == 0, soon 1..soon_days, later beyond."""
    left = loan.days_left(today)
    if left < 0:
        return "overdue"
    if left == 0:
        return "today"
    if left <= soon_days:
        return "soon"
    return "later"


def card_expiry(until: date | None, today: date) -> CardExpiry | None:
    """None when the page shows no expiry; expired before today; soon within
    CARD_EXPIRY_WARN_DAYS; ok otherwise."""
    if until is None:
        return None
    left = (until - today).days
    if left < 0:
        return "expired"
    if left <= CARD_EXPIRY_WARN_DAYS:
        return "soon"
    return "ok"
