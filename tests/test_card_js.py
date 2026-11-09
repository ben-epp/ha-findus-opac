"""Run the card's JavaScript render tests (tests/card.test.mjs) with Node."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

TESTS = Path(__file__).parent / "card.test.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_card_render():
    result = subprocess.run(
        ["node", "--test", str(TESTS)], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
