"""Findus Internet-OPAC: library loans and renewals."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_CONFIG_ENTRY_ID, ATTR_MEDIA_IDS, DOMAIN, SERVICE_RENEW
from .coordinator import FindusConfigEntry, FindusCoordinator, outcome_dict

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

RENEW_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_MEDIA_IDS): vol.All(cv.ensure_list, [cv.string]),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def handle_renew(call: ServiceCall) -> ServiceResponse:
        entry = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"config_entry_id": call.data[ATTR_CONFIG_ENTRY_ID]},
            )
        coordinator: FindusCoordinator = entry.runtime_data
        outcomes = await coordinator.async_renew(call.data.get(ATTR_MEDIA_IDS) or None)
        return {"items": [outcome_dict(o) for o in outcomes]}

    hass.services.async_register(
        DOMAIN,
        SERVICE_RENEW,
        handle_renew,
        schema=RENEW_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FindusConfigEntry) -> bool:
    coordinator = FindusCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: FindusConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FindusConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
