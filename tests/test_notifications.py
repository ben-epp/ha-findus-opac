"""Built-in notifications: daily digest, dedup, renewal notices, mobile 'Renew' action."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)
from homeassistant.util import dt as dt_util

from custom_components.findus_opac.client import Loan
from custom_components.findus_opac.const import (
    CONF_NOTIFY_EVENTS,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_TIME,
    DOMAIN,
    EVENT_RENEWAL,
)
from custom_components.findus_opac.notifications import (
    async_load_texts,
    build_message,
    build_renewal_message,
)

from .conftest import CARD, ENTRY_DATA

# Fixture loans on 2026-11-06 (Friday): overdue nonfiction (10-20), Tonie due today
# (renewable), CD due 11-08 (renewable), book + DVD 11-27; card valid until 2026-12-01.
DAY1 = "2026-11-06 07:59:59+01:00"
DAY2 = "2026-11-07 07:59:59+01:00"


def _entry(**options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kinder",
        data=dict(ENTRY_DATA),
        unique_id=f"musterstadt_{CARD}",
        options={CONF_NOTIFY_TARGETS: ["mobile_app_phone"], CONF_NOTIFY_TIME: "08:00:00", **options},
    )


async def _setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _fire_at(hass, freezer, when: str) -> None:
    """Jump to just before `when`'s 08:00, then let the 08:00 trigger fire."""
    freezer.move_to(when)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    freezer.tick(1)
    async_fire_time_changed(hass, dt_util.now())
    await hass.async_block_till_done()


@pytest.fixture
async def de(hass):
    await hass.config.async_set_time_zone("Europe/Berlin")
    hass.config.language = "de"


async def test_daily_digest(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    entry = _entry()
    await _setup(hass, entry)
    await _fire_at(hass, freezer, DAY1)

    assert len(calls) == 1
    data = calls[0].data
    assert data["title"] == "Bücherei: Kinder"
    assert data["message"].splitlines() == [
        "Überfällig seit 17 Tagen: Wieso? Weshalb? Warum? – Wale & Delfine",
        "Heute fällig: Der kleine Drache (verlängerbar)",
        "Fällig am So., 8.11.: Lieder zum Mitsingen (verlängerbar)",
        "Ausweis gültig bis 01.12.2026 – bitte verlängern lassen",
    ]
    assert data["data"]["tag"] == f"findus_opac_{entry.entry_id}"
    assert data["data"]["group"] == "findus_opac"
    assert data["data"]["actions"] == [
        {"action": f"FINDUS_OPAC_RENEW_{entry.entry_id}", "title": "Verlängern"}
    ]


async def test_next_day_only_overdue_repeats(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    await _setup(hass, _entry())
    await _fire_at(hass, freezer, DAY1)
    await _fire_at(hass, freezer, DAY2)

    assert len(calls) == 2
    lines = calls[1].data["message"].splitlines()
    # The Tonie due yesterday is overdue now; the CD (due soon) and the card were already sent.
    assert lines == [
        "Überfällig seit 18 Tagen: Wieso? Weshalb? Warum? – Wale & Delfine",
        "Überfällig seit 1 Tag: Der kleine Drache (verlängerbar)",
    ]


async def test_dedup_survives_reload(hass, freezer, opac, de, hass_storage):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    entry = _entry()
    await _setup(hass, entry)
    await _fire_at(hass, freezer, DAY1)
    assert f"{DOMAIN}.notified.{entry.entry_id}" in hass_storage

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await _fire_at(hass, freezer, DAY2)
    assert len(calls) == 2
    assert "Fällig am" not in calls[1].data["message"]
    assert "Ausweis" not in calls[1].data["message"]


async def test_catch_up_after_missed_notify_time(hass, freezer, opac, de):
    """HA down at 08:00 (e.g. restart): the digest goes out right after start."""
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to("2026-11-06 09:30:00+01:00")
    entry = _entry()
    await _setup(hass, entry)
    assert len(calls) == 1
    assert "Heute fällig: Der kleine Drache (verlängerbar)" in calls[0].data["message"]

    # Another restart the same day: digest already ran, nothing is repeated.
    freezer.move_to("2026-11-06 11:00:00+01:00")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_no_catch_up_before_notify_time(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to("2026-11-06 07:00:00+01:00")
    await _setup(hass, _entry())
    assert calls == []


async def test_nothing_new_sends_nothing(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    await _setup(hass, _entry(**{CONF_NOTIFY_EVENTS: ["due_soon"]}))
    await _fire_at(hass, freezer, DAY1)
    await _fire_at(hass, freezer, DAY2)
    assert len(calls) == 1  # CD due soon once; day 2 has nothing new


async def test_event_filter(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    await _setup(hass, _entry(**{CONF_NOTIFY_EVENTS: ["due_today"]}))
    await _fire_at(hass, freezer, DAY1)
    assert len(calls) == 1
    assert calls[0].data["message"] == "Heute fällig: Der kleine Drache (verlängerbar)"


async def test_no_targets_no_notifier(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    await _setup(hass, _entry(**{CONF_NOTIFY_TARGETS: []}))
    await _fire_at(hass, freezer, DAY1)
    assert calls == []
    assert "mobile_app_notification_action" not in hass.bus.async_listeners()


async def test_non_mobile_target_gets_no_data(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "family_email")
    freezer.move_to(DAY1)
    await _setup(hass, _entry(**{CONF_NOTIFY_TARGETS: ["family_email"]}))
    await _fire_at(hass, freezer, DAY1)
    assert len(calls) == 1
    assert "data" not in calls[0].data


async def test_missing_target_is_skipped(hass, freezer, opac, de, caplog):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    await _setup(hass, _entry(**{CONF_NOTIFY_TARGETS: ["mobile_app_gone", "mobile_app_phone"]}))
    await _fire_at(hass, freezer, DAY1)
    assert len(calls) == 1
    assert "notify.mobile_app_gone not found" in caplog.text


async def test_mobile_action_renews_and_notifies(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    entry = _entry()
    await _setup(hass, entry)
    posts_before = len(opac.posts)

    hass.bus.async_fire("mobile_app_notification_action", {"action": "SOMETHING_ELSE"})
    await hass.async_block_till_done()
    assert len(opac.posts) == posts_before

    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": f"FINDUS_OPAC_RENEW_{entry.entry_id}"}
    )
    await hass.async_block_till_done()
    renew = opac.posts[-1]
    assert sorted(k for k in renew if k.startswith("verlaengere_nr_")) == [
        "verlaengere_nr_0900000101",
        "verlaengere_nr_0900000102",
    ]
    # The renewal event that follows produces a notice (same page back -> "requested").
    assert calls[-1].data["message"] == (
        "Verlängerung beantragt: Der kleine Drache, Lieder zum Mitsingen"
    )


async def test_mobile_action_failure_notifies(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    entry = _entry()
    await _setup(hass, entry)
    opac.fail_network()
    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": f"FINDUS_OPAC_RENEW_{entry.entry_id}"}
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["message"].startswith("Verlängerung fehlgeschlagen:")


async def test_auto_renewal_event_notice(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    entry = _entry()
    await _setup(hass, entry)
    hass.bus.async_fire(
        EVENT_RENEWAL,
        {
            "config_entry_id": entry.entry_id,
            "account_name": "Kinder",
            "trigger": "auto",
            "items": [
                {"mednr": "1", "title": "Der kleine Drache", "old_due": "2026-11-06",
                 "new_due": "2026-11-06", "status": "requested"},
                {"mednr": "2", "title": "Lieder zum Mitsingen", "old_due": "2026-11-08",
                 "new_due": "2026-12-06", "status": "renewed"},
            ],
        },
    )
    # Other accounts and empty renewals are ignored
    hass.bus.async_fire(EVENT_RENEWAL, {"config_entry_id": "other", "items": [{"title": "x"}]})
    hass.bus.async_fire(EVENT_RENEWAL, {"config_entry_id": entry.entry_id, "items": []})
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["message"] == (
        "Automatisch: Verlängerung beantragt: Der kleine Drache\n"
        "Verlängert bis So., 6.12.: Lieder zum Mitsingen"
    )
    assert "actions" not in calls[0].data["data"]


async def test_renewal_notices_can_be_disabled(hass, freezer, opac, de):
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    freezer.move_to(DAY1)
    entry = _entry(**{CONF_NOTIFY_EVENTS: ["due_today"]})
    await _setup(hass, entry)
    hass.bus.async_fire(
        EVENT_RENEWAL,
        {"config_entry_id": entry.entry_id, "trigger": "manual",
         "items": [{"title": "A", "status": "requested"}]},
    )
    await hass.async_block_till_done()
    assert calls == []


TRANSLATIONS = Path(__file__).parent.parent / "custom_components" / "findus_opac" / "translations"


def texts(lang: str) -> dict[str, str]:
    """Notification texts straight from translations/<lang>.json."""
    exc = json.loads((TRANSLATIONS / f"{lang}.json").read_text())["exceptions"]
    return {k.removeprefix("notify_"): v["message"] for k, v in exc.items() if k.startswith("notify_")}


async def test_texts_load_through_ha_with_english_fallback(hass):
    assert await async_load_texts(hass, "de") == texts("de")
    assert await async_load_texts(hass, "fr") == texts("en")


def test_translations_have_same_notify_keys():
    keys = {lang: set(texts(lang)) for lang in ("en", "de")}
    assert keys["en"] == keys["de"]
    assert len(keys["en"]) > 10


def _loan(mednr, title, due, renewable=False):
    return Loan(mednr=mednr, title=title, author="", media_type="", due=due, renewable=renewable)


def test_build_message_de():
    today = date(2026, 11, 6)
    title, msg = build_message(
        texts("de"),
        "Kinder",
        {
            "overdue": [_loan("1", "A", date(2026, 11, 5)), _loan("2", "B", date(2026, 11, 3))],
            "due_today": [_loan("3", "C", today, renewable=True)],
            "due_soon": [
                _loan("4", "D", date(2026, 11, 9)),
                _loan("5", "E", date(2026, 11, 8)),
                _loan("6", "F", date(2026, 11, 8)),
            ],
        },
        date(2026, 11, 13),
        today,
    )
    assert title == "Bücherei: Kinder"
    assert msg.splitlines() == [
        "Überfällig seit 3 Tagen: B",
        "Überfällig seit 1 Tag: A",
        "Heute fällig: C (verlängerbar)",
        "Fällig am So., 8.11.: E, F",
        "Fällig am Mo., 9.11.: D",
        "Ausweis gültig bis 13.11.2026 – bitte verlängern lassen",
    ]


def test_build_message_en_and_expired_card():
    today = date(2026, 11, 6)
    title, msg = build_message(
        texts("en"),
        "Kids",
        {"due_soon": [_loan("1", "A", date(2026, 11, 8), renewable=True)]},
        date(2026, 11, 1),
        today,
    )
    assert title == "Library: Kids"
    assert msg.splitlines() == [
        "Due Sun 8 Nov: A (renewable)",
        "Library card expired on 1 Nov 2026 – please have it renewed",
    ]


def test_build_renewal_message_en():
    title, msg = build_renewal_message(
        texts("en"),
        "Kids",
        [{"title": "A", "status": "renewed", "new_due": "2026-12-04"}],
        "manual",
    )
    assert (title, msg) == ("Library: Kids", "Renewed until Fri 4 Dec: A")


def test_renewal_message_failed_and_pending_suffix():
    _, msg = build_renewal_message(
        texts("de"), "Kinder", [{"title": "A", "status": "failed"}, {"title": "B", "status": "requested"}], "manual"
    )
    assert msg == "Verlängerung beantragt: B\nVerlängerung nicht angenommen: A"
