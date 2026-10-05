import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .classifier import load_rules
from .ics import build_calendar, validate_calendar
from .models import normalize_event
from .source import fetch_calendar
from .store import EventStore

LOG = logging.getLogger("rednews")


class PipelineError(RuntimeError):
    pass


def validate_source(raw: list[dict], minimum: int) -> None:
    if len(raw) < minimum:
        raise PipelineError(f"suspicious source size: {len(raw)} < {minimum}")
    required = {"title", "country", "impact", "date", "forecast", "previous"}
    for index, event in enumerate(raw):
        if not isinstance(event, dict) or not required.issubset(event):
            raise PipelineError(f"invalid schema at row {index}")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def run_pipeline(fetcher: Callable[[], list[dict]] = fetch_calendar, output_path: Path = Path("public/red-news.ics"), state_path: Path = Path("data/events.json"), rules_path: Path = Path("config/rules.json")) -> dict:
    now = datetime.now(timezone.utc)
    rules = load_rules(Path(rules_path))
    LOG.info("Starting RED NEWS pipeline")
    LOG.info("Fetching source")
    try:
        raw = fetcher()
        validate_source(raw, int(rules["minimum_source_events"]))
        normalized = [normalize_event(row, rules, now=now) for row in raw]
    except Exception as exc:
        LOG.error("Source rejected; preserving last known-good feed: %s", exc)
        raise PipelineError(str(exc)) from exc

    usd = [e for e in normalized if e["currency"] == "USD"]
    usd_high = [e for e in usd if e["impact"] == "HIGH"]
    quality = [e for e in usd_high if e["classification"] in {"EXTREME", "HIGH"}]
    non_usd = [e for e in normalized if e["classification"] == "SUPER_HIGH_IMPACT"]
    final = quality + non_usd

    store = EventStore(Path(state_path))
    source_dates = [datetime.fromisoformat(e["datetime_utc"].replace("Z", "+00:00")) for e in normalized]
    observed_week = min(source_dates).strftime("%G-W%V")
    stats = store.reconcile(final, observed_week)
    run = {
        "timestamp": now.isoformat().replace("+00:00", "Z"), "status": "success",
        "source_events": len(raw), "usd_events": len(usd), "usd_high_impact": len(usd_high),
        "quality_filter_passed": len(quality), "non_usd_super_events": len(non_usd),
        "final_red_news": len(final), **stats,
    }
    store.add_run(run)
    candidate = build_calendar(store.active_events(), generated_at=now)
    validation = validate_calendar(candidate)
    store.save()
    atomic_write(Path(output_path), candidate)
    LOG.info("Source OK; Raw events: %d; USD: %d; USD high: %d", len(raw), len(usd), len(usd_high))
    LOG.info("Quality filter: %d; Non-USD super: %d; Final RED NEWS: %d", len(quality), len(non_usd), len(final))
    LOG.info("Added: %d; Updated: %d; Removed: %d", stats["added"], stats["updated"], stats["removed"])
    LOG.info("ICS generated; Validation PASS; Pipeline complete")
    return {**run, "events": final, "validation": validation}
