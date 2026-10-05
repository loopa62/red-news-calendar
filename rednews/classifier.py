import json
import re
from pathlib import Path


def load_rules(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_name(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"\b(m/m|q/q|y/y|s/a|prelim|final)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _matches(name: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, name, re.IGNORECASE) for pattern in patterns)


def classify_event(raw: dict, rules: dict) -> str:
    name = normalize_name(str(raw.get("title", "")))
    currency = str(raw.get("country", "")).upper()
    impact = str(raw.get("impact", "")).upper()
    if impact != "HIGH" or not name or _matches(name, rules["exclude_patterns"]):
        return "EXCLUDED"
    if currency == "USD":
        if _matches(name, rules["extreme_patterns"]):
            return "EXTREME"
        if _matches(name, rules["high_patterns"]):
            return "HIGH"
        return "EXCLUDED"
    if currency in rules["non_usd_currencies"] and _matches(name, rules["non_usd_super_patterns"]):
        return "SUPER_HIGH_IMPACT"
    return "EXCLUDED"
