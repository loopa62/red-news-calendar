import json
from datetime import datetime, timezone
from pathlib import Path


class EventStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"version": 1, "events": {}, "runs": []}

    def reconcile(self, incoming: list[dict], observed_week: str) -> dict:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        current = self.data["events"]
        seen = set()
        stats = {"added": 0, "updated": 0, "removed": 0}
        mutable = {"event_name", "datetime_utc", "datetime_local", "forecast", "previous", "classification", "impact", "status"}
        for event in incoming:
            uid = event["uid"]
            seen.add(uid)
            event["observed_week"] = observed_week
            if uid not in current:
                current[uid] = event
                stats["added"] += 1
                continue
            old = current[uid]
            changed = any(old.get(k) != event.get(k) for k in mutable)
            first_seen = old["first_seen_at"]
            last_changed = now if changed else old["last_changed_at"]
            old.update(event)
            old["first_seen_at"] = first_seen
            old["last_seen_at"] = now
            old["last_changed_at"] = last_changed
            old["status"] = "active"
            if changed:
                stats["updated"] += 1
        for uid, old in current.items():
            if old.get("observed_week") == observed_week and uid not in seen and old.get("status") == "active":
                old["status"] = "removed"
                old["last_changed_at"] = now
                stats["removed"] += 1
        return stats

    def add_run(self, run: dict) -> None:
        self.data["runs"] = (self.data.get("runs", []) + [run])[-100:]

    def all_events(self) -> list[dict]:
        return sorted(self.data["events"].values(), key=lambda x: (x["datetime_utc"], x["uid"]))

    def active_events(self) -> list[dict]:
        return [event for event in self.all_events() if event["status"] == "active" and event["classification"] != "EXCLUDED"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(self.path)
