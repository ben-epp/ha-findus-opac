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
from urllib.parse import urljoin

GetFn = Callable[[str], Awaitable[str]]
PostFn = Callable[[str, dict[str, str]], Awaitable[str]]

ROW_RE = re.compile(
    r"<!-- ausgeliehene_mednr = (?P<mednr>\w+) -->\s*"
    r'<tr class="(?:odd|even)(?: (?P<state>[\w ]*))?">(?P<body>.*?)</tr>',
    re.S,
)
RENEWABLE_STATE = "verlaengerung_ist_moeglich_ja"
REQUESTED_STATE = "verlaengerung_wurde_schon_beantragt"  # e.g. leserkonto_..._zelle
RENEW_OK_RE = re.compile(r'class="alert alert-success"[^>]*>\s*OK, Verl(?:&auml;|ä)ngerungsantrag')
COVER_RE = re.compile(r'<img class="coverscan"[^>]*?src="(https://[^"]+)"')
HIDDEN_RE = re.compile(r'<input type="hidden" name="(\w+)" value="([^"]*)"')
FORM_RE = re.compile(r'<form method="POST"[^>]*>\s*(?:<input type="hidden"[^>]*>\s*)+', re.I)
NOTICE_OPEN_RE = re.compile(r'<div id="veranstaltungshinweis"[^>]*>', re.I)
DIV_TAG_RE = re.compile(r"<(/?)div\b", re.I)
NOTICE_TITLE_RE = re.compile(r"<h[12][^>]*>(.*?)</h[12]>", re.S | re.I)
# Keyword guess, tuned on ~115 real notices: whole words only ("anschließend" is no closure),
# and "bleibt ... offen" / "nicht geschlossen" cancel it. Only the start of the text is read.
CLOSURE_RE = re.compile(
    r"geschlossen|\bschlie(?:ß|ss)(?:ung|en)\b|bleibt[^\n]{0,40}\bzu\b|betriebsferien|betriebsruhe|\burlaub\b",
    re.I,
)
NOT_CLOSED_RE = re.compile(r"(?:nicht|nie|kein\w*)\s+(?:\w+\s+)?geschlossen|bleibt[^\n]{0,40}\boffen\b", re.I)
KIND_WINDOW = 400
NOTICE_MAX_CHARS = 2000
NOTICE_MAX_IMAGES = 3
IMG_SRC_RE = re.compile(r'<img[^>]*?\ssrc=["\']([^"\']+)["\']', re.I)
LOGIN_MARKER = 'name="lesernr" type="text"'
ACCOUNT_MARKER = "findus_leserkonto_ausgeliehen_tabelle"
EMPTY_MARKER = "findus_leserkonto"
# Why Findus refuses a renewal, from its reason text (see Loan.renew_block).
RENEW_BLOCKS = (
    ("limit", re.compile(r"maximale anzahl|h(?:ö|oe)chst(?:zahl|anzahl)", re.I)),
    ("reserved", re.compile(r"vorbestellt|reserviert", re.I)),
    ("too_early", re.compile(r"noch nicht|erst \d+ tage", re.I)),
)


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
    renew_requested: bool = False  # Verlängerungsantrag pending until the next library sync

    @property
    def renew_block(self) -> str:
        """Why it cannot be renewed: limit / reserved / too_early / other.

        Empty if renewable, already requested, or Findus gave no reason text.
        """
        if self.renewable or self.renew_requested or not self.note:
            return ""
        return next((key for key, rx in RENEW_BLOCKS if rx.search(self.note)), "other")

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
class Announcement:
    """Free-text library notice ("Veranstaltungshinweis"); `kind` is a keyword guess."""

    title: str
    text: str  # plain text, paragraphs separated by a blank line, capped
    kind: str  # "closure" | "info"
    truncated: bool = False  # text was cut at NOTICE_MAX_CHARS; `url` has the full notice
    url: str = ""  # library's OPAC homepage, where the notice is shown in full
    images: list[str] = field(default_factory=list)  # absolute http(s) URLs, at most NOTICE_MAX_IMAGES


@dataclass
class Account:
    loans: list[Loan] = field(default_factory=list)
    form: dict[str, str] = field(default_factory=dict)
    card_valid_until: date | None = None
    announcement: Announcement | None = None

    def loan(self, mednr: str) -> Loan | None:
        return next((l for l in self.loans if l.mednr == mednr), None)


@dataclass
class RenewOutcome:
    """Per-item result. `renewed`: due date moved; `requested`: sent, not yet visible."""

    mednr: str
    title: str
    old_due: date
    new_due: date | None
    status: str  # "renewed" | "requested" | "failed"


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


def parse_announcement(page: str) -> Announcement | None:
    """The library's notice box, if the page carries one. Free text, so `kind` is a guess."""
    opening = NOTICE_OPEN_RE.search(page)
    if not opening:
        return None
    raw, depth = page[opening.end() :], 1  # inner HTML up to the matching </div>
    for tag in DIV_TAG_RE.finditer(raw):
        depth += -1 if tag[1] else 1
        if depth == 0:
            raw = raw[: tag.start()]
            break
    images = [htmllib.unescape(u) for u in IMG_SRC_RE.findall(raw)]
    body = re.sub(r"<img[^>]*>|<br[^>]*>", " ", raw, flags=re.I)
    t = NOTICE_TITLE_RE.search(body)
    title = _text(t.group(1)) if t else ""
    rest = body[t.end() :] if t else body
    paragraphs = [p for p in (_text(x) for x in re.split(r"</p>|</div>|<hr[^>]*>", rest, flags=re.I)) if p]
    text = "\n\n".join(paragraphs)
    if not title and not text:
        return None
    head = f"{title} {text[:KIND_WINDOW]}"
    kind = "closure" if CLOSURE_RE.search(head) and not NOT_CLOSED_RE.search(head) else "info"
    truncated = len(text) > NOTICE_MAX_CHARS
    if truncated:
        text = text[: NOTICE_MAX_CHARS - 1].rstrip() + "…"
    return Announcement(
        title=(title or paragraphs[0])[:255],
        text=text,
        kind=kind,
        truncated=truncated,
        images=images,
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
        state = m["state"] or ""
        renewable = RENEWABLE_STATE in state
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
                renew_requested=REQUESTED_STATE in state,
            )
        )
    if not loans and ACCOUNT_MARKER not in page and EMPTY_MARKER not in page:
        raise ParseError("no account content")
    return Account(
        loans=loans,
        form=hidden_fields(page) if loans else {},
        card_valid_until=parse_card_valid_until(page),
        announcement=parse_announcement(page),
    )


class FindusClient:
    def __init__(self, subdomain: str, card: str, secret: str, get: GetFn, post: PostFn) -> None:
        self.subdomain = subdomain
        self.url = f"https://{subdomain}.findus-internet-opac.de/cgi-bin/findus.fcgi.pl"
        self._card, self._secret, self._get, self._post = card, secret, get, post

    @property
    def home_url(self) -> str:
        return f"{self.url}?customer={self.subdomain}"

    def _announce(self, account: Account, *fallbacks: Announcement | None) -> None:
        """Set the notice (first non-empty of the account's own and the fallbacks) with its link."""
        account.announcement = next((a for a in (account.announcement, *fallbacks) if a), None)
        if note := account.announcement:
            note.url = self.home_url
            urls = (urljoin(self.url, u) for u in note.images)  # relative srcs -> absolute
            # https only: plain http would expose the browser's request on the network.
            note.images = [u for u in urls if u.startswith("https://")][:NOTICE_MAX_IMAGES]

    @property
    def login_url(self) -> str:
        return f"{self.url}?customer={self.subdomain}&leserkonto=1&submit=1"

    async def fetch(self) -> Account:
        """Log in and return the account. Each call is a fresh login; Findus is stateless."""
        login_page = await self._get(self.login_url)
        form = hidden_fields(login_page)
        form.update(
            {
                "customer": self.subdomain,
                "leserkonto": "1",
                "submit": "1",
                "lesernr": self._card,
                "gebdat": self._secret,
            }
        )
        account = parse_account(await self._post(self.url, form))
        # The notice is on every page; prefer the account page's, else the login page's.
        self._announce(account, parse_announcement(login_page))
        return account

    async def renew(self, mednrs: list[str] | None = None) -> tuple[Account, list[RenewOutcome]]:
        """Renew the given items (default: all renewable). Non-renewable ids are skipped.

        Findus calls this a "Verlängerungsantrag": the library system may only apply it
        on its next sync. The account page then marks the row as requested and the due
        date stays unchanged until then; such items are reported as "requested". Items that
        are neither moved nor marked (and no success banner) are reported as "failed".
        """
        before = await self.fetch()
        wanted = set(mednrs) if mednrs else None
        targets = [l for l in before.loans if l.renewable and (wanted is None or l.mednr in wanted)]
        if not targets:
            return before, []
        data = {**before.form, "submit": " "}
        data.update({f"verlaengere_nr_{l.mednr}": "1" for l in targets})
        page = await self._post(self.url, data)
        accepted = bool(RENEW_OK_RE.search(page))
        try:
            after = parse_account(page)
        except ParseError:
            after = Account()
        if not after.loans:  # confirmation page instead of the account: reload it
            after = await self.fetch()
        outcomes = []
        for old in targets:
            new = after.loan(old.mednr)
            if new is not None and new.due > old.due:
                status = "renewed"
            elif (new is not None and new.renew_requested) or (new is None and accepted):
                status = "requested"
            else:
                status = "failed"
            outcomes.append(
                RenewOutcome(
                    mednr=old.mednr,
                    title=old.title,
                    old_due=old.due,
                    new_due=new.due if new else None,
                    status=status,
                )
            )
        self._announce(after, before.announcement)
        return after, outcomes
