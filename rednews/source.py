import json
import urllib.error
import urllib.request


SOURCE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def fetch_calendar(url: str = SOURCE_URL, timeout: int = 30) -> list[dict]:
    request = urllib.request.Request(url, headers={"User-Agent": "Ashley-RED-NEWS/1.0 (+personal calendar)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"source HTTP {response.status}")
            payload = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"source fetch failed: {exc}") from exc
    try:
        data = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"malformed source JSON: {exc}") from exc
    if not isinstance(data, list):
        raise RuntimeError("source root must be a JSON array")
    return data
