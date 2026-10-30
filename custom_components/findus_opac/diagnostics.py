"""Diagnostics with credentials redacted."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_CARD, CONF_SECRET
from .coordinator import FindusConfigEntry

TO_REDACT = {CONF_CARD, CONF_SECRET}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FindusConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    account = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "loans": [
            {
                "mednr": l.mednr,
                "title": l.title,
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
