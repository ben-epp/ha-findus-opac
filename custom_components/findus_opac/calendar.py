"""Calendar: one all-day event per due date."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import Loan
from .coordinator import FindusConfigEntry, FindusCoordinator
from .entity import FindusEntity
from .notifications import async_load_texts, count_text

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FindusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([FindusCalendar(entry.runtime_data)])


class FindusCalendar(FindusEntity, CalendarEntity):
    def __init__(self, coordinator: FindusCoordinator) -> None:
        super().__init__(coordinator, "due_dates")
        self._texts: Mapping[str, str] = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._texts = await async_load_texts(self.hass, self.hass.config.language)

    def _events(self) -> list[CalendarEvent]:
        by_due: dict[date, list[Loan]] = {}
        for loan in self.coordinator.data.loans:
            by_due.setdefault(loan.due, []).append(loan)
        return [
            CalendarEvent(
                # Counts only: the summary is stored in the recorder, the description is not.
                summary=self._texts["calendar_due"].format(items=count_text(self._texts, len(loans))),
                description="\n".join(l.title for l in loans),
                start=due,
                end=due + timedelta(days=1),
                uid=f"{self.coordinator.entry.entry_id}_{due}",
            )
            for due, loans in sorted(by_due.items())
        ]

    @property
    def event(self) -> CalendarEvent | None:
        """The next due date; overdue items stay on the past dates."""
        if not self._texts:
            return None
        today = self.coordinator.today()
        return next((e for e in self._events() if e.start >= today), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            e
            for e in self._events()
            if e.start < end_date.date() and e.end > start_date.date()
        ]
