"""Shared fixtures: a fake Findus OPAC behind aioclient_mock, and a config entry."""
from __future__ import annotations

from pathlib import Path

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.findus_opac.const import (
    CONF_ACCOUNT_NAME,
    CONF_CARD,
    CONF_SECRET,
    CONF_SUBDOMAIN,
    DOMAIN,
)

from .pages import renewal_ids, requested

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "konto_musterstadt.html").read_text()
BASE_URL = "https://musterstadt.findus-internet-opac.de/cgi-bin/findus.fcgi.pl"
LOGIN_URL = f"{BASE_URL}?customer=musterstadt&leserkonto=1&submit=1"
LOGIN_PAGE = (
    '<form method="POST" action="">\n'
    '<input type="hidden" name="customer" value="musterstadt">\n'
    '<input type="hidden" name="leserkonto" value="1">\n'
    '<input type="hidden" name="tsnowepoch" value="1793374248">\n'
    '<input type="hidden" name="submit" value="1">\n'
    '<input name="lesernr" type="text" class="form-control">\n'
    "</form>"
)
CARD = "12345678"
SECRET = "01.01.2000"
ENTRY_DATA = {
    CONF_ACCOUNT_NAME: "Kinder",
    CONF_SUBDOMAIN: "musterstadt",
    CONF_CARD: CARD,
    CONF_SECRET: SECRET,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    yield


class FakeOpac:
    """Serves the login page on GET; POSTs pop `queue`, then fall back to `page`."""

    def __init__(self, mock: AiohttpClientMocker) -> None:
        self.mock = mock
        self.page = PAGE
        self.queue: list[str] = []
        self.exc: Exception | None = None
        mock.get(LOGIN_URL, text=LOGIN_PAGE)
        mock.post(BASE_URL, side_effect=self._post)

    async def _post(self, method, url, data) -> AiohttpClientMockResponse:
        if self.exc is not None:
            return AiohttpClientMockResponse(method, url, exc=self.exc)
        if self.queue:
            text = self.queue.pop(0)
        else:  # behave like Findus: a renewal POST marks the ticked rows as requested
            text = requested(self.page, renewal_ids(data or {}))
        return AiohttpClientMockResponse(method, url, text=text)

    def reject_login(self) -> None:
        self.page = LOGIN_PAGE

    def fail_network(self) -> None:
        self.exc = aiohttp.ClientError("boom")

    @property
    def gets(self) -> int:
        return sum(1 for c in self.mock.mock_calls if c[0].lower() == "get")

    @property
    def posts(self) -> list[dict]:
        return [c[2] for c in self.mock.mock_calls if c[0].lower() == "post"]


@pytest.fixture
def opac(aioclient_mock: AiohttpClientMocker) -> FakeOpac:
    return FakeOpac(aioclient_mock)


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kinder",
        data=dict(ENTRY_DATA),
        unique_id=f"musterstadt_{CARD}",
    )


@pytest.fixture
async def loaded_entry(hass, opac, entry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
