"""Binary sensors: something overdue, something renewable."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CARD_EXPIRY_WARN_DAYS
from .coordinator import FindusConfigEntry, FindusCoordinator
from .entity import FindusEntity, loan_items

PARALLEL_UPDATES = 0

WEEKDAY_KEYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True, kw_only=True)
class FindusBinarySensorEntityDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[FindusCoordinator], bool | None]
    attrs_fn: Callable[[FindusCoordinator], dict[str, Any]] | None = None


def _overdue(c: FindusCoordinator) -> list:
    today = c.today()
    return [l for l in c.data.loans if l.days_left(today) < 0]


def _renewable(c: FindusCoordinator) -> list:
    return [l for l in c.data.loans if l.renewable]


def _card_expires_soon(c: FindusCoordinator) -> bool | None:
    """Unknown (None) when the page shows no expiry banner."""
    until = c.data.card_valid_until
    return None if until is None else (until - c.today()).days <= CARD_EXPIRY_WARN_DAYS


BINARY_SENSORS: tuple[FindusBinarySensorEntityDescription, ...] = (
    FindusBinarySensorEntityDescription(
        key="has_overdue",
        translation_key="has_overdue",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda c: bool(_overdue(c)),
        attrs_fn=lambda c: {"items": loan_items(_overdue(c), c.today())},
    ),
    FindusBinarySensorEntityDescription(
        key="can_renew",
        translation_key="can_renew",
        is_on_fn=lambda c: bool(_renewable(c)),
        attrs_fn=lambda c: {"items": loan_items(_renewable(c), c.today())},
    ),
    FindusBinarySensorEntityDescription(
        key="card_expires_soon",
        translation_key="card_expires_soon",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=_card_expires_soon,
        attrs_fn=lambda c: {
            "valid_until": c.data.card_valid_until.isoformat() if c.data.card_valid_until else None,
            "warn_days": CARD_EXPIRY_WARN_DAYS,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FindusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [*(FindusBinarySensor(coordinator, d) for d in BINARY_SENSORS), FindusOpenNow(coordinator)]
    )


class FindusBinarySensor(FindusEntity, BinarySensorEntity):
    entity_description: FindusBinarySensorEntityDescription

    def __init__(
        self, coordinator: FindusCoordinator, description: FindusBinarySensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator) if fn else None


class FindusOpenNow(FindusEntity, BinarySensorEntity):
    """Open according to the regular weekly hours; holidays and closures are not known."""

    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(self, coordinator: FindusCoordinator) -> None:
        super().__init__(coordinator, "open_now")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _tick(_now: datetime) -> None:  # polling is far too rare to catch opening times
            self.async_write_ha_state()

        self.async_on_remove(async_track_time_change(self.hass, _tick, second=0))

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.hours is not None

    @property
    def is_on(self) -> bool | None:
        hours = self.coordinator.hours
        return hours.is_open(dt_util.now()) if hours else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        hours = self.coordinator.hours
        if hours is None:
            return None
        now = dt_util.now()
        closes = hours.closes_at(now)
        opens = hours.next_open(now)
        return {
            "hours": {
                name: [f"{a:%H:%M}-{b:%H:%M}" for a, b in hours.days[i].intervals]
                if i in hours.days
                else []
                for i, name in enumerate(WEEKDAY_KEYS)
            },
            "conditional_days": [n for i, n in enumerate(WEEKDAY_KEYS) if i in hours.days and hours.days[i].conditional],
            "closes_at": f"{closes:%H:%M}" if closes else None,
            "next_open": opens.isoformat() if opens else None,
            "note": hours.note,
        }
