"""Which loans and card notices today's digest contains.

The notifier only schedules, sends and stores; the decisions that used to be buried in
its async_run live here, pure and testable without Home Assistant.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .client import Account, Loan, OpeningHours
from .const import CARD_REMINDER_DAYS, NOTIFY_KEEP_DAYS
from .due import due_status

# Stored next to the dedup keys: the day of the last digest run (for catch-up after restarts).
LAST_RUN_KEY = "_last_run"


@dataclass
class Digest:
    loans_by_kind: dict[str, list[Loan]]  # overdue, due_today, last_chance, due_soon
    card_until: date | None  # set when a card-expiry reminder is due
    new_keys: list[str]
    sent: dict[str, str]  # what to store: pruned, LAST_RUN_KEY = today, new_keys stamped today

    @property
    def has_news(self) -> bool:
        return bool(self.new_keys)

    @property
    def renewable(self) -> bool:
        return any(l.renewable for group in self.loans_by_kind.values() for l in group)


def is_last_chance(loan: Loan, now: datetime, hours: OpeningHours | None) -> bool:
    """Today is the last regular opening before a closed due date, and it has to come back."""
    today = now.date()
    if hours is None or loan.renewable or loan.renew_requested or loan.due <= today:
        return False
    last = hours.last_open_before(loan.due)
    return last is not None and last[0] == today and now.time() < last[1]


def select_digest(
    account: Account,
    sent: Mapping[str, str],
    now: datetime,
    hours: OpeningHours | None,
    events: Collection[str],
    due_soon_days: int,
) -> Digest:
    """What today's digest says, given what earlier digests already said."""
    today = now.date()
    cutoff = (today - timedelta(days=NOTIFY_KEEP_DAYS)).isoformat()
    stored = {k: v for k, v in sent.items() if v >= cutoff}
    stored[LAST_RUN_KEY] = today.isoformat()

    kinds: dict[str, list[Loan]] = {"overdue": [], "due_today": [], "last_chance": [], "due_soon": []}
    new_keys: list[str] = []
    for loan in account.loans:
        status = due_status(loan, today, due_soon_days)
        if status == "overdue":
            kind, key = "overdue", f"overdue:{loan.mednr}:{loan.due}:{today}"
        elif status == "today":
            kind, key = "due_today", f"due_today:{loan.mednr}:{loan.due}"
        elif status == "soon":
            kind, key = "due_soon", f"due_soon:{loan.mednr}:{loan.due}"
        else:
            kind, key = "", ""
        if kind in events and key not in stored:
            kinds[kind].append(loan)
            new_keys.append(key)
        if "last_chance" in events and is_last_chance(loan, now, hours):
            key = f"last_chance:{loan.mednr}:{loan.due}"
            if key not in stored:
                new_keys.append(key)
                # Already listed as due soon: that line names the last opening too.
                if loan not in kinds["due_soon"]:
                    kinds["last_chance"].append(loan)

    card_until = None
    until = account.card_valid_until
    if "card_expiry" in events and until is not None:
        left = (until - today).days
        due_keys = [f"card{n}:{until}" for n in CARD_REMINDER_DAYS if left <= n]
        if any(k not in stored for k in due_keys):
            card_until = until
            new_keys.extend(k for k in due_keys if k not in stored)

    for key in new_keys:
        stored[key] = today.isoformat()
    return Digest(loans_by_kind=kinds, card_until=card_until, new_keys=new_keys, sent=stored)
