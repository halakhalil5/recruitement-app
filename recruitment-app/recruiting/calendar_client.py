"""The one object you talk to: `CalendarClient`.

    cal.find_free_slots(attendees, duration_min=45)  -> list[TimeSlot]
    cal.create_event(...)                            -> event link

`find_free_slots` only reads. `create_event` writes to the calendar and
sends invites - call it only after a human has picked one of the proposed
slots, never as a side effect of proposing them. That is the "review
important actions before they are executed" requirement, made structural:
two separate methods instead of one that books automatically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build

from .auth import get_credentials
from .models import TimeSlot

WORK_START_HOUR = 9
WORK_END_HOUR = 17


class CalendarClient:
    def __init__(self, calendar_id: str = "primary", credentials=None) -> None:
        self._service = build("calendar", "v3", credentials=credentials or get_credentials())
        self.calendar_id = calendar_id

    def find_free_slots(
        self,
        attendee_emails: list[str],
        duration_min: int = 45,
        search_days: int = 5,
        max_slots: int = 3,
    ) -> list[TimeSlot]:
        """Open slots, working hours only (UTC, Mon-Fri), across every attendee."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=search_days)
        response = (
            self._service.freebusy()
            .query(
                body={
                    "timeMin": now.isoformat(),
                    "timeMax": (cutoff + timedelta(days=2)).isoformat(),  # pad past weekends
                    "items": [{"id": email} for email in attendee_emails],
                }
            )
            .execute()
        )
        busy = [
            (_parse(period["start"]), _parse(period["end"]))
            for calendar in response.get("calendars", {}).values()
            for period in calendar.get("busy", [])
        ]

        duration = timedelta(minutes=duration_min)
        slots: list[TimeSlot] = []
        cursor = _next_business_start(now)
        while len(slots) < max_slots and cursor < cutoff:
            day_end = cursor.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
            candidate_end = cursor + duration
            if candidate_end > day_end:
                cursor = _next_business_start(cursor + timedelta(days=1))
                continue
            if any(cursor < b_end and candidate_end > b_start for b_start, b_end in busy):
                cursor += timedelta(minutes=15)
                continue
            slots.append(TimeSlot(start=cursor, end=candidate_end))
            cursor = candidate_end + timedelta(minutes=15)
        return slots

    def create_event(
        self,
        summary: str,
        slot: TimeSlot,
        attendee_emails: list[str],
        description: str = "",
    ) -> str:
        """Book one confirmed slot and invite `attendee_emails`. Returns the event link."""
        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": slot.start.isoformat()},
            "end": {"dateTime": slot.end.isoformat()},
            "attendees": [{"email": email} for email in attendee_emails],
        }
        created = (
            self._service.events()
            .insert(calendarId=self.calendar_id, body=event, sendUpdates="all")
            .execute()
        )
        return created.get("htmlLink", "")


def _next_business_start(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    if dt.hour >= WORK_END_HOUR:
        dt = (dt + timedelta(days=1)).replace(hour=WORK_START_HOUR, minute=0)
    elif dt.hour < WORK_START_HOUR:
        dt = dt.replace(hour=WORK_START_HOUR, minute=0)
    while dt.weekday() >= 5:  # Saturday=5, Sunday=6
        dt = (dt + timedelta(days=1)).replace(hour=WORK_START_HOUR, minute=0)
    return dt


def _parse(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
