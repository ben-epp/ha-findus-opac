"""Simulate what Findus serves after a renewal request (structure from a real response)."""
from __future__ import annotations

import re

BANNER = '<div class="alert alert-success" role="alert">OK, Verl&auml;ngerungsantrag wurde gestellt...</div>\n'
REQUESTED_CELL = """<td class="spalteverlaengerung">
    <span class="sortierhinweis">20 = verlaengerung schon beantragt</span>
    <p>Sie haben erst eine Verl&auml;ngerung beantragt.</p>
          <ul>
              <li>Verl&auml;ngerung wurde beantragt am 31.10.2026 2:39 Uhr</li>
          </ul>
                </td>"""


def requested(page: str, mednrs: list[str]) -> str:
    """Account page after a Verlängerungsantrag: banner, rows marked as requested."""
    for mednr in mednrs:
        page = re.sub(
            rf'(<!-- ausgeliehene_mednr = {mednr} -->\s*<tr class="(?:odd|even)) verlaengerung_ist_moeglich_ja">'
            r'(.*?)<td class="spalteverlaengerung">.*?</td>',
            lambda m: f'{m[1]} leserkonto_verlaengerung_wurde_schon_beantragt_zelle">{m[2]}{REQUESTED_CELL}',
            page,
            count=1,
            flags=re.S,
        )
    return page.replace("<body>", "<body>\n" + BANNER, 1) if mednrs else page


def renewal_ids(data: dict[str, str]) -> list[str]:
    """Item numbers ticked in a renewal POST (empty for a login POST)."""
    return [k.removeprefix("verlaengere_nr_") for k in data if k.startswith("verlaengere_nr_")]
