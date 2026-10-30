"""Buttons: renew all renewable items, sync the account now."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FindusConfigEntry
from .entity import FindusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: FindusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([RenewAllButton(coordinator, "renew_all"), SyncButton(coordinator, "sync")])


class RenewAllButton(FindusEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.coordinator.async_renew()


class SyncButton(FindusEntity, ButtonEntity):
    """Re-read the account now. Findus itself only has what the library last uploaded."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
