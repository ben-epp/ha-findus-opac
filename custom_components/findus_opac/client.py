"""Findus Internet-OPAC client: parse the Leserkonto page, submit renewals.

Pure stdlib and transport-agnostic: the caller injects async `get(url) -> str`
and `post(url, data) -> str`, so this module has no Home Assistant dependency.
"""
from __future__ import annotations

import html as htmllib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

GetFn = Callable[[str], Awaitable[str]]
PostFn = Callable[[str, dict[str, str]], Awaitable[str]]

ROW_RE = re.compile(
    r"<!-- ausgeliehene_mednr = (?P<mednr>\w+) -->\s*"
    r'<tr class="(?:odd|even) verlaengerung_ist_moeglich_(?P<ok>ja|nein)">(?P<body>.*?)</tr>',
    re.S,
)
COVER_RE = re.compile(r'<img class="coverscan"[^>]*?src="(https://[^"]+)"')
HIDDEN_RE = re.compile(r'<input type="hidden" name="(\w+)" value="([^"]*)"')
FORM_RE = re.compile(r'<form method="POST"[^>]*>\s*(?:<input type="hidden"[^>]*>\s*)+', re.I)
LOGIN_MARKER = 'name="lesernr" type="text"'
ACCOUNT_MARKER = "findus_leserkonto_ausgeliehen_tabelle"
EMPTY_MARKER = "findus_leserkonto"


class FindusError(Exception):
    """Base error."""


class AuthError(FindusError):
    """Card number or birth date/password rejected."""


class ParseError(FindusError):
    """Page is neither a login form nor a recognizable account page."""


@dataclass
class Loan:
    mednr: str
    title: str
    author: str
    media_type: str
    due: date
    renewable: bool
    note: str = ""
    cover_url: str = ""
    series: str = ""

    @property
    def category(self) -> str:
        t = self.media_type.lower()
        if "tonie" in t:
            return "tonie"
        if re.search(r"\bcd\b", t) or "hörbuch" in t or "hoerbuch" in t or "musik" in t:
            return "cd"
        if "dvd" in t or "blu" in t or "film" in t or "video" in t:
            return "video"
        if "spiel" in t or "game" in t:
            return "game"
        return "book"

    def days_left(self, today: date) -> int:
        return (self.due - today).days


@dataclass
class Account:
    loans: list[Loan] = field(default_factory=list)
    form: dict[str, str] = field(default_factory=dict)
    card_valid_until: date | None = None

    def loan(self, mednr: str) -> Loan | None:
        return next((l for l in self.loans if l.mednr == mednr), None)


@dataclass
class RenewOutcome:
    """Per-item result. `renewed`: due date moved; `requested`: sent, not yet visible."""

    mednr: str
    title: str
    old_due: date
    new_due: date | None
    status: str  # "renewed" | "requested"


def _text(fragment: str) -> str:
    return htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _cell(body: str, cls: str) -> str:
    m = re.search(rf'<td class="{cls}">(.*?)</td>', body, re.S)
    return m.group(1) if m else ""


def _hint(cell: str) -> str:
    m = re.search(r'<span class="sortierhinweis">([^<]*)</span>', cell)
    return htmllib.unescape(m.group(1)).strip() if m else ""


def _renew_note(cell: str) -> str:
    """Why an item cannot be renewed: the <li> reasons, else the <p> headline."""
    reasons = [_text(li) for li in re.findall(r"<li>(.*?)</li>", cell, re.S)]
    if reasons:
        return " ".join(reasons)
    p = re.search(r"<p>(.*?)</p>", cell, re.S)
    return _text(p.group(1)) if p else ""


def _title(cell: str) -> tuple[str, str]:
    """(title, series). Series items carry two bold lines: series name, then volume title."""
    # Only the visible head of the cell: the hidden details/annotation block has its own
    # bold labels ("<b>Inhalt:</b>") that are not titles.
    cell = re.split(r'<span class="(?:standort_ueberschrift|details_hier)"|<div class="annotation_inline"', cell)[0]
    bold = [_text(b) for b in re.findall(r"<b>(.*?)</b>", cell, re.S)]
    bold = [b for b in bold if b]
    if not bold:
        return _hint(cell), ""
    if len(bold) == 1:
        return bold[0], ""
    series, part = bold[0], bold[1]
    # "Yakari" + "Yakari - Die Rache des Carcajou (Band 26)": the part already names the series
    title = part if part.lower().startswith(series.lower()) else f"{series} – {part}"
    return title, series


MONTHS = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11,
    "dezember": 12,
}
# "Ihr Ausweis ist gültig bis: 15. Juni 2027" (also "abgelaufen am/seit", or 15.06.2027)
CARD_RE = re.compile(
    r"Ausweis[^<]{0,40}?(?:bis|am|seit)\s*:?\s*(\d{1,2})\.\s*(?:([A-Za-zÄäÖöÜü]+)|(\d{1,2})\.)\s*(\d{4})"
)


def parse_card_valid_until(page: str) -> date | None:
    """Expiry date of the library card from the account banner, if shown."""
    m = CARD_RE.search(htmllib.unescape(page))
    if not m:
        return None
    day, month_name, month_num, year = m.groups()
    month = int(month_num) if month_num else MONTHS.get(month_name.lower())
    try:
        return date(int(year), month, int(day)) if month else None
    except ValueError:
        return None


def hidden_fields(page: str) -> dict[str, str]:
    """Hidden inputs of the first POST form on the page."""
    m = FORM_RE.search(page)
    return dict(HIDDEN_RE.findall(m.group(0))) if m else {}


def parse_account(page: str) -> Account:
    """Parse a logged-in Leserkonto page."""
    if LOGIN_MARKER in page:
        raise AuthError("login form returned")
    loans = []
    for m in ROW_RE.finditer(page):
        body = m["body"]
        title_cell = _cell(body, "spaltetitel")
        title, series = _title(title_cell)
        media_cell = _cell(body, "spaltemedienart")
        cover = COVER_RE.search(media_cell)
        renewable = m["ok"] == "ja"
        try:
            due = date.fromisoformat(_hint(_cell(body, "spalteausleihfrist")))
        except ValueError as err:
            raise ParseError(f"bad due date for {m['mednr']}") from err
        loans.append(
            Loan(
                mednr=m["mednr"],
                title=title,
                series=series,
                author=_hint(_cell(body, "spalteautor")),
                media_type=_hint(media_cell),
                due=due,
                renewable=renewable,
                note="" if renewable else _renew_note(_cell(body, "spalteverlaengerung")),
                cover_url=htmllib.unescape(cover.group(1)) if cover else "",
            )
        )
    if not loans and ACCOUNT_MARKER not in page and EMPTY_MARKER not in page:
        raise ParseError("no account content")
    return Account(
        loans=loans,
        form=hidden_fields(page) if loans else {},
        card_valid_until=parse_card_valid_until(page),
    )


class FindusClient:
    def __init__(self, subdomain: str, card: str, secret: str, get: GetFn, post: PostFn) -> None:
        self.subdomain = subdomain
        self.url = f"https://{subdomain}.findus-internet-opac.de/cgi-bin/findus.fcgi.pl"
        self._card, self._secret, self._get, self._post = card, secret, get, post

    @property
    def login_url(self) -> str:
        return f"{self.url}?customer={self.subdomain}&leserkonto=1&submit=1"

    async def fetch(self) -> Account:
        """Log in and return the account. Each call is a fresh login; Findus is stateless."""
        form = hidden_fields(await self._get(self.login_url))
        form.update(
            {
                "customer": self.subdomain,
                "leserkonto": "1",
                "submit": "1",
                "lesernr": self._card,
                "gebdat": self._secret,
            }
        )
        return parse_account(await self._post(self.url, form))

    async def renew(self, mednrs: list[str] | None = None) -> tuple[Account, list[RenewOutcome]]:
        """Renew the given items (default: all renewable). Non-renewable ids are skipped.

        Findus calls this a "Verlängerungsantrag": the library system may only apply it
        on its next sync, so an unchanged due date is reported as "requested", not failed.
        """
        before = await self.fetch()
        wanted = set(mednrs) if mednrs else None
        targets = [l for l in before.loans if l.renewable and (wanted is None or l.mednr in wanted)]
        if not targets:
            return before, []
        data = {**before.form, "submit": " "}
        data.update({f"verlaengere_nr_{l.mednr}": "1" for l in targets})
        page = await self._post(self.url, data)
        try:
            after = parse_account(page)
        except ParseError:
            after = Account()
        if not after.loans:  # confirmation page instead of the account: reload it
            after = await self.fetch()
        outcomes = []
        for old in targets:
            new = after.loan(old.mednr)
            moved = new is not None and new.due > old.due
            outcomes.append(
                RenewOutcome(
                    mednr=old.mednr,
                    title=old.title,
                    old_due=old.due,
                    new_due=new.due if new else None,
                    status="renewed" if moved else "requested",
                )
            )
        return after, outcomes
