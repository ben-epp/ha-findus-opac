"""Auto-renew on coordinator refresh."""
from __future__ import annotations

from datetime import date
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

from .conftest import CARD, ENTRY_DATA, PAGE
from .pages import requested

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


async def _refresh(hass, entry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _item(hass, mednr: str) -> dict:
    state = hass.states.get("sensor.kinder_loans")
    return next(i for i in state.attributes["items"] if i["mednr"] == mednr)


async def test_pending_request_survives_findus_forgetting_it(hass, opac, make_entry, freezer):
    """Findus shows the item as renewable again at the next upload; staff have not acted yet."""
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    assert len(renew_posts(opac)) == 1
    freezer.tick(86400)  # the fake account page shows both items as renewable again
    await _refresh(hass, entry)
    assert len(renew_posts(opac)) == 1  # not requested twice
    item = _item(hass, "0900000101")
    assert (item["renewable"], item["renew_requested"], item["renew_requested_on"]) == (
        False, True, "2026-11-06",
    )


async def test_pending_request_retried_once_after_library_had_time(hass, opac, make_entry, freezer):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    until = entry.runtime_data.pending_until(date(2026, 11, 6))
    freezer.tick(86400 * (until - date(2026, 11, 6)).days)
    await _refresh(hass, entry)
    assert len(renew_posts(opac)) == 1  # still pending on its last day
    freezer.tick(86400)
    await _refresh(hass, entry)
    assert len(renew_posts(opac)) == 2
    await _refresh(hass, entry)
    assert len(renew_posts(opac)) == 2  # and that one is pending again


async def test_pending_request_survives_restart(hass, opac, make_entry, freezer):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    freezer.tick(86400)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(renew_posts(opac)) == 1


async def test_renew_all_skips_pending_but_explicit_ids_are_sent(hass, opac, make_entry):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    await _refresh(hass, entry)
    assert await coordinator.async_renew() == []
    assert len(renew_posts(opac)) == 1
    await coordinator.async_renew(["0900000101"])
    assert renew_posts(opac)[-1] == ["verlaengere_nr_0900000101"]


async def test_request_made_on_website_counts_as_pending(hass, opac, make_entry, freezer):
    opac.page = requested(opac.page, ["0900000101"])
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    assert renew_posts(opac) == [["verlaengere_nr_0900000102"]]
    opac.page = PAGE  # Findus forgot the request
    freezer.tick(3600)
    await _refresh(hass, entry)
    assert renew_posts(opac) == [["verlaengere_nr_0900000102"]]
    assert _item(hass, "0900000101")["renew_requested"] is True


async def test_requests_dropped_when_due_date_moves(hass, opac, make_entry, freezer, hass_storage):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    key = f"{DOMAIN}.requests.{entry.entry_id}"
    assert set(hass_storage[key]["data"]) == {"0900000101", "0900000102"}
    opac.page = PAGE.replace(
        '<span class="sortierhinweis">2026-11-06</span>', '<span class="sortierhinweis">2026-12-04</span>'
    )
    freezer.tick(3600)
    await _refresh(hass, entry)
    assert set(hass_storage[key]["data"]) == {"0900000102"}
    item = _item(hass, "0900000101")
    assert (item["due"], item["renew_requested"]) == ("2026-12-04", False)


async def test_removing_entry_deletes_stored_requests(hass, opac, make_entry, hass_storage):
    entry = await make_entry(**{CONF_AUTO_RENEW: True, CONF_AUTO_RENEW_DAYS: 2})
    await _setup(hass, entry)
    key = f"{DOMAIN}.requests.{entry.entry_id}"
    assert key in hass_storage
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


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
