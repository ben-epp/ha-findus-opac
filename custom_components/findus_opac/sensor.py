"""Sensors: loan counts, due dates and renewal state."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import Loan
from .const import CATEGORIES
from .coordinator import FindusConfigEntry, FindusCoordinator
from .entity import FindusEntity, loan_items

PARALLEL_UPDATES = 0

LoanFilter = Callable[[FindusCoordinator, Loan], bool]


@dataclass(frozen=True, kw_only=True)
class FindusSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[FindusCoordinator], Any]
    attrs_fn: Callable[[FindusCoordinator], dict[str, Any]] | None = None


def _select(c: FindusCoordinator, pred: LoanFilter) -> list[Loan]:
    return [l for l in c.data.loans if pred(c, l)]


def _count(pred: LoanFilter) -> Callable[[FindusCoordinator], int]:
    return lambda c: len(_select(c, pred))


def _items(pred: LoanFilter) -> Callable[[FindusCoordinator], dict[str, Any]]:
    return lambda c: {"items": loan_items(_select(c, pred), c.today())}


def _next_due(c: FindusCoordinator) -> date | None:
    return min((l.due for l in c.data.loans), default=None)


def _days_left(c: FindusCoordinator) -> int | None:
    due = _next_due(c)
    return None if due is None else (due - c.today()).days


def _next_due_attrs(c: FindusCoordinator) -> dict[str, Any]:
    due = _next_due(c)
    return {"titles": sorted(l.title for l in c.data.loans if l.due == due)}


def _all(c: FindusCoordinator, l: Loan) -> bool:
    return True


def _in_category(category: str) -> LoanFilter:
    return lambda c, l: l.category == category


def _due_today(c: FindusCoordinator, l: Loan) -> bool:
    return l.days_left(c.today()) == 0


def _due_soon(c: FindusCoordinator, l: Loan) -> bool:
    return 0 <= l.days_left(c.today()) <= c.due_soon_days


def _overdue(c: FindusCoordinator, l: Loan) -> bool:
    return l.days_left(c.today()) < 0


def _renewable(c: FindusCoordinator, l: Loan) -> bool:
    return l.renewable


def _counter(key: str, pred: LoanFilter, **kwargs: Any) -> FindusSensorEntityDescription:
    return FindusSensorEntityDescription(
        key=key,
        translation_key=key,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count(pred),
        attrs_fn=_items(pred),
        **kwargs,
    )


SENSORS: tuple[FindusSensorEntityDescription, ...] = (
    _counter("loans", _all),
    *(
        _counter(
            cat,
            _in_category(cat),
            entity_registry_enabled_default=cat not in ("video", "game"),
        )
        for cat in CATEGORIES
    ),
    FindusSensorEntityDescription(
        key="next_due",
        translation_key="next_due",
        device_class=SensorDeviceClass.DATE,
        value_fn=_next_due,
        attrs_fn=_next_due_attrs,
    ),
    FindusSensorEntityDescription(
        key="days_left",
        translation_key="days_left",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=_days_left,
    ),
    FindusSensorEntityDescription(
        key="due_today",
        translation_key="due_today",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count(_due_today),
    ),
    _counter("due_soon", _due_soon),
    _counter("overdue", _overdue),
    _counter("renewable", _renewable),
    FindusSensorEntityDescription(
        key="card_valid_until",
        translation_key="card_valid_until",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda c: c.data.card_valid_until,
        attrs_fn=lambda c: {
            "days_left": (c.data.card_valid_until - c.today()).days
            if c.data.card_valid_until
            else None
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FindusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(FindusSensor(coordinator, d) for d in SENSORS)


class FindusSensor(FindusEntity, SensorEntity):
    entity_description: FindusSensorEntityDescription

    def __init__(
        self, coordinator: FindusCoordinator, description: FindusSensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator) if fn else None
