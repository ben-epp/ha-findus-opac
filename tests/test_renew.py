"""Renew button, renew service, renewal event and delayed re-check."""
from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.findus_opac.const import DOMAIN, EVENT_RENEWAL

from .conftest import PAGE
from .pages import requested

RENEWED = PAGE.replace(
    '<span class="sortierhinweis">2026-11-06</span>',
    '<span class="sortierhinweis">2026-12-04</span>',
)


def _button(hass, entry) -> str:
    return er.async_get(hass).async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_renew_all")


async def _press(hass, entry) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": _button(hass, entry)}, blocking=True
    )


async def test_press_renews_all_renewable(hass, opac, loaded_entry):
    events = async_capture_events(hass, EVENT_RENEWAL)
    await _press(hass, loaded_entry)
    renew = opac.posts[-1]
    assert sorted(k for k in renew if k.startswith("verlaengere_nr_")) == [
        "verlaengere_nr_0900000101",
        "verlaengere_nr_0900000102",
    ]
    assert renew["verlaengerungsantrag"] == "1"
    assert len(events) == 1
    data = events[0].data
    assert data["config_entry_id"] == loaded_entry.entry_id
    assert data["account_name"] == "Kinder"
    assert data["trigger"] == "manual"
    assert [(i["mednr"], i["status"]) for i in data["items"]] == [
        ("0900000101", "requested"),
        ("0900000102", "requested"),
    ]
    assert set(data["items"][0]) == {"mednr", "title", "old_due", "new_due", "status"}


async def test_press_detects_renewed(hass, opac, loaded_entry):
    events = async_capture_events(hass, EVENT_RENEWAL)
    # login before renewal, then the response: 0101 moved, 0102 marked as requested
    opac.queue = [PAGE, requested(RENEWED, ["0900000102"])]
    await _press(hass, loaded_entry)
    items = {i["mednr"]: i for i in events[0].data["items"]}
    assert items["0900000101"]["status"] == "renewed"
    assert items["0900000101"]["old_due"] == "2026-11-06"
    assert items["0900000101"]["new_due"] == "2026-12-04"
    assert items["0900000102"]["status"] == "requested"
    # Coordinator data is the post-renewal account.
    loan = loaded_entry.runtime_data.data.loan("0900000101")
    assert loan.due.isoformat() == "2026-12-04"


async def test_service_with_media_ids_returns_response(hass, opac, loaded_entry):
    result = await hass.services.async_call(
        DOMAIN,
        "renew",
        {"config_entry_id": loaded_entry.entry_id, "media_ids": ["0900000102", "0900000103"]},
        blocking=True,
        return_response=True,
    )
    assert [i["mednr"] for i in result["items"]] == ["0900000102"]  # 103 not renewable
    renew = opac.posts[-1]
    assert [k for k in renew if k.startswith("verlaengere_nr_")] == ["verlaengere_nr_0900000102"]


async def test_service_unknown_entry(hass, opac, loaded_entry):
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call(
            DOMAIN, "renew", {"config_entry_id": "nope"}, blocking=True
        )
    assert exc.value.translation_key == "entry_not_found"
    assert exc.value.translation_placeholders == {"config_entry_id": "nope"}


async def test_renew_network_error(hass, opac, loaded_entry):
    opac.fail_network()
    with pytest.raises(HomeAssistantError) as exc:
        await _press(hass, loaded_entry)
    assert exc.value.translation_key == "renew_failed"
    assert exc.value.translation_placeholders["error"] == "boom"


async def test_renew_auth_error(hass, opac, loaded_entry):
    opac.reject_login()
    with pytest.raises(HomeAssistantError) as exc:
        await _press(hass, loaded_entry)
    assert exc.value.translation_key == "renew_auth_failed"


async def test_requested_triggers_recheck(hass, opac, loaded_entry):
    await _press(hass, loaded_entry)
    gets = opac.gets
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=29))
    await hass.async_block_till_done()
    assert opac.gets == gets
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done()
    assert opac.gets == gets + 1


async def test_renewed_only_schedules_no_recheck(hass, opac, loaded_entry):
    # Make both renewable items move so nothing stays "requested".
    both = RENEWED.replace(
        '<span class="sortierhinweis">2026-11-08</span>',
        '<span class="sortierhinweis">2026-12-06</span>',
    )
    opac.queue = [PAGE, both]
    await _press(hass, loaded_entry)
    gets = opac.gets
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done()
    assert opac.gets == gets


async def test_nothing_renewable_fires_empty_event(hass, opac, loaded_entry):
    events = async_capture_events(hass, EVENT_RENEWAL)
    opac.page = PAGE.replace("verlaengerung_ist_moeglich_ja", "verlaengerung_ist_moeglich_nein")
    await _press(hass, loaded_entry)
    assert events[0].data["items"] == []


async def test_service_categories(hass, opac, loaded_entry):
    events = async_capture_events(hass, EVENT_RENEWAL)
    result = await hass.services.async_call(
        DOMAIN,
        "renew",
        {"config_entry_id": loaded_entry.entry_id, "categories": ["tonie"]},
        blocking=True,
        return_response=True,
    )
    assert [i["mednr"] for i in result["items"]] == ["0900000101"]
    renew = opac.posts[-1]
    assert [k for k in renew if k.startswith("verlaengere_nr_")] == ["verlaengere_nr_0900000101"]
    assert events[0].data["trigger"] == "manual"


async def test_service_categories_without_match_posts_nothing(hass, opac, loaded_entry):
    events = async_capture_events(hass, EVENT_RENEWAL)
    posts = len(opac.posts)
    result = await hass.services.async_call(
        DOMAIN,
        "renew",
        {"config_entry_id": loaded_entry.entry_id, "categories": ["game"]},
        blocking=True,
        return_response=True,
    )
    assert result == {"items": []}
    assert len(opac.posts) == posts  # no login, no renewal
    assert events[0].data["items"] == []


async def test_service_rejects_unknown_category(hass, opac, loaded_entry):
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"config_entry_id": loaded_entry.entry_id, "categories": ["comics"]},
            blocking=True,
        )


async def test_sync_button_refreshes(hass, opac, loaded_entry):
    entity_id = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{loaded_entry.entry_id}_sync"
    )
    assert entity_id
    gets, posts = opac.gets, len(opac.posts)
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    assert opac.gets == gets + 1
    assert len(opac.posts) == posts + 1
    assert not any(k.startswith("verlaengere_nr_") for k in opac.posts[-1])


async def test_renew_not_accepted_raises(hass, opac, loaded_entry):
    opac.queue = [PAGE, PAGE]  # renewal response without banner or marked rows
    with pytest.raises(HomeAssistantError) as exc:
        await _press(hass, loaded_entry)
    assert exc.value.translation_key == "renew_failed"


async def test_pending_item_stays_listed(hass, opac, loaded_entry):
    await _press(hass, loaded_entry)
    state = hass.states.get("sensor.kinder_loans")
    assert state.state == "5"
    items = {i["mednr"]: i for i in state.attributes["items"]}
    assert items["0900000101"]["renew_requested"] is True
    assert items["0900000101"]["renewable"] is False
