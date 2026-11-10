"""Data update coordinator for Findus Internet-OPAC."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import date, timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import (
    Account,
    AuthError,
    FindusClient,
    FindusError,
    OpeningHours,
    RenewOutcome,
)
from .const import (
    CONF_ACCOUNT_NAME,
    CONF_AUTO_RENEW,
    CONF_AUTO_RENEW_CATEGORIES,
    CONF_AUTO_RENEW_DAYS,
    CONF_RENEW_EMAIL,
    CONF_CARD,
    CONF_DUE_SOON_DAYS,
    CONF_SCAN_HOURS,
    CONF_SECRET,
    CONF_SUBDOMAIN,
    DEFAULT_AUTO_RENEW_DAYS,
    DEFAULT_DUE_SOON_DAYS,
    DEFAULT_SCAN_HOURS,
    DOMAIN,
    EVENT_RENEWAL,
    RENEW_RECHECK_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

type FindusConfigEntry = ConfigEntry[FindusCoordinator]

# A renewal request is an email to the library; staff apply it by hand. Findus forgets the
# request at the library's next data upload and shows the item as renewable again, so the
# integration keeps its own record. It counts as pending for this many opening days after it
# was sent (calendar days if the hours are unknown); only then is one new request sent.
PENDING_OPEN_DAYS = 2
PENDING_FALLBACK_DAYS = 3


def requests_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, dict[str, str]]]:
    return Store(hass, 1, f"{DOMAIN}.requests.{entry_id}")


def make_client(hass: HomeAssistant, data: Mapping[str, Any]) -> FindusClient:
    session = async_get_clientsession(hass)
    timeout = aiohttp.ClientTimeout(total=30)

    async def get(url: str) -> str:
        async with session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def post(url: str, form: dict[str, str]) -> str:
        async with session.post(url, data=form, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.text()

    return FindusClient(data[CONF_SUBDOMAIN], data[CONF_CARD], data[CONF_SECRET], get, post)


def outcome_dict(o: RenewOutcome) -> dict[str, Any]:
    d = asdict(o)
    d["old_due"] = o.old_due.isoformat()
    d["new_due"] = o.new_due.isoformat() if o.new_due else None
    return d


class FindusCoordinator(DataUpdateCoordinator[Account]):
    config_entry: FindusConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FindusConfigEntry) -> None:
        self.entry = entry
        self.account_name: str = entry.data.get(CONF_ACCOUNT_NAME) or entry.title
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.account_name}",
            update_interval=timedelta(
                hours=entry.options.get(CONF_SCAN_HOURS, DEFAULT_SCAN_HOURS)
            ),
        )
        self.client = make_client(hass, entry.data)
        self._recheck: Callable[[], None] | None = None
        # mednr -> (due date, day) of the last auto-renew. A pending request is not renewable,
        # so it is never resent; one the library dropped (renewable again, same due date)
        # is retried the next day instead of never.
        self._auto_attempted: dict[str, tuple[date, date]] = {}
        # mednr -> {"due": ISO date, "sent": ISO date} of renewal requests still pending.
        self._requests: dict[str, dict[str, str]] = {}
        self._requests_store = requests_store(hass, entry.entry_id)
        self._requests_dirty = False
        # Regular opening hours; they rarely change, so fetched once a day.
        self.hours: OpeningHours | None = None
        self._hours_day: date | None = None
        entry.async_on_unload(self._cancel_recheck)

    @property
    def due_soon_days(self) -> int:
        return self.entry.options.get(CONF_DUE_SOON_DAYS, DEFAULT_DUE_SOON_DAYS)

    @property
    def renew_email(self) -> str:
        return self.entry.options.get(CONF_RENEW_EMAIL, "")

    def today(self) -> date:
        return dt_util.now().date()

    async def async_load_requests(self) -> None:
        self._requests = dict(await self._requests_store.async_load() or {})

    def pending_until(self, sent: date) -> date:
        """Last day a request sent on `sent` counts as pending: the library's second opening
        day after it, so staff had a full working day for it."""
        if self.hours is not None:
            day, open_days = sent, 0
            for _ in range(14):
                day += timedelta(days=1)
                hours = self.hours.days.get(day.weekday())
                if hours and (hours.intervals or hours.conditional):
                    open_days += 1
                    if open_days == PENDING_OPEN_DAYS:
                        return day
        return sent + timedelta(days=PENDING_FALLBACK_DAYS)

    def _track_requests(self, account: Account) -> Account:
        """Mark items with a pending request, which Findus itself soon stops showing."""
        today = self.today()
        loans = {l.mednr: l for l in account.loans}
        changed = False
        for mednr, req in list(self._requests.items()):
            loan = loans.get(mednr)
            if loan is None or loan.due.isoformat() != req["due"]:  # renewed or returned
                del self._requests[mednr]
                changed = True
        for loan in account.loans:
            req = self._requests.get(loan.mednr)
            if req is None and loan.renew_requested:  # e.g. requested on the website
                req = self._requests[loan.mednr] = {
                    "due": loan.due.isoformat(), "sent": today.isoformat()
                }
                changed = True
            # A reason not to renew from the library (e.g. reserved) wins over our record.
            if req is None or not (loan.renewable or loan.renew_requested):
                continue
            sent = date.fromisoformat(req["sent"])
            if today <= self.pending_until(sent):
                loan.renewable = False
                loan.renew_requested = True
                loan.renew_requested_on = sent
        self._requests_dirty |= changed
        return account

    def _record_requests(self, outcomes: list[RenewOutcome]) -> None:
        today = self.today().isoformat()
        for o in outcomes:
            if o.status == "requested":
                self._requests[o.mednr] = {"due": o.old_due.isoformat(), "sent": today}
                self._requests_dirty = True

    async def _async_save_requests(self) -> None:
        """Written right away: a delayed save would be lost when the entry reloads."""
        if self._requests_dirty:
            self._requests_dirty = False
            await self._requests_store.async_save(self._requests)

    async def _async_update_data(self) -> Account:
        try:
            account = await self.client.fetch()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (FindusError, aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(str(err)) from err
        await self._async_update_hours()
        account = await self._async_auto_renew(self._track_requests(account))
        await self._async_save_requests()
        return account

    async def _async_update_hours(self) -> None:
        """Never fails the poll: the account matters more; retried on the next one."""
        if self._hours_day == self.today():
            return
        try:
            self.hours = await self.client.fetch_opening_hours()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Could not fetch opening hours: %s", err)
            return
        self._hours_day = self.today()

    def auto_renew_targets(self, account: Account) -> list[str]:
        """Renewable loans inside the auto-renew window not tried today for this due date.

        Expects an account passed through _track_requests: pending requests are not renewable.
        """
        opts = self.entry.options
        if not opts.get(CONF_AUTO_RENEW, False):
            return []
        days = opts.get(CONF_AUTO_RENEW_DAYS, DEFAULT_AUTO_RENEW_DAYS)
        categories = set(opts.get(CONF_AUTO_RENEW_CATEGORIES) or [])
        today = self.today()
        return [
            l.mednr
            for l in account.loans
            if l.renewable
            and l.days_left(today) <= days
            and (not categories or l.category in categories)
            and self._auto_attempted.get(l.mednr) != (l.due, today)
        ]

    async def _async_auto_renew(self, account: Account) -> Account:
        targets = self.auto_renew_targets(account)
        if not targets:
            return account
        today = self.today()
        for loan in account.loans:
            if loan.mednr in targets:
                self._auto_attempted[loan.mednr] = (loan.due, today)
        try:
            renewed, outcomes = await self.client.renew(targets, reply_to=self.renew_email)
        except (FindusError, aiohttp.ClientError, TimeoutError) as err:
            # Never fail the poll because of auto-renew; retried tomorrow.
            _LOGGER.warning("Auto-renew for entry %s failed: %s", self.entry.entry_id, err)
            return account
        self._record_requests(outcomes)
        self._after_renew(outcomes, "auto")
        return self._track_requests(renewed)

    @callback
    def _cancel_recheck(self) -> None:
        if self._recheck:
            self._recheck()
            self._recheck = None

    async def async_renew(
        self, mednrs: list[str] | None = None, categories: list[str] | None = None
    ) -> list[RenewOutcome]:
        """Renew items (default: all renewable), optionally restricted to media categories.

        Without explicit media ids, items with a pending request are left out so the library
        does not get the same request twice. Explicit ids are always sent.
        """
        if not mednrs:
            mednrs = [
                l.mednr
                for l in (self.data.loans if self.data else [])
                if l.renewable and (not categories or l.category in categories)
            ]
            if not mednrs:  # an empty list would mean "renew everything" to the client
                self._after_renew([], "manual")
                return []
        elif categories:
            loans = {l.mednr: l for l in (self.data.loans if self.data else [])}
            mednrs = [m for m in mednrs if m in loans and loans[m].category in categories]
            if not mednrs:
                self._after_renew([], "manual")
                return []
        try:
            account, outcomes = await self.client.renew(mednrs, reply_to=self.renew_email)
        except AuthError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="renew_auth_failed"
            ) from err
        except (FindusError, aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="renew_failed",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err
        self._record_requests(outcomes)
        account = self._track_requests(account)
        await self._async_save_requests()
        self.async_set_updated_data(account)
        self._after_renew(outcomes, "manual")
        if outcomes and all(o.status == "failed" for o in outcomes):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="renew_failed",
                translation_placeholders={"error": "request not accepted by the library"},
            )
        return outcomes

    @callback
    def _after_renew(self, outcomes: list[RenewOutcome], trigger: str) -> None:
        """Fire the renewal event and schedule a re-check for pending requests."""
        self.hass.bus.async_fire(
            EVENT_RENEWAL,
            {
                "config_entry_id": self.entry.entry_id,
                "account_name": self.account_name,
                "trigger": trigger,
                "items": [outcome_dict(o) for o in outcomes],
            },
        )
        if any(o.status == "requested" for o in outcomes):
            self._cancel_recheck()

            async def _recheck(_now: Any) -> None:
                self._recheck = None
                await self.async_request_refresh()

            self._recheck = async_call_later(self.hass, RENEW_RECHECK_MINUTES * 60, _recheck)
