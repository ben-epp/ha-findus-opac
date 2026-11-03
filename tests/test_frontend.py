"""Bundled Lovelace card registration and brand images."""
from __future__ import annotations

from pathlib import Path
import struct
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.lovelace.const import LOVELACE_DATA

from custom_components.findus_opac import _async_ensure_lovelace_resource, _async_register_card
from custom_components.findus_opac.const import CARD_VERSION

URL = f"/findus_opac/findus-opac-card.js?v={CARD_VERSION}"

COMPONENT = Path(__file__).parent.parent / "custom_components" / "findus_opac"


async def test_card_registered_when_frontend_loaded(hass):
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    hass.config.components.add("frontend")
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_js:
        await _async_register_card(hass)
    (configs,), _ = hass.http.async_register_static_paths.call_args
    assert configs[0].url_path == "/findus_opac/findus-opac-card.js"
    assert Path(configs[0].path).is_file()
    add_js.assert_called_once()
    assert add_js.call_args.args[1] == URL


async def test_card_skipped_without_frontend(hass):
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    assert "frontend" not in hass.config.components
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_js:
        await _async_register_card(hass)
    hass.http.async_register_static_paths.assert_not_called()
    add_js.assert_not_called()


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def test_brand_icons():
    assert _png_size(COMPONENT / "brand" / "icon.png") == (256, 256)
    assert _png_size(COMPONENT / "brand" / "icon@2x.png") == (512, 512)


class FakeResources:
    """Stand-in for lovelace's ResourceStorageCollection."""

    def __init__(self, items=None):
        self.loaded = False
        self.items = [dict(i) for i in items or []]
        self.created, self.updated = [], []

    async def async_load(self):
        pass

    def async_items(self):
        return self.items

    async def async_create_item(self, data):
        self.created.append(data)

    async def async_update_item(self, item_id, data):
        self.updated.append((item_id, data))


def _lovelace(hass, resources, mode="storage"):
    hass.data[LOVELACE_DATA] = MagicMock(resource_mode=mode, resources=resources)


async def test_resource_created_in_storage_mode(hass):
    res = FakeResources([{"id": "x", "url": "/local/other.js", "type": "module"}])
    _lovelace(hass, res)
    await _async_ensure_lovelace_resource(hass, URL)
    assert res.loaded
    assert res.created == [{"res_type": "module", "url": URL}]


async def test_resource_url_updated_on_new_version(hass):
    res = FakeResources([{"id": "r1", "url": "/findus_opac/findus-opac-card.js?v=0.3.0"}])
    _lovelace(hass, res)
    await _async_ensure_lovelace_resource(hass, URL)
    assert res.created == []
    assert res.updated == [("r1", {"res_type": "module", "url": URL})]


async def test_resource_unchanged_when_current(hass):
    res = FakeResources([{"id": "r1", "url": URL}])
    _lovelace(hass, res)
    await _async_ensure_lovelace_resource(hass, URL)
    assert res.created == [] and res.updated == []


async def test_resource_skipped_in_yaml_mode_or_without_lovelace(hass):
    await _async_ensure_lovelace_resource(hass, URL)  # lovelace not loaded: no error
    res = FakeResources()
    _lovelace(hass, res, mode="yaml")
    await _async_ensure_lovelace_resource(hass, URL)
    assert res.created == [] and res.updated == []


async def test_resource_failure_does_not_break_registration(hass, caplog):
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    hass.config.components.add("frontend")
    res = FakeResources()
    res.async_create_item = AsyncMock(side_effect=RuntimeError("boom"))
    _lovelace(hass, res)
    with patch("homeassistant.components.frontend.add_extra_js_url"):
        await _async_register_card(hass)
    assert "Could not register the Findus card as dashboard resource" in caplog.text


async def test_resource_with_real_lovelace(hass, hass_storage):
    """Create once, update on version bump, never duplicate - against HA's own collection."""
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})
    old = "/findus_opac/findus-opac-card.js?v=0.3.0"
    await _async_ensure_lovelace_resource(hass, old)
    await _async_ensure_lovelace_resource(hass, URL)
    await _async_ensure_lovelace_resource(hass, URL)
    items = hass.data[LOVELACE_DATA].resources.async_items()
    assert [(i["url"], i["type"]) for i in items] == [(URL, "module")]


def test_card_version_matches_js():
    """CARD_VERSION busts the browser cache; a stale one hides card changes."""
    js = (COMPONENT / "frontend" / "findus-opac-card.js").read_text()
    assert f'const CARD_VERSION = "{CARD_VERSION}";' in js
