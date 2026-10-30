"""Bundled Lovelace card registration and brand images."""
from __future__ import annotations

from pathlib import Path
import struct
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.findus_opac import _async_register_card

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
    assert add_js.call_args.args[1] == "/findus_opac/findus-opac-card.js?v=0.3.0"


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
