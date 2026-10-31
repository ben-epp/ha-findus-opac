"""Daily due-date notifications and renewal notices via notify services."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date, time, timedelta
import logging
import re
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
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

# Texts live in translations/<lang>.json under "exceptions" (the only free-form text
# section hassfest allows); keys start with this prefix, e.g. notify_title.
TEXT_PREFIX = "notify_"

Texts = Mapping[str, str]


async def async_load_texts(hass: HomeAssistant, language: str) -> dict[str, str]:
    """Notification texts in `language`, English for missing keys: {key without prefix: text}."""
    raw = await async_get_translations(hass, language, "exceptions", [DOMAIN])
    head = f"component.{DOMAIN}.exceptions.{TEXT_PREFIX}"
    return {k[len(head):].removesuffix(".message"): v for k, v in raw.items() if k.startswith(head)}


def _format_date(t: Texts, pattern: str, d: date) -> str:
    """Date tokens (no braces, so each language may use its own set): %a weekday, %b month
    name, %d day, %m month, %D/%M two-digit day/month, %Y year."""
    names = {
        "%a": t["weekdays"].split(",")[d.weekday()],
        "%b": t["months"].split(",")[d.month - 1],
        "%d": str(d.day),
        "%m": str(d.month),
        "%D": f"{d.day:02d}",
        "%M": f"{d.month:02d}",
        "%Y": str(d.year),
    }
    return re.sub(r"%[abdmDMY]", lambda m: names[m[0]], t[pattern])


def _short_date(t: Texts, d: date) -> str:
    """'Fr., 8.11.' / 'Fri 8 Nov'."""
    return _format_date(t, "date_short", d)


def _long_date(t: Texts, d: date) -> str:
    """'15.06.2027' / '15 Jun 2027'."""
    return _format_date(t, "date_long", d)


def _items(t: Texts, loans: Iterable[Loan]) -> str:
    def name(l: Loan) -> str:
        if l.renewable:
            return f"{l.title} ({t['renewable']})"
        return f"{l.title} ({t['pending']})" if l.renew_requested else l.title

    return ", ".join(name(l) for l in loans)


def build_message(
    t: Texts,
    account_name: str,
    loans_by_kind: dict[str, list[Loan]],
    card_until: date | None,
    today: date,
) -> tuple[str, str]:
    """(title, message) for one daily run. `loans_by_kind`: overdue / due_today / due_soon."""
    lines: list[str] = []

    by_days: dict[int, list[Loan]] = {}
    for l in loans_by_kind.get("overdue", []):
        by_days.setdefault(-l.days_left(today), []).append(l)
    for n in sorted(by_days, reverse=True):
        key = "overdue_one" if n == 1 else "overdue_other"
        lines.append(t[key].format(count=n, items=_items(t, by_days[n])))

    if today_loans := loans_by_kind.get("due_today"):
        lines.append(t["due_today"].format(items=_items(t, today_loans)))

    by_due: dict[date, list[Loan]] = {}
    for l in loans_by_kind.get("due_soon", []):
        by_due.setdefault(l.due, []).append(l)
    for d in sorted(by_due):
        lines.append(t["due_on"].format(date=_short_date(t, d), items=_items(t, by_due[d])))

    if card_until is not None:
        key = "card_expired" if card_until < today else "card"
        lines.append(t[key].format(date=_long_date(t, card_until)))

    return t["title"].format(account=account_name), "\n".join(lines)


def build_renewal_message(
    t: Texts, account_name: str, items: list[dict[str, Any]], trigger: str
) -> tuple[str, str]:
    """(title, message) for a findus_opac_renewal event payload."""
    lines: list[str] = []
    requested = [i["title"] for i in items if i.get("status") == "requested"]
    if requested:
        lines.append(t["requested"].format(items=", ".join(requested)))
    by_due: dict[str, list[str]] = {}
    for i in items:
        if i.get("status") == "renewed" and i.get("new_due"):
            by_due.setdefault(i["new_due"], []).append(i["title"])
    for due in sorted(by_due):
        d = date.fromisoformat(due)
        lines.append(t["renewed"].format(date=_short_date(t, d), items=", ".join(by_due[due])))
    if failed := [i["title"] for i in items if i.get("status") == "failed"]:
        lines.append(t["not_accepted"].format(items=", ".join(failed)))
    message = "\n".join(lines)
    if trigger == "auto" and message:
        message = t["auto"].format(message=message)
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

    async def _async_texts(self) -> dict[str, str]:
        return await async_load_texts(self.hass, self.hass.config.language)

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
        texts = await self._async_texts()
        title, message = build_message(
            texts, self.coordinator.account_name, kinds, card_until, today
        )
        renewable = any(l.renewable for group in kinds.values() for l in group)
        await self._async_send(title, message, action_title=texts["action"] if renewable else None)
        for key in new_keys:
            sent[key] = today.isoformat()
        await self._store.async_save(sent)

    async def _async_send(self, title: str, message: str, action_title: str | None = None) -> None:
        for target in self.targets:
            if not self.hass.services.has_service("notify", target):
                _LOGGER.warning("Notify service notify.%s not found; skipping", target)
                continue
            payload: dict[str, Any] = {"title": title, "message": message}
            if target.startswith("mobile_app_"):
                data: dict[str, Any] = {"tag": f"findus_opac_{self.entry_id}", "group": "findus_opac"}
                if action_title:
                    data["actions"] = [{"action": self.action, "title": action_title}]
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
            texts = await self._async_texts()
            title = texts["title"].format(account=self.coordinator.account_name)
            await self._async_send(title, texts["failed"].format(error=err))

    async def _async_handle_renewal(self, event: Event) -> None:
        data = event.data
        if data.get("config_entry_id") != self.entry_id or not data.get("items"):
            return
        title, message = build_renewal_message(
            await self._async_texts(), self.coordinator.account_name, data["items"], data.get("trigger", "manual")
        )
        if message:
            await self._async_send(title, message)
