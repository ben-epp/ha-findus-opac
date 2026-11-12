"""Library data date, opening hours, last-chance reminders and the due date calendar."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.findus_opac.client import parse_last_sync, parse_opening_hours
from custom_components.findus_opac.notifications import FindusNotifier
from custom_components.findus_opac.const import CONF_NOTIFY_SHOW_TITLES, CONF_NOTIFY_TARGETS, CONF_NOTIFY_TIME, DOMAIN

from .conftest import CARD, ENTRY_DATA


@pytest.fixture(autouse=True)
async def berlin(hass):
    """Library times are German local time; the test default is US/Pacific."""
    await hass.config.async_set_time_zone("Europe/Berlin")


def _hours_page(*rows: tuple[str, ...], note: str = "") -> str:
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    tail = f"</ul> <p>{note}</p>" if note else ""
    return f'<ul><table id="oeffnungszeiten" class="zebra">{body}</table>{tail}<h2>Kontakt</h2>'


WEEK = _hours_page(
    ("Montag", "", "16:00 - 19:00 Uhr"),
    ("Dienstag", "geschlossen", ""),
    ("Mittwoch", "9:30 - 12:30 Uhr", "14:00 - 17:00 Uhr"),
    ("Samstag", "9.00 - 12.00 uhr", "Jeden 1. Samstag im Monat"),
    note="Geschlossen an Heilig Abend",
)
MONDAYS_ONLY = _hours_page(("Montag", "09:00 - 17:00 Uhr", ""))


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute)  # 2026-11-02 is a Monday


def test_parse_opening_hours():
    hours = parse_opening_hours(WEEK)
    assert hours.days[0].intervals == ((time(16), time(19)),)
    assert hours.days[1].intervals == () and not hours.days[1].conditional
    assert hours.days[2].intervals == ((time(9, 30), time(12, 30)), (time(14), time(17)))
    assert hours.days[5].conditional and hours.days[5].intervals == ((time(9), time(12)),)
    assert hours.note == "Geschlossen an Heilig Abend"


@pytest.mark.parametrize(
    "page",
    ["<p>no table</p>", _hours_page(("Montag", "Siehe Homepage der Bibliothek", ""))],
)
def test_no_usable_hours(page):
    assert parse_opening_hours(page) is None


@pytest.mark.parametrize(
    ("cell", "conditional"),
    [
        ("geschlosssen", False),  # typo seen on a real page
        ("15:00 - 18:00 Unr", False),
        ("9:00 - 18:00 durchgehend", False),
        ("In den Schulferien geschlossen", True),
        ("16:00 - 19:00 Uhr (öffentliche Ausleihe)", True),
    ],
)
def test_real_world_cells(cell, conditional):
    hours = parse_opening_hours(_hours_page(("Montag", "10:00 - 11:00", cell)))
    assert hours.days[0].conditional is conditional


def test_is_open_closes_at_next_open():
    hours = parse_opening_hours(WEEK)
    assert hours.is_open(_at(2, 16)) is True
    assert hours.closes_at(_at(2, 16)) == time(19)
    assert hours.is_open(_at(2, 19)) is False  # closing time is exclusive
    assert hours.is_open(_at(3, 12)) is False  # closed day
    assert hours.is_open(_at(7, 10)) is None  # conditional day
    assert hours.next_open(_at(4, 13)) == _at(4, 14)  # lunch break
    assert hours.next_open(_at(4, 18)) == _at(9, 16)  # skips the conditional Saturday


def test_last_open_before():
    hours = parse_opening_hours(WEEK)
    assert hours.last_open_before(date(2026, 11, 4)) == (date(2026, 11, 4), time(17))  # open that day
    assert hours.last_open_before(date(2026, 11, 3)) == (date(2026, 11, 2), time(19))  # closed Tuesday
    # Sunday: walking back hits the conditional Saturday, so no claim at all.
    assert hours.last_open_before(date(2026, 11, 8)) is None


def test_nth_open_day_after():
    hours = parse_opening_hours(WEEK)
    # Closed Sunday, open Monday, closed Tuesday: the conditional Saturday counts as open.
    assert hours.nth_open_day_after(date(2026, 11, 3), 2) == date(2026, 11, 7)
    assert hours.nth_open_day_after(date(2026, 11, 7), 1) == date(2026, 11, 9)
    mondays = parse_opening_hours(MONDAYS_ONLY)
    assert mondays.nth_open_day_after(date(2026, 11, 4), 2) == date(2026, 11, 16)
    assert mondays.nth_open_day_after(date(2026, 11, 4), 1, horizon=4) is None


def test_parse_last_sync():
    page = "letztes Datenbankupdate: 20.10.2026, 17:01 Uhr. 31 Zugriffe"
    assert parse_last_sync(page) == datetime(2026, 10, 20, 17, 1)
    assert parse_last_sync("nothing") is None
    assert parse_last_sync("letztes Datenbankupdate: 99.10.2026, 17:01 Uhr") is None


def _entity(hass, entry, domain: str, key: str) -> str:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")


async def test_last_sync_sensor_uses_login_page_footer(hass, opac, entry):
    opac.login += "letztes Datenbankupdate: 20.10.2026, 17:01 Uhr."
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = _entity(hass, entry, "sensor", "last_sync")
    assert registry.async_get(entity_id).entity_category == "diagnostic"
    expected = datetime(2026, 10, 20, 17, 1, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    assert dt_util.parse_datetime(hass.states.get(entity_id).state) == expected


async def test_open_now_follows_the_clock(hass, freezer, opac, entry):
    opac.hours_page = WEEK
    freezer.move_to("2026-11-02 15:59:00+01:00")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _entity(hass, entry, "binary_sensor", "open_now")
    state = hass.states.get(entity_id)
    assert state.state == "off"
    assert state.attributes["hours"]["monday"] == ["16:00-19:00"]
    assert state.attributes["conditional_days"] == ["saturday"]
    assert state.attributes["note"] == "Geschlossen an Heilig Abend"

    freezer.move_to("2026-11-02 16:00:00+01:00")
    async_fire_time_changed(hass, dt_util.now())
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes["closes_at"] == "19:00"


async def test_open_now_unavailable_without_hours(hass, opac, loaded_entry):
    assert hass.states.get(_entity(hass, loaded_entry, "binary_sensor", "open_now")).state == "unavailable"


async def test_hours_failure_does_not_break_the_poll(hass, opac, entry):
    """The account still loads; opening hours are simply unknown until the next poll."""
    opac.hours_exc = aiohttp.ClientError("down")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.hours is None
    assert len(entry.runtime_data.data.loans) == 5


async def test_hours_fetched_once_a_day(hass, freezer, opac, loaded_entry):
    def hour_gets() -> int:
        return sum(1 for c in opac.mock.mock_calls if "zeige_" in str(c[1]))

    assert hour_gets() == 1
    await loaded_entry.runtime_data.async_refresh()
    assert hour_gets() == 1
    freezer.tick(timedelta(days=1))
    await loaded_entry.runtime_data.async_refresh()
    assert hour_gets() == 2


def _notify_entry(**options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kinder",
        data=dict(ENTRY_DATA),
        unique_id=f"musterstadt_{CARD}",
        options={CONF_NOTIFY_TARGETS: ["mobile_app_phone"], CONF_NOTIFY_TIME: "08:00:00", **options},
    )


async def _digest(hass, freezer, entry, when: str) -> None:
    freezer.move_to(when)
    if entry.state.value == "not_loaded":
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.now())
    await hass.async_block_till_done()


@pytest.fixture
async def de(hass):
    hass.config.language = "de"


async def test_last_chance_reminder(hass, freezer, opac, de):
    """Book and DVD are due Fri 27 Nov, the library only opens on Mondays."""
    opac.hours_page = MONDAYS_ONLY
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _notify_entry(**{CONF_NOTIFY_SHOW_TITLES: False})
    await _digest(hass, freezer, entry, "2026-11-23 07:59:59+01:00")
    lines = calls[0].data["message"].splitlines()
    assert "Letzte Chance heute bis 17:00: 2 Medien (am Rückgabetag geschlossen)" in lines
    assert lines[-1] == "Reguläre Öffnungszeiten, an Feiertagen können sie abweichen."

    # A second run on the same day has nothing new, even after a restart.
    calls.clear()
    await FindusNotifier(hass, entry.runtime_data).async_run()
    await hass.async_block_till_done()
    assert not calls


async def test_no_last_chance_when_disabled(hass, freezer, opac, de):
    opac.hours_page = MONDAYS_ONLY
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _notify_entry(notify_events=["overdue"])
    await _digest(hass, freezer, entry, "2026-11-23 07:59:59+01:00")
    assert not any("Letzte Chance" in c.data["message"] for c in calls)


async def test_due_soon_names_the_last_opening(hass, freezer, opac, de):
    """CD due Sun 8 Nov; the library is open on Saturdays."""
    opac.hours_page = _hours_page(("Samstag", "10:00 - 12:00 Uhr", ""))
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _notify_entry(**{CONF_NOTIFY_SHOW_TITLES: False})
    await _digest(hass, freezer, entry, "2026-11-06 07:59:59+01:00")
    assert (
        "Fällig am So., 8.11., da geschlossen – letzte Chance Sa., 7.11. bis 12:00: 1 Medium"
        in calls[0].data["message"].splitlines()
    )


async def test_calendar_events(hass, freezer, opac, entry):
    freezer.move_to("2026-11-06 12:00:00+01:00")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _entity(hass, entry, "calendar", "due_dates")
    state = hass.states.get(entity_id)
    assert state.attributes["message"] == "Library return: 1 item"  # no title in the recorder
    assert state.attributes["start_time"].startswith("2026-11-06")

    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {"entity_id": entity_id, "start_date_time": "2026-11-27 00:00:00", "end_date_time": "2026-11-28 00:00:00"},
        blocking=True,
        return_response=True,
    )
    events = result[entity_id]["events"]
    assert len(events) == 1
    assert events[0]["summary"] == "Library return: 2 items"
    assert events[0]["start"] == "2026-11-27" and events[0]["end"] == "2026-11-28"
    assert events[0]["description"].count("\n") == 1  # one title per line
