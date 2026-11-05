"""Setup, unload, auth failure and diagnostics."""
from __future__ import annotations

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState

from custom_components.findus_opac.const import (
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_TIME,
    DOMAIN,
)
from custom_components.findus_opac.diagnostics import async_get_config_entry_diagnostics

from .conftest import CARD, SECRET


async def test_setup_and_unload(hass, opac, loaded_entry):
    assert loaded_entry.state is ConfigEntryState.LOADED
    assert len(loaded_entry.runtime_data.data.loans) == 5
    assert hass.services.has_service(DOMAIN, "renew")

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    await hass.async_block_till_done()
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED


async def test_auth_failure_starts_reauth(hass, opac, entry):
    opac.reject_login()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_network_failure_retries(hass, opac, entry):
    opac.fail_network()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_diagnostics_redacts_credentials(hass, opac, loaded_entry):
    diag = await async_get_config_entry_diagnostics(hass, loaded_entry)
    text = repr(diag)
    assert CARD not in text and SECRET not in text
    assert "2000-01-01" not in text  # birth date echoed in the renewal form
    assert diag["entry"]["data"]["card"] == "**REDACTED**"
    assert diag["entry"]["data"]["secret"] == "**REDACTED**"
    assert len(diag["loans"]) == 5
    assert "formburnerid" in diag["form_keys"]


async def test_diagnostics_redacts_names(hass, opac, loaded_entry):
    """Account names and notify targets (mobile_app_lenas_iphone) identify people."""
    hass.config_entries.async_update_entry(
        loaded_entry,
        options={CONF_NOTIFY_TARGETS: ["mobile_app_lenas_iphone"], CONF_NOTIFY_TIME: "08:00:00"},
    )
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, loaded_entry)
    entry_text = repr(diag["entry"])  # media types in the loans also contain "Kinder"
    assert "Kinder" not in entry_text and "lenas_iphone" not in entry_text
    assert diag["entry"]["data"]["account_name"] == "**REDACTED**"
    assert diag["entry"]["options"][CONF_NOTIFY_TARGETS] == "**REDACTED**"
    assert diag["entry"]["options"][CONF_NOTIFY_TIME] == "08:00:00"  # still useful for support


async def test_diagnostics_omits_titles(hass, opac, loaded_entry):
    diag = await async_get_config_entry_diagnostics(hass, loaded_entry)
    assert diag["loans"] and all("title" not in loan for loan in diag["loans"])
    assert "Der kleine Drache" not in repr(diag)


async def test_loan_titles_are_not_recorded(hass, opac, loaded_entry):
    states = [s for s in hass.states.async_all("sensor") if "items" in s.attributes]
    assert states
    for state in states:
        assert "items" in state.state_info["unrecorded_attributes"]
