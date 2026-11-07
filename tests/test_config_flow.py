"""Config, reauth and options flows."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.findus_opac.config_flow import normalize_subdomain
from custom_components.findus_opac.const import (
    CONF_AUTO_RENEW,
    CONF_AUTO_RENEW_CATEGORIES,
    CONF_AUTO_RENEW_DAYS,
    CONF_DUE_SOON_DAYS,
    CONF_NOTIFY_EVENTS,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_TIME,
    CONF_SCAN_HOURS,
    CONF_SECRET,
    CONF_SUBDOMAIN,
    DOMAIN,
)

from .conftest import ENTRY_DATA, PAGE


@pytest.fixture
def no_setup():
    with patch("custom_components.findus_opac.async_setup_entry", return_value=True) as m:
        yield m


async def _start(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return result


async def test_user_success(hass, opac, no_setup):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kinder"
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == "musterstadt_12345678"
    login = opac.posts[0]
    assert (login["lesernr"], login["gebdat"], login["tsnowepoch"]) == (
        "12345678",
        "01.01.2000",
        "1793374248",
    )


async def test_user_full_url_is_normalized(hass, opac, no_setup):
    result = await _start(hass)
    url = "https://Musterstadt.findus-internet-opac.de/cgi-bin/findus.fcgi.pl?customer=musterstadt"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_SUBDOMAIN: url}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SUBDOMAIN] == "musterstadt"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("alzey", "alzey"),
        (" Alzey ", "alzey"),
        ("alzey.findus-internet-opac.de", "alzey"),
        ("https://alzey.findus-internet-opac.de/leserkonto", "alzey"),
        ("https://example.com/alzey", None),
        ("www.findus-internet-opac.de", None),
        ("", None),
        ("neu_wied", None),
    ],
)
def test_normalize_subdomain(value, expected):
    assert normalize_subdomain(value) == expected


async def test_user_invalid_subdomain(hass, opac):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_SUBDOMAIN: "https://example.com"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SUBDOMAIN: "invalid_subdomain"}
    assert opac.posts == []


async def test_user_invalid_auth_then_recover(hass, opac, no_setup):
    opac.reject_login()
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    opac.page = PAGE
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_cannot_connect(hass, opac):
    opac.fail_network()
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_already_configured(hass, opac, entry):
    entry.add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert opac.posts == []  # aborted before any login


async def test_reauth(hass, opac, loaded_entry):
    result = await loaded_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["account_name"] == "Kinder"

    opac.reject_login()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SECRET: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    opac.page = PAGE
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SECRET: " geheim "}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert loaded_entry.data[CONF_SECRET] == "geheim"
    assert opac.posts[-1]["gebdat"] == "geheim"  # reloaded with the new secret


async def test_options_flow_reloads(hass, opac, loaded_entry):
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_HOURS: 12, CONF_DUE_SOON_DAYS: 5}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options == {
        CONF_SCAN_HOURS: 12,
        CONF_DUE_SOON_DAYS: 5,
        CONF_AUTO_RENEW: False,
        CONF_AUTO_RENEW_DAYS: 2,
        CONF_AUTO_RENEW_CATEGORIES: [],
        CONF_NOTIFY_TARGETS: [],
        CONF_NOTIFY_TIME: "08:00:00",
        CONF_NOTIFY_EVENTS: ["due_soon", "due_today", "overdue", "last_chance", "renewed", "card_expiry"],
        "notify_show_titles": False,
    }
    coordinator = loaded_entry.runtime_data
    assert coordinator.update_interval == timedelta(hours=12)
    assert coordinator.due_soon_days == 5


async def test_options_flow_saves_auto_renew(hass, opac, loaded_entry):
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_HOURS: 6,
            CONF_DUE_SOON_DAYS: 3,
            CONF_AUTO_RENEW: True,
            CONF_AUTO_RENEW_DAYS: 4,
            CONF_AUTO_RENEW_CATEGORIES: ["tonie", "cd"],
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options[CONF_AUTO_RENEW] is True
    assert loaded_entry.options[CONF_AUTO_RENEW_DAYS] == 4
    assert loaded_entry.options[CONF_AUTO_RENEW_CATEGORIES] == ["tonie", "cd"]


async def test_options_flow_saves_notifications(hass, opac, loaded_entry):
    hass.services.async_register("notify", "mobile_app_phone", lambda call: None)
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    schema = result["data_schema"].schema
    targets_selector = next(v for k, v in schema.items() if k == CONF_NOTIFY_TARGETS)
    assert "mobile_app_phone" in targets_selector.config["options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_HOURS: 6,
            CONF_DUE_SOON_DAYS: 3,
            CONF_NOTIFY_TARGETS: ["mobile_app_phone"],
            CONF_NOTIFY_TIME: "07:30:00",
            CONF_NOTIFY_EVENTS: ["due_today"],
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options[CONF_NOTIFY_TARGETS] == ["mobile_app_phone"]
    assert loaded_entry.options[CONF_NOTIFY_TIME] == "07:30:00"
    assert loaded_entry.options[CONF_NOTIFY_EVENTS] == ["due_today"]
