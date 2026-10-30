"""Renew button."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FindusConfigEntry
from .entity import FindusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: FindusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([RenewAllButton(entry.runtime_data, "renew_all")])


class RenewAllButton(FindusEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.coordinator.async_renew()
