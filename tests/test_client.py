from datetime import date
from pathlib import Path

import pytest

from custom_components.findus_opac.client import (
    AuthError,
    FindusClient,
    ParseError,
    parse_account,
    parse_card_valid_until,
)

# Synthetic page: real Findus markup structure, invented data.
PAGE = (Path(__file__).parent / "fixtures" / "konto_musterstadt.html").read_text()
LOGIN_PAGE = (
    '<form method="POST" action="">\n'
    '<input type="hidden" name="customer" value="musterstadt">\n'
    '<input type="hidden" name="leserkonto" value="1">\n'
    '<input type="hidden" name="tsnowepoch" value="1793374248">\n'
    '<input type="hidden" name="submit" value="1">\n'
    '<input name="lesernr" type="text" class="form-control">'
)


class FakeOpac:
    """Records requests; serves the login page on GET and `pages` (in order) on POST."""

    def __init__(self, *pages: str) -> None:
        self.pages = list(pages) or [PAGE]
        self.gets: list[str] = []
        self.posts: list[dict[str, str]] = []

    async def get(self, url: str) -> str:
        self.gets.append(url)
        return LOGIN_PAGE

    async def post(self, url: str, data: dict[str, str]) -> str:
        self.posts.append(data)
        return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]

    def client(self) -> FindusClient:
        return FindusClient("musterstadt", "1", "2", self.get, self.post)


def test_parse_loans():
    acc = parse_account(PAGE)
    assert len(acc.loans) == 5
    assert [l.category for l in acc.loans] == ["tonie", "cd", "book", "book", "video"]
    first = acc.loans[0]
    assert (first.title, first.author, first.due) == (
        "Der kleine Drache",
        "Musterfrau, Erika",
        date(2026, 11, 6),
    )
    assert acc.loans[3].title == "Wieso? Weshalb? Warum? – Wale & Delfine"
    assert acc.loans[4].author == ""
    assert [l.renewable for l in acc.loans] == [True, True, False, False, False]
    assert acc.form["verlaengerungsantrag"] == "1" and acc.form["formburnerid"]


def test_series_titles():
    acc = parse_account(PAGE)
    # Volume title already names the series ("Yakari" / "Yakari - ... (Band 26)" on real pages)
    assert (acc.loans[2].title, acc.loans[2].series) == (
        "Waldbande - Abenteuer im Wald (Band 3)",
        "Waldbande",
    )
    # Volume title without the series name gets it prefixed
    assert (acc.loans[3].title, acc.loans[3].series) == (
        "Wieso? Weshalb? Warum? – Wale & Delfine",
        "Wieso? Weshalb? Warum?",
    )
    assert (acc.loans[0].title, acc.loans[0].series) == ("Der kleine Drache", "")


def test_card_valid_until():
    assert parse_account(PAGE).card_valid_until == date(2026, 12, 1)


@pytest.mark.parametrize(
    ("banner", "expected"),
    [
        ("Ihr Ausweis ist g&uuml;ltig bis: 15. Juni 2027", date(2027, 6, 15)),
        ("Ihr Ausweis ist gültig bis: 1. März 2027", date(2027, 3, 1)),
        ("Ihr Ausweis ist abgelaufen seit: 15.06.2025", date(2025, 6, 15)),
        ("Ihr Ausweis ist gültig bis: 31. Februar 2027", None),
        ("<div>Willkommen</div>", None),
    ],
)
def test_card_valid_until_variants(banner, expected):
    assert parse_card_valid_until(banner) == expected


def test_cover_urls():
    acc = parse_account(PAGE)
    assert acc.loans[0].cover_url == (
        "https://mycover.findus-internet-opac.de/cover/musterstadt/90/4000000000017.jpg"
    )
    assert acc.loans[2].cover_url.endswith("/isbn/9780000000002")
    assert acc.loans[3].cover_url == ""  # item without a cover


def test_notes_are_cleaned():
    acc = parse_account(PAGE)
    assert acc.loans[0].note == ""
    assert acc.loans[2].note.startswith("Verlängerung ist noch nicht möglich")
    assert "sortierhinweis" not in acc.loans[2].note and "10 =" not in acc.loans[2].note
    assert acc.loans[3].note == "Das Medium ist vorbestellt."


def test_days_left():
    assert parse_account(PAGE).loans[0].days_left(date(2026, 10, 30)) == 7


def test_login_form_is_auth_error():
    with pytest.raises(AuthError):
        parse_account(LOGIN_PAGE)


def test_garbage_is_parse_error():
    with pytest.raises(ParseError):
        parse_account("<html><body>Wartungsarbeiten</body></html>")


async def test_fetch_sends_login_hidden_fields():
    opac = FakeOpac()
    acc = await opac.client().fetch()
    assert len(acc.loans) == 5
    assert opac.gets == [
        "https://musterstadt.findus-internet-opac.de/cgi-bin/findus.fcgi.pl"
        "?customer=musterstadt&leserkonto=1&submit=1"
    ]
    login = opac.posts[0]
    assert login["tsnowepoch"] == "1793374248"
    assert (login["lesernr"], login["gebdat"], login["customer"]) == ("1", "2", "musterstadt")


async def test_renew_posts_only_renewable():
    opac = FakeOpac()
    _, outcomes = await opac.client().renew()
    renew = opac.posts[-1]
    keys = sorted(k for k in renew if k.startswith("verlaengere_nr_"))
    assert keys == ["verlaengere_nr_0900000101", "verlaengere_nr_0900000102"]
    assert renew["verlaengerungsantrag"] == "1"
    assert renew["gebdat"] == "2000-01-01"
    # Same page back: due dates unchanged -> reported as requested, not failed.
    assert [(o.mednr, o.status) for o in outcomes] == [
        ("0900000101", "requested"),
        ("0900000102", "requested"),
    ]


async def test_renew_detects_moved_due_date():
    renewed = PAGE.replace(
        '<span class="sortierhinweis">2026-11-06</span>',
        '<span class="sortierhinweis">2026-12-04</span>',
    )
    opac = FakeOpac(PAGE, renewed)
    _, outcomes = await opac.client().renew(["0900000101"])
    assert len(outcomes) == 1
    o = outcomes[0]
    assert (o.status, o.old_due, o.new_due) == ("renewed", date(2026, 11, 6), date(2026, 12, 4))


async def test_renew_confirmation_page_triggers_reload():
    opac = FakeOpac(PAGE, "<html><p>Ihr Antrag wurde gespeichert.</p></html>", PAGE)
    account, outcomes = await opac.client().renew(["0900000102"])
    assert len(account.loans) == 5
    assert len(opac.posts) == 3  # login, renew, reload login
    assert outcomes[0].status == "requested"


async def test_renew_ignores_non_renewable_ids():
    opac = FakeOpac()
    _, outcomes = await opac.client().renew(["0900000103"])
    assert outcomes == []
    assert len(opac.posts) == 1  # only the login, no renewal POST
