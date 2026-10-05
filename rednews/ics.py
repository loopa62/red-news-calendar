from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from icalendar import Alarm, Calendar, Event


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_calendar(events: list[dict], generated_at: datetime | None = None) -> bytes:
    uids = [event["uid"] for event in events]
    if len(uids) != len(set(uids)):
        raise ValueError("duplicate UID detected")
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cal = Calendar()
    cal.add("prodid", "-//Ashley RED NEWS//Economic Calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Ashley RED NEWS")
    cal.add("x-wr-timezone", "Asia/Jakarta")
    cal.add("refresh-interval", timedelta(hours=1))
    cal.add("x-published-ttl", timedelta(hours=1))
    for item in sorted(events, key=lambda x: (x["datetime_utc"], x["uid"])):
        event = Event()
        event.add("uid", item["uid"])
        event.add("dtstamp", generated_at)
        start = _dt(item["datetime_utc"]).astimezone(ZoneInfo(item["timezone"]))
        event.add("dtstart", start)
        event.add("dtend", start + timedelta(minutes=30))
        event.add("last-modified", _dt(item["last_changed_at"]))
        event.add("sequence", int(_dt(item["last_changed_at"]).timestamp()))
        event.add("status", "CONFIRMED")
        event.add("summary", f"🔴 {item['currency']} — {item['event_name']}")
        description = "\n".join([
            f"Currency: {item['currency']}", f"Impact: {item['classification']}",
            f"Event: {item['event_name']}", "", f"Forecast: {item['forecast'] or '—'}",
            f"Previous: {item['previous'] or '—'}", "", f"Source: {item['source']}",
            f"Last updated: {item['last_seen_at']}",
        ])
        event.add("description", description)
        event.add("url", item["source_url"])
        for minutes, text in [(60, "RED NEWS in 1 hour"), (15, "RED NEWS in 15 minutes")]:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("trigger", timedelta(minutes=-minutes))
            alarm.add("description", text)
            event.add_component(alarm)
        cal.add_component(event)
    return cal.to_ical()


def validate_calendar(raw: bytes) -> dict:
    parsed = Calendar.from_ical(raw)
    events = [component for component in parsed.walk() if component.name == "VEVENT"]
    uids = [str(event["UID"]) for event in events]
    if len(uids) != len(set(uids)):
        raise ValueError("duplicate UID in generated calendar")
    for event in events:
        alarms = [c for c in event.subcomponents if c.name == "VALARM"]
        triggers = {int(a.decoded("TRIGGER").total_seconds()) for a in alarms}
        if triggers != {-3600, -900}:
            raise ValueError(f"invalid alarms for {event['UID']}: {triggers}")
        if event.decoded("DTSTART").tzinfo is None:
            raise ValueError(f"timezone missing for {event['UID']}")
    return {"valid": True, "events": len(events), "unique_uids": len(uids)}
