import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .classifier import classify_event, normalize_name


def stable_uid(source: str, currency: str, normalized_name: str, event_date: str) -> str:
    identity = "|".join([source.casefold(), currency.upper(), normalized_name, event_date])
    digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return f"{digest}@red-news-calendar"


def normalize_event(raw: dict, rules: dict, now: datetime | None = None) -> dict:
    required = {"title", "country", "impact", "date", "forecast", "previous"}
    if not required.issubset(raw):
        raise ValueError(f"missing fields: {sorted(required - set(raw))}")
    parsed = datetime.fromisoformat(str(raw["date"]).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("source datetime must include timezone offset")
    utc = parsed.astimezone(timezone.utc)
    local = utc.astimezone(ZoneInfo(rules["timezone"]))
    seen = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    normalized = normalize_name(str(raw["title"]))
    currency = str(raw["country"]).upper()
    source = rules["source_name"]
    return {
        "uid": stable_uid(source, currency, normalized, local.date().isoformat()),
        "source_id": None,
        "event_name": str(raw["title"]).strip(),
        "normalized_name": normalized,
        "currency": currency,
        "impact": str(raw["impact"]).upper(),
        "classification": classify_event(raw, rules),
        "datetime_utc": utc.isoformat().replace("+00:00", "Z"),
        "datetime_local": local.isoformat(),
        "timezone": rules["timezone"],
        "forecast": str(raw.get("forecast") or ""),
        "previous": str(raw.get("previous") or ""),
        "source": source,
        "source_url": rules["source_url"],
        "first_seen_at": seen.isoformat().replace("+00:00", "Z"),
        "last_seen_at": seen.isoformat().replace("+00:00", "Z"),
        "last_changed_at": seen.isoformat().replace("+00:00", "Z"),
        "status": "active",
    }
