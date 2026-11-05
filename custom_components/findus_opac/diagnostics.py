"""Diagnostics without credentials, names or loan titles."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_ACCOUNT_NAME, CONF_CARD, CONF_NOTIFY_TARGETS, CONF_SECRET
from .coordinator import FindusConfigEntry

# Credentials, plus names: account names and notify targets often identify a person.
TO_REDACT = {CONF_ACCOUNT_NAME, CONF_CARD, CONF_NOTIFY_TARGETS, CONF_SECRET}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FindusConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    account = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "last_update_success": coordinator.last_update_success,
        # No titles: they reveal what someone reads, and this file gets posted to issues.
        "loans": [
            {
                "mednr": l.mednr,
                "media_type": l.media_type,
                "category": l.category,
                "due": l.due.isoformat(),
                "renewable": l.renewable,
                "note": l.note,
            }
            for l in (account.loans if account else [])
        ],
        # The renewal form echoes card number and birth date: keys only.
        "form_keys": sorted(account.form) if account else [],
    }
