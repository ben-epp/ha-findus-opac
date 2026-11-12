"""Which loans and card notices a digest contains, independent of Home Assistant."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from custom_components.findus_opac.client import Account, DayHours, Loan, OpeningHours
from custom_components.findus_opac.digest import LAST_RUN_KEY, is_last_chance, select_digest

TODAY = date(2026, 11, 12)  # Thursday
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
ALL_EVENTS = frozenset({"overdue", "due_today", "due_soon", "last_chance", "card_expiry"})

# Mondays 09:00-17:00: Tuesday 17 Nov is closed, so Monday 16 is the last chance.
MONDAYS = OpeningHours(days={0: DayHours(intervals=((time(9), time(17)),))})
MONDAY_NOON = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
MONDAY_EVENING = datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc)


def _loan(
    mednr: str, due: date, *, renewable: bool = False, requested: bool = False
) -> Loan:
    return Loan(
        mednr=mednr,
        title=f"Titel {mednr}",
        author="",
        media_type="Buch",
        due=due,
        renewable=renewable,
        renew_requested=requested,
    )


def test_first_run_lists_each_kind_with_exact_keys():
    overdue = _loan("1", TODAY - timedelta(days=2))
    due_today = _loan("2", TODAY, renewable=True)
    due_soon = _loan("3", TODAY + timedelta(days=2))

    d = select_digest(Account(loans=[overdue, due_today, due_soon]), {}, NOW, None, ALL_EVENTS, 3)

    assert d.loans_by_kind == {
        "overdue": [overdue],
        "due_today": [due_today],
        "last_chance": [],
        "due_soon": [due_soon],
    }
    assert d.new_keys == [
        "overdue:1:2026-11-10:2026-11-12",
        "due_today:2:2026-11-12",
        "due_soon:3:2026-11-14",
    ]
    assert d.card_until is None
    assert d.has_news is True
    assert d.renewable is True
    assert d.sent == {
        LAST_RUN_KEY: "2026-11-12",
        "overdue:1:2026-11-10:2026-11-12": "2026-11-12",
        "due_today:2:2026-11-12": "2026-11-12",
        "due_soon:3:2026-11-14": "2026-11-12",
    }


def test_second_day_only_overdue_repeats():
    overdue = _loan("1", TODAY - timedelta(days=2))
    due_soon = _loan("3", TODAY + timedelta(days=2))
    account = Account(loans=[overdue, due_soon])
    day1 = select_digest(account, {}, NOW, None, ALL_EVENTS, 3)

    day2 = select_digest(
        account,
        day1.sent,
        datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc),
        None,
        ALL_EVENTS,
        3,
    )

    # The overdue key carries the run date, so it is the only one that is new again.
    assert day2.new_keys == ["overdue:1:2026-11-10:2026-11-13"]
    assert day2.loans_by_kind["overdue"] == [overdue]
    assert day2.loans_by_kind["due_soon"] == []
    assert day2.sent["overdue:1:2026-11-10:2026-11-12"] == "2026-11-12"
    assert day2.sent["due_soon:3:2026-11-14"] == "2026-11-12"


def test_events_filter_drops_kinds_and_their_keys():
    overdue = _loan("1", TODAY - timedelta(days=2))
    due_today = _loan("2", TODAY, renewable=True)
    due_soon = _loan("3", TODAY + timedelta(days=2))

    d = select_digest(
        Account(loans=[overdue, due_today, due_soon]),
        {},
        NOW,
        None,
        frozenset({"due_today"}),
        3,
    )

    assert d.loans_by_kind["overdue"] == []
    assert d.loans_by_kind["due_today"] == [due_today]
    assert d.loans_by_kind["due_soon"] == []
    assert d.new_keys == ["due_today:2:2026-11-12"]
    assert "overdue:1:2026-11-10:2026-11-12" not in d.sent
    assert "due_soon:3:2026-11-14" not in d.sent


def test_last_chance_before_and_after_closing_time():
    due = date(2026, 11, 17)  # Tuesday, library closed
    loan = _loan("1", due)
    assert is_last_chance(loan, MONDAY_NOON, MONDAYS)

    d = select_digest(
        Account(loans=[loan]), {}, MONDAY_NOON, MONDAYS, frozenset({"last_chance"}), 0
    )
    assert d.loans_by_kind["last_chance"] == [loan]
    assert d.new_keys == ["last_chance:1:2026-11-17"]
    assert d.sent["last_chance:1:2026-11-17"] == "2026-11-16"

    assert not is_last_chance(loan, MONDAY_EVENING, MONDAYS)
    d = select_digest(
        Account(loans=[loan]),
        {},
        MONDAY_EVENING,
        MONDAYS,
        frozenset({"last_chance"}),
        0,
    )
    assert d.loans_by_kind["last_chance"] == []
    assert "last_chance:1:2026-11-17" not in d.sent


def test_no_last_chance_when_renewable_requested_or_disabled():
    due = date(2026, 11, 17)
    renewable = _loan("1", due, renewable=True)
    requested = _loan("2", due, requested=True)
    plain = _loan("3", due)

    assert not is_last_chance(renewable, MONDAY_NOON, MONDAYS)
    assert not is_last_chance(requested, MONDAY_NOON, MONDAYS)
    assert not is_last_chance(plain, MONDAY_NOON, None)

    d = select_digest(
        Account(loans=[plain]), {}, MONDAY_NOON, MONDAYS, frozenset({"overdue"}), 0
    )
    assert d.loans_by_kind["last_chance"] == []
    assert "last_chance:3:2026-11-17" not in d.sent


def test_last_chance_already_due_soon_is_listed_once_but_stored():
    due = date(2026, 11, 18)  # Wednesday; Monday 16 is the last regular opening
    loan = _loan("1", due)

    d = select_digest(
        Account(loans=[loan]),
        {},
        MONDAY_NOON,
        MONDAYS,
        frozenset({"due_soon", "last_chance"}),
        3,
    )

    assert d.loans_by_kind["due_soon"] == [loan]
    assert d.loans_by_kind["last_chance"] == []
    assert d.new_keys == ["due_soon:1:2026-11-18", "last_chance:1:2026-11-18"]
    assert d.sent["last_chance:1:2026-11-18"] == "2026-11-16"


def test_card_expiry_reminders():
    card_events = frozenset({"card_expiry"})

    # 31 days left: too early for a reminder.
    d = select_digest(Account(card_valid_until=TODAY + timedelta(days=31)), {}, NOW, None, card_events, 3)
    assert d.card_until is None
    assert d.new_keys == []

    # 30 days: the first reminder.
    until = TODAY + timedelta(days=30)
    account = Account(card_valid_until=until)
    d = select_digest(account, {}, NOW, None, card_events, 3)
    assert d.card_until == until
    assert d.new_keys == ["card30:2026-12-12"]

    # Seven days later only the second reminder is new.
    later = datetime(2026, 12, 5, 9, 0, tzinfo=timezone.utc)
    d = select_digest(account, d.sent, later, None, card_events, 3)
    assert d.card_until == until
    assert d.new_keys == ["card7:2026-12-12"]

    # Both already sent: nothing to say.
    d = select_digest(account, d.sent, later, None, card_events, 3)
    assert d.card_until is None
    assert d.new_keys == []


def test_pruning_and_last_run():
    boundary = (TODAY - timedelta(days=60)).isoformat()
    d = select_digest(
        Account(),
        {
            "old": (TODAY - timedelta(days=61)).isoformat(),
            "boundary": boundary,
            LAST_RUN_KEY: (TODAY - timedelta(days=1)).isoformat(),
        },
        NOW,
        None,
        frozenset(),
        3,
    )

    assert "old" not in d.sent
    assert d.sent["boundary"] == boundary
    assert d.sent[LAST_RUN_KEY] == "2026-11-12"
    assert d.new_keys == []
    assert d.has_news is False


def test_input_sent_is_not_mutated():
    sent = {
        "old": (TODAY - timedelta(days=61)).isoformat(),
        LAST_RUN_KEY: (TODAY - timedelta(days=1)).isoformat(),
    }
    before = dict(sent)

    select_digest(Account(loans=[_loan("1", TODAY - timedelta(days=1))]), sent, NOW, None, ALL_EVENTS, 3)

    assert sent == before


def test_nothing_new_still_stores_last_run():
    d = select_digest(Account(), {}, NOW, None, ALL_EVENTS, 3)

    assert d.has_news is False
    assert d.new_keys == []
    assert d.sent == {LAST_RUN_KEY: "2026-11-12"}
