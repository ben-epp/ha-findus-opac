"""The renewal request record: pending window, auto-renew targets, stored state."""
from __future__ import annotations

from datetime import date, time, timedelta

from custom_components.findus_opac.client import (
    Account,
    DayHours,
    Loan,
    OpeningHours,
    RenewOutcome,
)
from custom_components.findus_opac.renewal_requests import (
    AutoRenewRule,
    RenewalRequests,
    pending_until,
)

TODAY = date(2026, 11, 6)  # a Friday
DUE = date(2026, 11, 10)


class FakeStore:
    """Stands in for Store: hands out the loaded data and records every save."""

    def __init__(self, data: dict[str, dict[str, str]] | None = None) -> None:
        self.data = data
        self.saved: list[dict[str, dict[str, str]]] = []

    async def async_load(self) -> dict[str, dict[str, str]] | None:
        return self.data

    async def async_save(self, data: dict[str, dict[str, str]]) -> None:
        self.saved.append(data)


def _loan(
    mednr: str = "1",
    due: date = DUE,
    renewable: bool = True,
    renew_requested: bool = False,
    media_type: str = "Roman",
) -> Loan:
    return Loan(
        mednr=mednr,
        title=f"Titel {mednr}",
        author="",
        media_type=media_type,
        due=due,
        renewable=renewable,
        renew_requested=renew_requested,
    )


def _account(*loans: Loan) -> Account:
    return Account(loans=list(loans))


def _outcome(mednr: str, due: date, status: str) -> RenewOutcome:
    return RenewOutcome(mednr=mednr, title="Titel", old_due=due, new_due=None, status=status)


def _hours() -> OpeningHours:
    """Monday and Wednesday open, Thursday conditional, everything else closed."""
    return OpeningHours(
        days={
            0: DayHours(intervals=((time(10), time(12)),)),
            2: DayHours(intervals=((time(10), time(12)),)),
            3: DayHours(conditional=True),
        }
    )


def test_requested_outcome_makes_the_loan_pending():
    requests = RenewalRequests(FakeStore())
    requests.record([_outcome("1", DUE, "requested")], TODAY)
    loan = requests.mark(_account(_loan()), TODAY, None).loans[0]
    assert (loan.renewable, loan.renew_requested, loan.renew_requested_on) == (False, True, TODAY)


def test_pending_window_with_hours_ends_on_the_second_open_day():
    hours = _hours()
    # Saturday and Sunday closed, Tuesday closed: Friday -> Monday (1st), Wednesday (2nd).
    assert pending_until(date(2026, 11, 6), hours) == date(2026, 11, 11)
    # Wednesday is the 1st open day, the conditional Thursday the 2nd.
    assert pending_until(date(2026, 11, 9), hours) == date(2026, 11, 12)
    # No open day within the horizon: the calendar fallback still applies.
    assert pending_until(date(2026, 11, 6), OpeningHours(days={})) == date(2026, 11, 9)

    requests = RenewalRequests(FakeStore())
    requests.record([_outcome("1", DUE, "requested")], date(2026, 11, 6))
    pending = requests.mark(_account(_loan()), date(2026, 11, 11), hours).loans[0]
    assert pending.renew_requested is True
    done = requests.mark(_account(_loan()), date(2026, 11, 12), hours).loans[0]
    assert (done.renewable, done.renew_requested) == (True, False)


def test_without_hours_the_window_is_three_calendar_days():
    requests = RenewalRequests(FakeStore())
    requests.record([_outcome("1", DUE, "requested")], TODAY)
    last_day = requests.mark(_account(_loan()), date(2026, 11, 9), None).loans[0]
    assert (last_day.renewable, last_day.renew_requested) == (False, True)
    after = requests.mark(_account(_loan()), date(2026, 11, 10), None).loans[0]
    assert (after.renewable, after.renew_requested, after.renew_requested_on) == (True, False, None)


async def test_record_is_dropped_when_the_due_date_moves_or_the_loan_is_gone():
    store = FakeStore()
    requests = RenewalRequests(store)
    requests.record([_outcome("1", DUE, "requested")], TODAY)
    requests.mark(_account(_loan(due=date(2026, 12, 4))), TODAY, None)
    await requests.async_save()
    assert store.saved[-1] == {}

    requests.record([_outcome("1", DUE, "requested")], TODAY)
    requests.mark(_account(), TODAY, None)
    await requests.async_save()
    assert store.saved[-1] == {}


async def test_request_made_on_the_website_is_adopted():
    store = FakeStore()
    requests = RenewalRequests(store)
    loan = _loan(renewable=False, renew_requested=True)
    marked = requests.mark(_account(loan), TODAY, None).loans[0]
    assert (marked.renewable, marked.renew_requested, marked.renew_requested_on) == (
        False,
        True,
        TODAY,
    )
    await requests.async_save()
    assert store.saved == [{"1": {"due": DUE.isoformat(), "sent": TODAY.isoformat()}}]


def test_the_librarys_reason_wins_over_the_record():
    requests = RenewalRequests(FakeStore())
    requests.record([_outcome("1", DUE, "requested")], TODAY)
    loan = _loan(renewable=False)
    loan.note = "Vorbestellt"
    marked = requests.mark(_account(loan), TODAY, None).loans[0]
    assert marked is loan
    assert (loan.renewable, loan.renew_requested, loan.renew_requested_on) == (False, False, None)


def test_mark_does_not_mutate_the_input_account():
    requests = RenewalRequests(FakeStore())
    requests.record([_outcome("1", DUE, "requested")], TODAY)
    loan = _loan()
    account = _account(loan)
    marked = requests.mark(account, TODAY, None)
    assert marked is not account
    assert marked.loans is not account.loans
    assert marked.loans[0] is not loan
    assert (loan.renewable, loan.renew_requested, loan.renew_requested_on) == (True, False, None)


def test_auto_targets_are_empty_when_disabled():
    requests = RenewalRequests(FakeStore())
    rule = AutoRenewRule(enabled=False, days=2, categories=frozenset())
    assert requests.auto_targets(_account(_loan(due=DUE - timedelta(days=2))), TODAY, rule) == []


def test_auto_targets_respect_the_days_window():
    requests = RenewalRequests(FakeStore())
    rule = AutoRenewRule(enabled=True, days=2, categories=frozenset())
    account = _account(
        _loan("1", due=TODAY + timedelta(days=2)),
        _loan("2", due=TODAY + timedelta(days=3)),
    )
    assert requests.auto_targets(account, TODAY, rule) == ["1"]


def test_auto_targets_respect_categories_an_empty_set_means_all():
    account = _account(
        _loan("1", due=TODAY + timedelta(days=1), media_type="Tonie"),
        _loan("2", due=TODAY + timedelta(days=1), media_type="Roman"),
    )
    tonies = AutoRenewRule(enabled=True, days=2, categories=frozenset({"tonie"}))
    everything = AutoRenewRule(enabled=True, days=2, categories=frozenset())
    assert RenewalRequests(FakeStore()).auto_targets(account, TODAY, tonies) == ["1"]
    assert RenewalRequests(FakeStore()).auto_targets(account, TODAY, everything) == ["1", "2"]


def test_auto_targets_attempt_once_per_due_date_and_day():
    requests = RenewalRequests(FakeStore())
    rule = AutoRenewRule(enabled=True, days=2, categories=frozenset())
    account = _account(_loan(due=TODAY + timedelta(days=1)))
    assert requests.auto_targets(account, TODAY, rule) == ["1"]
    assert requests.auto_targets(account, TODAY, rule) == []
    assert requests.auto_targets(account, TODAY + timedelta(days=1), rule) == ["1"]


async def test_record_stores_only_requested_with_the_old_due_date():
    store = FakeStore()
    requests = RenewalRequests(store)
    requests.record(
        [
            _outcome("1", date(2026, 11, 1), "renewed"),
            _outcome("2", DUE, "requested"),
            _outcome("3", DUE, "failed"),
        ],
        TODAY,
    )
    await requests.async_save()
    assert store.saved == [{"2": {"due": DUE.isoformat(), "sent": TODAY.isoformat()}}]


async def test_async_save_writes_only_when_dirty_and_once():
    store = FakeStore()
    requests = RenewalRequests(store)
    await requests.async_save()
    assert store.saved == []
    requests.record([_outcome("1", DUE, "requested")], TODAY)
    await requests.async_save()
    await requests.async_save()
    assert len(store.saved) == 1


async def test_async_load_restores_the_record():
    store = FakeStore({"1": {"due": DUE.isoformat(), "sent": TODAY.isoformat()}})
    requests = RenewalRequests(store)
    await requests.async_load()
    loan = requests.mark(_account(_loan()), TODAY, None).loans[0]
    assert (loan.renewable, loan.renew_requested) == (False, True)
