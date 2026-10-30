"""Binary sensors: something overdue, something renewable."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CARD_EXPIRY_WARN_DAYS
from .coordinator import FindusConfigEntry, FindusCoordinator
from .entity import FindusEntity, loan_items

PARALLEL_UPDATES = 0


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
    async_add_entities(FindusBinarySensor(coordinator, d) for d in BINARY_SENSORS)


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
