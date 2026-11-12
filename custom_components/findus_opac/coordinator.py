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
    CONF_RENEW_EMAIL,
    CONF_CARD,
    CONF_DUE_SOON_DAYS,
    CONF_SCAN_HOURS,
    CONF_SECRET,
    CONF_SUBDOMAIN,
    DEFAULT_DUE_SOON_DAYS,
    DEFAULT_SCAN_HOURS,
    DOMAIN,
    EVENT_RENEWAL,
    RENEW_RECHECK_MINUTES,
)
from .renewal_requests import AutoRenewRule, RenewalRequests, requests_store

_LOGGER = logging.getLogger(__name__)

type FindusConfigEntry = ConfigEntry[FindusCoordinator]


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
        self.requests = RenewalRequests(requests_store(hass, entry.entry_id))
        self.auto_renew = AutoRenewRule.from_options(entry.options)
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

    async def _async_update_data(self) -> Account:
        try:
            account = await self.client.fetch()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (FindusError, aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(str(err)) from err
        # Hours first: the pending window needs them.
        await self._async_update_hours()
        account = self.requests.mark(account, self.today(), self.hours)
        account = await self._async_auto_renew(account)
        await self.requests.async_save()
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

    async def _async_auto_renew(self, account: Account) -> Account:
        today = self.today()
        targets = self.requests.auto_targets(account, today, self.auto_renew)
        if not targets:
            return account
        try:
            renewed, outcomes = await self.client.renew(targets, reply_to=self.renew_email)
        except (FindusError, aiohttp.ClientError, TimeoutError) as err:
            # Never fail the poll because of auto-renew; retried tomorrow.
            _LOGGER.warning("Auto-renew for entry %s failed: %s", self.entry.entry_id, err)
            return account
        self.requests.record(outcomes, today)
        self._after_renew(outcomes, "auto")
        return self.requests.mark(renewed, today, self.hours)

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
        self.requests.record(outcomes, self.today())
        account = self.requests.mark(account, self.today(), self.hours)
        await self.requests.async_save()
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
