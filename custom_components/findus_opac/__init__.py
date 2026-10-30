"""Findus Internet-OPAC: library loans and renewals."""
from __future__ import annotations

from pathlib import Path

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

from .const import (
    ATTR_CATEGORIES,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_MEDIA_IDS,
    CARD_FILE,
    CARD_URL,
    CARD_VERSION,
    CATEGORIES,
    DOMAIN,
    SERVICE_RENEW,
)
from .coordinator import FindusConfigEntry, FindusCoordinator, outcome_dict

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

RENEW_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_MEDIA_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_CATEGORIES): vol.All(cv.ensure_list, [vol.In(CATEGORIES)]),
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
        outcomes = await coordinator.async_renew(
            call.data.get(ATTR_MEDIA_IDS) or None, call.data.get(ATTR_CATEGORIES) or None
        )
        return {"items": [outcome_dict(o) for o in outcomes]}

    hass.services.async_register(
        DOMAIN,
        SERVICE_RENEW,
        handle_renew,
        schema=RENEW_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    await _async_register_card(hass)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card and load it on every dashboard (no manual resource)."""
    if hass.http is None or "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "frontend" / CARD_FILE), False)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")


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
