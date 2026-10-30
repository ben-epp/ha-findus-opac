"""Config, reauth and options flows for Findus Internet-OPAC."""
from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import AuthError, FindusError
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
    MAX_SCAN_HOURS,
    MIN_SCAN_HOURS,
)
from .coordinator import make_client

_LOGGER = logging.getLogger(__name__)

HOST_SUFFIX = ".findus-internet-opac.de"
SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def normalize_subdomain(value: str) -> str | None:
    """Accept `alzey` or any Findus URL; return the subdomain or None."""
    value = value.strip().lower()
    if "/" in value or value.endswith(HOST_SUFFIX):
        host = urlparse(value if "://" in value else f"https://{value}").hostname or ""
        if not host.endswith(HOST_SUFFIX):
            return None
        value = host.removesuffix(HOST_SUFFIX)
    if value in ("", "www") or not SUBDOMAIN_RE.match(value):
        return None
    return value


class FindusConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, data: Mapping[str, Any]) -> str | None:
        """Try a login; return an error key or None."""
        try:
            await make_client(self.hass, data).fetch()
        except AuthError:
            return "invalid_auth"
        except (FindusError, aiohttp.ClientError, TimeoutError):
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating Findus login")
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            subdomain = normalize_subdomain(user_input[CONF_SUBDOMAIN])
            if subdomain is None:
                errors[CONF_SUBDOMAIN] = "invalid_subdomain"
            else:
                data = {
                    CONF_ACCOUNT_NAME: user_input[CONF_ACCOUNT_NAME].strip(),
                    CONF_SUBDOMAIN: subdomain,
                    CONF_CARD: user_input[CONF_CARD].strip(),
                    CONF_SECRET: user_input[CONF_SECRET].strip(),
                }
                await self.async_set_unique_id(f"{subdomain}_{data[CONF_CARD]}")
                self._abort_if_unique_id_configured()
                if (error := await self._validate(data)) is None:
                    return self.async_create_entry(title=data[CONF_ACCOUNT_NAME], data=data)
                errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT_NAME): str,
                vol.Required(CONF_SUBDOMAIN): str,
                vol.Required(CONF_CARD): str,
                vol.Required(CONF_SECRET): PASSWORD,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            secret = user_input[CONF_SECRET].strip()
            if (error := await self._validate({**entry.data, CONF_SECRET: secret})) is None:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_SECRET: secret})
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_SECRET): PASSWORD}),
            description_placeholders={"account_name": entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FindusOptionsFlow:
        return FindusOptionsFlow()


class FindusOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_HOURS: int(user_input[CONF_SCAN_HOURS]),
                    CONF_DUE_SOON_DAYS: int(user_input[CONF_DUE_SOON_DAYS]),
                }
            )
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_HOURS, default=opts.get(CONF_SCAN_HOURS, DEFAULT_SCAN_HOURS)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_HOURS, max=MAX_SCAN_HOURS, step=1,
                        mode=NumberSelectorMode.BOX, unit_of_measurement="h",
                    )
                ),
                vol.Required(
                    CONF_DUE_SOON_DAYS, default=opts.get(CONF_DUE_SOON_DAYS, DEFAULT_DUE_SOON_DAYS)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=14, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="d"
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
