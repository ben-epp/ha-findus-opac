"""Sensor and binary sensor states on the synthetic fixture."""
from __future__ import annotations

from pathlib import Path

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
        ("card_valid_until", "2026-12-01"),
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
        "due", "days_left", "renewable", "renew_requested", "note", "cover", "series",
    }
    assert (first["title"], first["days_left"], first["category"]) == (
        "Wieso? Weshalb? Warum? – Wale & Delfine", -17, "book"
    )
    assert first["series"] == "Wieso? Weshalb? Warum?"
    assert first["note"] == "Das Medium ist vorbestellt."
    assert first["cover"] == ""
    tonie = setup("sensor", "tonie").attributes["items"]
    assert [i["mednr"] for i in tonie] == ["0900000101"]
    assert tonie[0]["cover"].endswith("/4000000000017.jpg")
    assert setup("sensor", "next_due").attributes["titles"] == [
        "Wieso? Weshalb? Warum? – Wale & Delfine"
    ]


async def test_binary_sensors(setup):
    overdue = setup("binary_sensor", "has_overdue")
    assert overdue.state == "on"
    assert [i["mednr"] for i in overdue.attributes["items"]] == ["0900000104"]
    renew = setup("binary_sensor", "can_renew")
    assert renew.state == "on"
    assert [i["mednr"] for i in renew.attributes["items"]] == ["0900000101", "0900000102"]


async def test_card_expiry(setup):
    assert setup("sensor", "card_valid_until").attributes["days_left"] == 25
    soon = setup("binary_sensor", "card_expires_soon")
    assert soon.state == "on"  # 25 days left, warning starts at 30
    assert soon.attributes == {
        **soon.attributes,
        "valid_until": "2026-12-01",
        "warn_days": 30,
    }


def test_card_expiry_states_without_hass():
    from datetime import date
    from types import SimpleNamespace

    from custom_components.findus_opac.binary_sensor import _card_expires_soon

    def coord(until):
        return SimpleNamespace(
            data=SimpleNamespace(card_valid_until=until), today=lambda: date(2026, 11, 6)
        )

    assert _card_expires_soon(coord(None)) is None  # no banner: unknown, not "off"
    assert _card_expires_soon(coord(date(2027, 6, 15))) is False
    assert _card_expires_soon(coord(date(2026, 12, 6))) is True  # exactly 30 days


async def test_entity_names_use_account_device(setup):
    st = setup("sensor", "loans")
    assert st.attributes["friendly_name"] == "Kinder Loans"
    assert st.entity_id == "sensor.kinder_loans"


NOTICE = (Path(__file__).parent / "fixtures" / "notice_closure.html").read_text()


async def test_announcement_sensor_none_without_notice(setup):
    st = setup("sensor", "announcement")
    assert st is not None and st.state == "unknown"
    assert "text" not in st.attributes


async def test_announcement_sensor_with_notice(hass, freezer, opac, entry):
    opac.login += NOTICE
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_announcement")
    st = hass.states.get(eid)
    assert st.state == "Urlaub der Bibliothek"
    a = st.attributes
    assert (a["kind"], a["truncated"]) == ("closure", False)
    assert a["text"].startswith("Liebe Leser,") and len(a["images"]) == 1
    assert a["url"].endswith("?customer=musterstadt")
