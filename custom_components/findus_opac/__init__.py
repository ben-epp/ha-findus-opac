"""Findus Internet-OPAC: library loans and renewals."""
from __future__ import annotations

import logging
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
    CONF_NOTIFY_TARGETS,
    DOMAIN,
    SERVICE_RENEW,
)
from .coordinator import FindusConfigEntry, FindusCoordinator, outcome_dict
from .notifications import FindusNotifier, notified_store
from .renewal_requests import requests_store

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.CALENDAR]
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
    url = f"{CARD_URL}?v={CARD_VERSION}"
    add_extra_js_url(hass, url)
    # The companion apps do not reliably load extra_module_url; dashboard resources they do.
    # Same URL as above, so browsers that get both load the module only once.
    try:
        await _async_ensure_lovelace_resource(hass, url)
    except Exception:  # noqa: BLE001 - never fail setup over a dashboard resource
        _LOGGER.warning("Could not register the Findus card as dashboard resource", exc_info=True)


async def _async_ensure_lovelace_resource(hass: HomeAssistant, url: str) -> None:
    """Create or update the card's module resource (storage-mode dashboards only)."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    data = hass.data.get(LOVELACE_DATA)
    mode = getattr(data, "resource_mode", None) or getattr(data, "mode", None)
    if data is None or mode != "storage":
        return  # YAML resources are managed by the user
    resources = data.resources
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    base = url.split("?", 1)[0]
    for item in resources.async_items():
        if item.get("url", "").split("?", 1)[0] == base:
            if item["url"] != url:
                await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
            return
    await resources.async_create_item({"res_type": "module", "url": url})


async def async_setup_entry(hass: HomeAssistant, entry: FindusConfigEntry) -> bool:
    coordinator = FindusCoordinator(hass, entry)
    await coordinator.requests.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if entry.options.get(CONF_NOTIFY_TARGETS):
        entry.async_on_unload(FindusNotifier(hass, coordinator).async_start())
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: FindusConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FindusConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: FindusConfigEntry) -> None:
    """Delete what the entry stored besides its config: pending requests, sent reminders."""
    await requests_store(hass, entry.entry_id).async_remove()
    await notified_store(hass, entry.entry_id).async_remove()
