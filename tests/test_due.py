"""The one definition of how urgent a loan is and how close a card is to expiry."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from custom_components.findus_opac.client import Loan
from custom_components.findus_opac.due import card_expiry, due_status

TODAY = date(2026, 11, 12)


def loan_in(days: int) -> Loan:
    return Loan(
        mednr="1",
        title="Titel",
        author="",
        media_type="Buch",
        due=TODAY + timedelta(days=days),
        renewable=False,
    )


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (-2, "overdue"),
        (-1, "overdue"),
        (0, "today"),
        (1, "soon"),
        (3, "soon"),  # N
        (4, "later"),  # N + 1
    ],
)
def test_due_status(days: int, expected: str):
    assert due_status(loan_in(days), TODAY, 3) == expected


@pytest.mark.parametrize(
    ("until", "expected"),
    [
        (None, None),
        (TODAY - timedelta(days=1), "expired"),
        (TODAY, "soon"),
        (TODAY + timedelta(days=30), "soon"),
        (TODAY + timedelta(days=31), "ok"),
    ],
)
def test_card_expiry(until: date | None, expected: str | None):
    assert card_expiry(until, TODAY) == expected
