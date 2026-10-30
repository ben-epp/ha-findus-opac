"""Daily due-date notifications and renewal notices via notify services."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, time, timedelta
import logging
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .client import Loan
from .const import (
    CONF_NOTIFY_EVENTS,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_TIME,
    DEFAULT_NOTIFY_TIME,
    DOMAIN,
    EVENT_RENEWAL,
    NOTIFY_ACTION_PREFIX,
    NOTIFY_EVENTS,
    NOTIFY_KEEP_DAYS,
)
from .coordinator import FindusCoordinator

_LOGGER = logging.getLogger(__name__)

MOBILE_ACTION_EVENT = "mobile_app_notification_action"
CARD_THRESHOLDS = (30, 7)  # days before the library card expires

WEEKDAYS = {
    "de": ("Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

TEXT = {
    "de": {
        "title": "Bücherei: {account}",
        "renewable": " (verlängerbar)",
        "overdue": "Überfällig seit {n} {days}: {items}",
        "day": ("Tag", "Tagen"),
        "today": "Heute fällig: {items}",
        "soon": "Fällig am {date}: {items}",
        "card": "Ausweis gültig bis {date} – bitte verlängern lassen",
        "card_expired": "Ausweis abgelaufen seit {date} – bitte verlängern lassen",
        "requested": "Verlängerung beantragt: {items}",
        "renewed": "Verlängert bis {date}: {items}",
        "auto": "Automatisch: ",
        "failed": "Verlängerung fehlgeschlagen: {error}",
        "action": "Verlängern",
    },
    "en": {
        "title": "Library: {account}",
        "renewable": " (renewable)",
        "overdue": "Overdue for {n} {days}: {items}",
        "day": ("day", "days"),
        "today": "Due today: {items}",
        "soon": "Due {date}: {items}",
        "card": "Library card valid until {date} – please have it renewed",
        "card_expired": "Library card expired on {date} – please have it renewed",
        "requested": "Renewal requested: {items}",
        "renewed": "Renewed until {date}: {items}",
        "auto": "Automatic: ",
        "failed": "Renewal failed: {error}",
        "action": "Renew",
    },
}


def _lang(language: str | None) -> str:
    return "de" if (language or "").lower().startswith("de") else "en"


def _short_date(lang: str, d: date) -> str:
    """'Fr., 8.11.' / 'Fri 8 Nov'."""
    wd = WEEKDAYS[lang][d.weekday()]
    return f"{wd}, {d.day}.{d.month}." if lang == "de" else f"{wd} {d.day} {MONTHS_EN[d.month - 1]}"


def _long_date(lang: str, d: date) -> str:
    """'15.06.2027' / '15 Jun 2027'."""
    return f"{d:%d.%m.%Y}" if lang == "de" else f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}"


def _items(lang: str, loans: Iterable[Loan]) -> str:
    t = TEXT[lang]
    return ", ".join(f"{l.title}{t['renewable'] if l.renewable else ''}" for l in loans)


def build_message(
    lang: str,
    account_name: str,
    loans_by_kind: dict[str, list[Loan]],
    card_until: date | None,
    today: date,
) -> tuple[str, str]:
    """(title, message) for one daily run. `loans_by_kind`: overdue / due_today / due_soon."""
    lang = _lang(lang)
    t = TEXT[lang]
    lines: list[str] = []

    by_days: dict[int, list[Loan]] = {}
    for l in loans_by_kind.get("overdue", []):
        by_days.setdefault(-l.days_left(today), []).append(l)
    for n in sorted(by_days, reverse=True):
        days = t["day"][0] if n == 1 else t["day"][1]
        lines.append(t["overdue"].format(n=n, days=days, items=_items(lang, by_days[n])))

    if today_loans := loans_by_kind.get("due_today"):
        lines.append(t["today"].format(items=_items(lang, today_loans)))

    by_due: dict[date, list[Loan]] = {}
    for l in loans_by_kind.get("due_soon", []):
        by_due.setdefault(l.due, []).append(l)
    for d in sorted(by_due):
        lines.append(t["soon"].format(date=_short_date(lang, d), items=_items(lang, by_due[d])))

    if card_until is not None:
        key = "card_expired" if card_until < today else "card"
        lines.append(t[key].format(date=_long_date(lang, card_until)))

    return t["title"].format(account=account_name), "\n".join(lines)


def build_renewal_message(
    lang: str, account_name: str, items: list[dict[str, Any]], trigger: str
) -> tuple[str, str]:
    """(title, message) for a findus_opac_renewal event payload."""
    lang = _lang(lang)
    t = TEXT[lang]
    lines: list[str] = []
    requested = [i["title"] for i in items if i.get("status") != "renewed"]
    if requested:
        lines.append(t["requested"].format(items=", ".join(requested)))
    by_due: dict[str, list[str]] = {}
    for i in items:
        if i.get("status") == "renewed" and i.get("new_due"):
            by_due.setdefault(i["new_due"], []).append(i["title"])
    for due in sorted(by_due):
        d = date.fromisoformat(due)
        lines.append(t["renewed"].format(date=_short_date(lang, d), items=", ".join(by_due[due])))
    message = "\n".join(lines)
    if trigger == "auto" and message:
        message = t["auto"] + message
    return t["title"].format(account=account_name), message


# Stored next to the dedup keys: the day of the last digest run (for catch-up after restarts).
LAST_RUN_KEY = "_last_run"


class FindusNotifier:
    """Per-account notifier: daily digest, renewal notices, mobile 'Renew' action."""

    def __init__(self, hass: HomeAssistant, coordinator: FindusCoordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        entry = coordinator.entry
        opts = entry.options
        self.entry_id = entry.entry_id
        self.targets: list[str] = list(opts.get(CONF_NOTIFY_TARGETS) or [])
        self.events: set[str] = set(opts.get(CONF_NOTIFY_EVENTS, NOTIFY_EVENTS))
        self.at: time = dt_util.parse_time(
            str(opts.get(CONF_NOTIFY_TIME, DEFAULT_NOTIFY_TIME))
        ) or time(8, 0)
        self.action = f"{NOTIFY_ACTION_PREFIX}{self.entry_id}"
        self._store: Store[dict[str, str]] = Store(hass, 1, f"{DOMAIN}.notified.{self.entry_id}")
        self._sent: dict[str, str] | None = None

    @property
    def lang(self) -> str:
        return _lang(self.hass.config.language)

    @callback
    def async_start(self) -> Callable[[], None]:
        """Register listeners; returns the combined unsubscribe callback."""
        unsubs = [
            async_track_time_change(
                self.hass, self._async_daily, hour=self.at.hour, minute=self.at.minute, second=self.at.second
            ),
            self.hass.bus.async_listen(MOBILE_ACTION_EVENT, self._async_handle_action),
            # HA was down or restarting at notify time: send today's digest once it is up.
            async_at_started(self.hass, self._async_catch_up),
        ]
        if "renewed" in self.events:
            unsubs.append(self.hass.bus.async_listen(EVENT_RENEWAL, self._async_handle_renewal))

        @callback
        def _stop() -> None:
            for unsub in unsubs:
                unsub()

        return _stop

    async def _async_load(self) -> dict[str, str]:
        if self._sent is None:
            self._sent = dict(await self._store.async_load() or {})
        return self._sent

    async def _async_daily(self, _now: Any = None) -> None:
        await self.async_run()

    async def _async_catch_up(self, _hass: HomeAssistant) -> None:
        sent = await self._async_load()
        if dt_util.now().time() >= self.at and sent.get(LAST_RUN_KEY) != self.coordinator.today().isoformat():
            await self.async_run()

    async def async_run(self) -> None:
        """Refresh, then send one digest with everything not notified yet."""
        await self.coordinator.async_refresh()  # failures are logged; last data is used
        account = self.coordinator.data
        if account is None:
            return
        sent = await self._async_load()
        today = self.coordinator.today()
        cutoff = (today - timedelta(days=NOTIFY_KEEP_DAYS)).isoformat()
        for key in [k for k, v in sent.items() if v < cutoff]:
            del sent[key]
        sent[LAST_RUN_KEY] = today.isoformat()

        kinds: dict[str, list[Loan]] = {"overdue": [], "due_today": [], "due_soon": []}
        new_keys: list[str] = []
        for loan in account.loans:
            left = loan.days_left(today)
            if left < 0:
                kind, key = "overdue", f"overdue:{loan.mednr}:{loan.due}:{today}"
            elif left == 0:
                kind, key = "due_today", f"due_today:{loan.mednr}:{loan.due}"
            elif left <= self.coordinator.due_soon_days:
                kind, key = "due_soon", f"due_soon:{loan.mednr}:{loan.due}"
            else:
                continue
            if kind in self.events and key not in sent:
                kinds[kind].append(loan)
                new_keys.append(key)

        card_until = None
        until = account.card_valid_until
        if "card_expiry" in self.events and until is not None:
            left = (until - today).days
            due_keys = [f"card{n}:{until}" for n in CARD_THRESHOLDS if left <= n]
            if any(k not in sent for k in due_keys):
                card_until = until
                new_keys.extend(k for k in due_keys if k not in sent)

        if not new_keys:
            await self._store.async_save(sent)
            return
        title, message = build_message(
            self.lang, self.coordinator.account_name, kinds, card_until, today
        )
        renewable = any(l.renewable for group in kinds.values() for l in group)
        await self._async_send(title, message, with_action=renewable)
        for key in new_keys:
            sent[key] = today.isoformat()
        await self._store.async_save(sent)

    async def _async_send(self, title: str, message: str, with_action: bool = False) -> None:
        for target in self.targets:
            if not self.hass.services.has_service("notify", target):
                _LOGGER.warning("Notify service notify.%s not found; skipping", target)
                continue
            payload: dict[str, Any] = {"title": title, "message": message}
            if target.startswith("mobile_app_"):
                data: dict[str, Any] = {"tag": f"findus_opac_{self.entry_id}", "group": "findus_opac"}
                if with_action:
                    data["actions"] = [{"action": self.action, "title": TEXT[self.lang]["action"]}]
                payload["data"] = data
            try:
                await self.hass.services.async_call("notify", target, payload, blocking=False)
            except HomeAssistantError as err:
                _LOGGER.warning("Sending to notify.%s failed: %s", target, err)

    async def _async_handle_action(self, event: Event) -> None:
        if event.data.get("action") != self.action:
            return
        try:
            await self.coordinator.async_renew()
        except HomeAssistantError as err:
            title = TEXT[self.lang]["title"].format(account=self.coordinator.account_name)
            await self._async_send(title, TEXT[self.lang]["failed"].format(error=err))

    async def _async_handle_renewal(self, event: Event) -> None:
        data = event.data
        if data.get("config_entry_id") != self.entry_id or not data.get("items"):
            return
        title, message = build_renewal_message(
            self.lang, self.coordinator.account_name, data["items"], data.get("trigger", "manual")
        )
        if message:
            await self._async_send(title, message)
