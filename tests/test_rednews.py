import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from icalendar import Calendar

from rednews.classifier import classify_event, load_rules, normalize_name
from rednews.ics import build_calendar, validate_calendar
from rednews.models import normalize_event, stable_uid
from rednews.pipeline import PipelineError, run_pipeline
from rednews.store import EventStore

RULES = load_rules(Path(__file__).parents[1] / "config" / "rules.json")


def source_event(title="CPI m/m", country="USD", impact="High", date="2026-10-13T08:30:00-04:00", forecast="0.3%", previous="0.2%"):
    return {"title": title, "country": country, "impact": impact, "date": date, "forecast": forecast, "previous": previous}


def test_quality_filter_is_selective_and_deterministic():
    assert classify_event(source_event(), RULES) == "EXTREME"
    assert classify_event(source_event("FOMC Meeting Minutes"), RULES) == "HIGH"
    assert classify_event(source_event("Consumer Credit m/m"), RULES) == "EXCLUDED"
    assert classify_event(source_event("10-y Bond Auction"), RULES) == "EXCLUDED"
    assert classify_event(source_event("ECB Main Refinancing Rate", "EUR"), RULES) == "SUPER_HIGH_IMPACT"
    assert classify_event(source_event("German CPI m/m", "EUR"), RULES) == "EXCLUDED"
    assert classify_event(source_event("CPI m/m", "USD", "Medium"), RULES) == "EXCLUDED"


def test_normalized_names_are_stable():
    assert normalize_name("  Core CPI m/m ") == "core cpi"
    assert normalize_name("Non-Farm Employment Change") == "non farm employment change"


def test_uid_does_not_change_when_time_or_details_change():
    a = normalize_event(source_event(), RULES, now=datetime(2026, 10, 5, tzinfo=timezone.utc))
    changed = source_event(date="2026-10-13T09:00:00-04:00", forecast="0.4%")
    b = normalize_event(changed, RULES, now=datetime(2026, 10, 5, tzinfo=timezone.utc))
    assert a["uid"] == b["uid"]
    assert a["datetime_utc"] != b["datetime_utc"]


def test_uid_separates_different_named_events_on_same_date():
    a = normalize_event(source_event("CPI m/m"), RULES)
    b = normalize_event(source_event("Core CPI m/m"), RULES)
    assert a["uid"] != b["uid"]


def test_store_detects_create_update_and_missing_without_deleting_history(tmp_path):
    store = EventStore(tmp_path / "state.json")
    first = normalize_event(source_event(), RULES)
    stats = store.reconcile([first], observed_week="2026-W42")
    assert stats == {"added": 1, "updated": 0, "removed": 0}
    changed = normalize_event(source_event(date="2026-10-13T09:00:00-04:00"), RULES)
    stats = store.reconcile([changed], observed_week="2026-W42")
    assert stats == {"added": 0, "updated": 1, "removed": 0}
    stats = store.reconcile([], observed_week="2026-W42")
    assert stats == {"added": 0, "updated": 0, "removed": 1}
    assert store.all_events()[0]["status"] == "removed"


def test_ics_is_parseable_wib_and_contains_two_attached_alarms():
    event = normalize_event(source_event(), RULES)
    raw = build_calendar([event], generated_at=datetime(2026, 10, 5, tzinfo=timezone.utc))
    cal = Calendar.from_ical(raw)
    vevents = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(vevents) == 1
    vevent = vevents[0]
    assert str(vevent["UID"]) == event["uid"]
    assert vevent.decoded("DTSTART").tzinfo is not None
    assert vevent.decoded("DTSTART").astimezone().utcoffset() is not None
    alarms = [c for c in vevent.subcomponents if c.name == "VALARM"]
    assert sorted(int(a.decoded("TRIGGER").total_seconds()) for a in alarms) == [-3600, -900]
    assert validate_calendar(raw)["valid"] is True


def test_duplicate_uids_are_rejected():
    event = normalize_event(source_event(), RULES)
    with pytest.raises(ValueError, match="duplicate UID"):
        build_calendar([event, copy.deepcopy(event)])


def test_pipeline_does_not_overwrite_good_feed_on_bad_source(tmp_path):
    output = tmp_path / "red-news.ics"
    state = tmp_path / "events.json"
    output.write_text("KNOWN-GOOD", encoding="utf-8")
    with pytest.raises(PipelineError):
        run_pipeline(fetcher=lambda: [], output_path=output, state_path=state, rules_path=Path(__file__).parents[1] / "config" / "rules.json")
    assert output.read_text(encoding="utf-8") == "KNOWN-GOOD"


def test_pipeline_does_not_mutate_state_when_candidate_calendar_fails(tmp_path, monkeypatch):
    output = tmp_path / "red-news.ics"
    state = tmp_path / "events.json"
    output.write_text("KNOWN-GOOD", encoding="utf-8")
    state.write_text('{"version": 1, "events": {}, "runs": []}\n', encoding="utf-8")
    original_state = state.read_text(encoding="utf-8")
    rows = [source_event() for _ in range(10)]
    monkeypatch.setattr("rednews.pipeline.build_calendar", lambda *args, **kwargs: b"BROKEN")
    with pytest.raises(Exception):
        run_pipeline(fetcher=lambda: rows, output_path=output, state_path=state, rules_path=Path(__file__).parents[1] / "config" / "rules.json")
    assert output.read_text(encoding="utf-8") == "KNOWN-GOOD"
    assert state.read_text(encoding="utf-8") == original_state


def test_pipeline_rejects_malformed_schema_without_overwrite(tmp_path):
    output = tmp_path / "red-news.ics"
    output.write_text("KNOWN-GOOD", encoding="utf-8")
    with pytest.raises(PipelineError):
        run_pipeline(fetcher=lambda: [{"nonsense": True}], output_path=output, state_path=tmp_path / "events.json", rules_path=Path(__file__).parents[1] / "config" / "rules.json")
    assert output.read_text(encoding="utf-8") == "KNOWN-GOOD"
