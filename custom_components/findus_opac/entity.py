"""Shared entity base and helpers."""
from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import Loan
from .const import CONF_ACCOUNT_NAME, CONF_SUBDOMAIN, DOMAIN
from .coordinator import FindusCoordinator
from .due import due_status


def loan_dict(loan: Loan, today: date, soon_days: int) -> dict[str, Any]:
    """Serialize a loan for state attributes."""
    return {
        "mednr": loan.mednr,
        "title": loan.title,
        "author": loan.author,
        "media_type": loan.media_type,
        "category": loan.category,
        "due": loan.due.isoformat(),
        "days_left": loan.days_left(today),
        "status": due_status(loan, today, soon_days),
        "renewable": loan.renewable,
        "renew_requested": loan.renew_requested,
        "renew_requested_on": loan.renew_requested_on.isoformat() if loan.renew_requested_on else None,
        "note": loan.note,
        "renew_block": loan.renew_block,
        "cover": loan.cover_url,
        "series": loan.series,
    }


def loan_items(loans: list[Loan], today: date, soon_days: int) -> list[dict[str, Any]]:
    """Loans as attribute dicts, soonest due first."""
    return [loan_dict(l, today, soon_days) for l in sorted(loans, key=lambda l: (l.due, l.title))]


class FindusEntity(CoordinatorEntity[FindusCoordinator]):
    """Base entity: one device per library account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FindusCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        sub = entry.data[CONF_SUBDOMAIN]
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_ACCOUNT_NAME) or entry.title,
            manufacturer="Findus Internet-OPAC",
            model=sub,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://{sub}.findus-internet-opac.de/leserkonto",
        )
