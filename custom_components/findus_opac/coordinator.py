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

from .client import Account, AuthError, FindusClient, FindusError, RenewOutcome
from .const import (
    CONF_ACCOUNT_NAME,
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
        entry.async_on_unload(self._cancel_recheck)

    @property
    def due_soon_days(self) -> int:
        return self.entry.options.get(CONF_DUE_SOON_DAYS, DEFAULT_DUE_SOON_DAYS)

    def today(self) -> date:
        return dt_util.now().date()

    async def _async_update_data(self) -> Account:
        try:
            return await self.client.fetch()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (FindusError, aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def _cancel_recheck(self) -> None:
        if self._recheck:
            self._recheck()
            self._recheck = None

    async def async_renew(self, mednrs: list[str] | None = None) -> list[RenewOutcome]:
        try:
            account, outcomes = await self.client.renew(mednrs)
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
        self.async_set_updated_data(account)
        self.hass.bus.async_fire(
            EVENT_RENEWAL,
            {
                "config_entry_id": self.entry.entry_id,
                "account_name": self.account_name,
                "items": [outcome_dict(o) for o in outcomes],
            },
        )
        if any(o.status == "requested" for o in outcomes):
            self._cancel_recheck()

            async def _recheck(_now: Any) -> None:
                self._recheck = None
                await self.async_request_refresh()

            self._recheck = async_call_later(self.hass, RENEW_RECHECK_MINUTES * 60, _recheck)
        return outcomes
