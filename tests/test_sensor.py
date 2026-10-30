"""Sensor and binary sensor states on the synthetic fixture."""
from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.findus_opac.const import DOMAIN

# Fixture loans: Tonie due 2026-11-06 (renewable), CD 11-08 (renewable),
# book 11-27, nonfiction 10-20 (overdue), DVD 11-27 (video, disabled by default).
NOW = "2026-11-06 10:00:00+01:00"


@pytest.fixture
async def setup(hass, freezer, opac, entry):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to(NOW)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def state(platform: str, key: str):
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        assert entity_id, f"{platform}.{key} not registered"
        return hass.states.get(entity_id)

    return state


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("loans", "5"),
        ("book", "2"),
        ("tonie", "1"),
        ("cd", "1"),
        ("game", None),  # disabled by default
        ("video", None),
        ("next_due", "2026-10-20"),
        ("days_left", "-17"),
        ("due_today", "1"),
        ("due_soon", "2"),
        ("overdue", "1"),
        ("renewable", "2"),
    ],
)
async def test_sensor_states(setup, key, expected):
    st = setup("sensor", key)
    if expected is None:
        assert st is None
    else:
        assert st is not None and st.state == expected


async def test_items_attribute_shape(setup):
    items = setup("sensor", "loans").attributes["items"]
    assert [i["due"] for i in items] == sorted(i["due"] for i in items)
    first = items[0]
    assert set(first) == {
        "mednr", "title", "author", "media_type", "category",
        "due", "days_left", "renewable", "note",
    }
    assert (first["title"], first["days_left"], first["category"]) == ("Wale & Delfine", -17, "book")
    assert first["note"] == "Das Medium ist vorbestellt."
    tonie = setup("sensor", "tonie").attributes["items"]
    assert [i["mednr"] for i in tonie] == ["0900000101"]
    assert setup("sensor", "next_due").attributes["titles"] == ["Wale & Delfine"]


async def test_binary_sensors(setup):
    overdue = setup("binary_sensor", "has_overdue")
    assert overdue.state == "on"
    assert [i["mednr"] for i in overdue.attributes["items"]] == ["0900000104"]
    renew = setup("binary_sensor", "can_renew")
    assert renew.state == "on"
    assert [i["mednr"] for i in renew.attributes["items"]] == ["0900000101", "0900000102"]


async def test_entity_names_use_account_device(setup):
    st = setup("sensor", "loans")
    assert st.attributes["friendly_name"] == "Kinder Loans"
    assert st.entity_id == "sensor.kinder_loans"
