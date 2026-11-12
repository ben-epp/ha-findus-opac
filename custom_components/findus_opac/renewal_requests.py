"""Renewal requests sent to the library, and the day's auto-renew attempts.

Pure besides the store: all decisions take plain dates and an `Account`, so the rules
can be tested without a Home Assistant setup and a frozen clock.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .client import Account, Loan, OpeningHours, RenewOutcome
from .const import (
    CONF_AUTO_RENEW,
    CONF_AUTO_RENEW_CATEGORIES,
    CONF_AUTO_RENEW_DAYS,
    DEFAULT_AUTO_RENEW_DAYS,
    DOMAIN,
)

# A renewal request is an email to the library; staff apply it by hand. Findus forgets the
# request at the library's next data upload and shows the item as renewable again, so the
# integration keeps its own record. It counts as pending for this many opening days after it
# was sent (calendar days if the hours are unknown); only then is one new request sent.
PENDING_OPEN_DAYS = 2
PENDING_FALLBACK_DAYS = 3


def requests_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, dict[str, str]]]:
    return Store(hass, 1, f"{DOMAIN}.requests.{entry_id}")


def pending_until(sent: date, hours: OpeningHours | None) -> date:
    """Last day a request sent on `sent` counts as pending: the library's second opening
    day after it, so staff had a full working day for it; 3 calendar days without hours."""
    fallback = sent + timedelta(days=PENDING_FALLBACK_DAYS)
    if hours is None:
        return fallback
    return hours.nth_open_day_after(sent, PENDING_OPEN_DAYS) or fallback


@dataclass(frozen=True)
class AutoRenewRule:
    enabled: bool
    days: int
    categories: frozenset[str]  # empty = all categories

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> AutoRenewRule:
        return cls(
            enabled=bool(options.get(CONF_AUTO_RENEW, False)),
            days=options.get(CONF_AUTO_RENEW_DAYS, DEFAULT_AUTO_RENEW_DAYS),
            categories=frozenset(options.get(CONF_AUTO_RENEW_CATEGORIES) or []),
        )


class RenewalRequests:
    """The integration's own record of renewal requests sent to the library, and of today's
    auto-renew attempts. Findus forgets a request at the library's next data upload; this
    record does not, until the due date moves or the item is returned."""

    def __init__(self, store: Store[dict[str, dict[str, str]]]) -> None:
        self._store = store
        # mednr -> {"due": ISO date, "sent": ISO date} of renewal requests still pending.
        self._requests: dict[str, dict[str, str]] = {}
        self._dirty = False
        # mednr -> (due date, day) of the last auto-renew. A pending request is not renewable,
        # so it is never resent; one the library dropped (renewable again, same due date)
        # is retried the next day instead of never. RAM only: a restart allows one more try.
        self._attempted: dict[str, tuple[date, date]] = {}

    async def async_load(self) -> None:
        self._requests = dict(await self._store.async_load() or {})

    def mark(self, account: Account, today: date, hours: OpeningHours | None) -> Account:
        """Mark items with a pending request, which Findus itself soon stops showing."""
        loans = {l.mednr: l for l in account.loans}
        changed = False
        for mednr, req in list(self._requests.items()):
            loan = loans.get(mednr)
            if loan is None or loan.due.isoformat() != req["due"]:  # renewed or returned
                del self._requests[mednr]
                changed = True
        marked: list[Loan] = []
        for loan in account.loans:
            req = self._requests.get(loan.mednr)
            if req is None and loan.renew_requested:  # e.g. requested on the website
                req = self._requests[loan.mednr] = {
                    "due": loan.due.isoformat(), "sent": today.isoformat()
                }
                changed = True
            # A reason not to renew from the library (e.g. reserved) wins over our record.
            if req is None or not (loan.renewable or loan.renew_requested):
                marked.append(loan)
                continue
            sent = date.fromisoformat(req["sent"])
            if today <= pending_until(sent, hours):
                loan = replace(
                    loan, renewable=False, renew_requested=True, renew_requested_on=sent
                )
            marked.append(loan)
        self._dirty |= changed
        return replace(account, loans=marked)

    def auto_targets(self, marked: Account, today: date, rule: AutoRenewRule) -> list[str]:
        """Renewable loans inside the auto-renew window not tried today for this due date.

        `marked` must come from mark(): pending requests are not renewable.
        """
        if not rule.enabled:
            return []
        targets = []
        for loan in marked.loans:
            if (
                loan.renewable
                and loan.days_left(today) <= rule.days
                and (not rule.categories or loan.category in rule.categories)
                and self._attempted.get(loan.mednr) != (loan.due, today)
            ):
                self._attempted[loan.mednr] = (loan.due, today)
                targets.append(loan.mednr)
        return targets

    def record(self, outcomes: list[RenewOutcome], today: date) -> None:
        for o in outcomes:
            if o.status == "requested":
                self._requests[o.mednr] = {"due": o.old_due.isoformat(), "sent": today.isoformat()}
                self._dirty = True

    async def async_save(self) -> None:
        """Written right away: a delayed save would be lost when the entry reloads."""
        if self._dirty:
            self._dirty = False
            await self._store.async_save(self._requests)
