"""Auto-renew on coordinator refresh."""
from __future__ import annotations

import logging

import aiohttp
import pytest
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.findus_opac.client import FindusClient

from custom_components.findus_opac.const import (
    CONF_AUTO_RENEW,
    CONF_AUTO_RENEW_CATEGORIES,
    CONF_AUTO_RENEW_DAYS,
    DOMAIN,
    EVENT_RENEWAL,
)

from .conftest import CARD, ENTRY_DATA

# Tonie 0900000101 due 2026-11-06 and CD 0900000102 due 2026-11-08 are the renewable items.
NOW = "2026-11-06 10:00:00+01:00"


def renew_posts(opac) -> list[list[str]]:
    return [
        sorted(k for k in p if k.startswith("verlaengere_nr_"))
        for p in opac.posts
        if any(k.startswith("verlaengere_nr_") for k in p)
    ]


@pytest.fixture
def make_entry(hass, freezer):
    async def _make(**options) -> MockConfigEntry:
        await hass.config.async_set_time_zone("Europe/Berlin")
        freezer.move_to(NOW)
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Kinder",
            data=dict(ENTRY_DATA),
            options=options,
            unique_id=f"musterstadt_{CARD}",
        )
        entry.add_to_hass(hass)
        return entry

    return _make


async def _setup(hass, entry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_auto_renew_window(hass, opac, make_entry):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    events = async_capture_events(hass, EVENT_RENEWAL)
    await _setup(hass, entry)
    assert renew_posts(opac) == [["verlaengere_nr_0900000101", "verlaengere_nr_0900000102"]]
    assert events[0].data["trigger"] == "auto"
    assert [i["mednr"] for i in events[0].data["items"]] == ["0900000101", "0900000102"]


async def test_auto_renew_window_excludes_later_items(hass, opac, make_entry):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 1})
    await _setup(hass, entry)
    assert renew_posts(opac) == [["verlaengere_nr_0900000101"]]  # CD is 2 days out


async def test_auto_renew_categories(hass, opac, make_entry):
    entry = await make_entry(
        **{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2, CONF_AUTO_RENEW_CATEGORIES: ["tonie"]}
    )
    await _setup(hass, entry)
    assert renew_posts(opac) == [["verlaengere_nr_0900000101"]]


async def test_auto_renew_dedup(hass, opac, make_entry):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(renew_posts(opac)) == 1  # due dates unchanged -> not requested again


async def test_auto_renew_retries_lapsed_request_next_day(hass, opac, make_entry, freezer):
    """The library can drop a request: the item is renewable again with the same due date."""
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    assert len(renew_posts(opac)) == 1
    freezer.tick(86400)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(renew_posts(opac)) == 2


async def test_auto_renew_off(hass, opac, make_entry):
    entry = await make_entry(**{CONF_AUTO_RENEW: False, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()
    assert renew_posts(opac) == []


async def test_auto_renew_default_is_off(hass, opac, make_entry):
    entry = await make_entry()
    await _setup(hass, entry)
    assert renew_posts(opac) == []


async def test_auto_renew_error_keeps_update(hass, opac, make_entry, caplog):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    with (
        patch.object(FindusClient, "renew", side_effect=aiohttp.ClientError("down")),
        caplog.at_level(logging.WARNING),
    ):
        await _setup(hass, entry)
    coordinator = entry.runtime_data
    assert coordinator.last_update_success
    assert len(coordinator.data.loans) == 5
    assert "failed: down" in caplog.text and "Kinder" not in caplog.text
