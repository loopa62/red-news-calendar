# Ashley RED NEWS Calendar

A deliberately low-noise economic calendar feed. It publishes only selected market-moving USD high-impact releases, plus a tiny configurable list of exceptional non-USD central-bank events.

## Architecture

```text
Fair Economy JSON adapter
  -> schema/sanity validation
  -> canonical normalization (UTC + Asia/Jakarta)
  -> deterministic rules/classification
  -> persistent JSON event state + change detection
  -> RFC 5545 ICS + two attached VALARMs
  -> parser validation
  -> GitHub Pages HTTPS feed
```

The source adapter is isolated in `rednews/source.py`, so another free source can replace Fair Economy without rewriting classification, state, or calendar generation.

## Source and safety

Primary source: `https://nfs.faireconomy.media/ff_calendar_thisweek.json` (ForexFactory-compatible Fair Economy feed).

The build rejects HTTP errors, malformed JSON, missing schema fields, and fewer than 10 source events. It creates the candidate calendar in memory and validates it before atomically replacing the public file. A failed fetch therefore leaves the last known-good ICS untouched. GitHub Pages also retains its prior deployment when a workflow fails.

Because the free source exposes the current week only, persistent state retains historical records independently. The workflow runs hourly at minute 7 and also supports manual dispatch.

## Classification and filtering

All rules live in **`config/rules.json`**.

- `EXTREME`: selected USD inflation, labor, FOMC rate/statement/press conference, Powell, PCE, and GDP releases.
- `HIGH`: selected USD FOMC minutes, ADP, ISM, Retail Sales, consumer sentiment, and JOLTS.
- `SUPER_HIGH_IMPACT`: explicitly allowed non-USD central-bank decisions only.
- `EXCLUDED`: everything else, including auctions, Consumer Credit, routine Fed-member speeches, inventories, and any non-high source event.

Order is exclusion first, then the allowlists. To add/remove an event, modify the corresponding regex array in `config/rules.json`, add a test in `tests/test_rednews.py`, and run `python -m pytest -q`.

## Canonical event and stable UID

Stored events include source name, original and normalized names, currency, source impact, internal classification, UTC and local timestamps, forecast/previous, first/last seen, last changed, and status.

UID algorithm:

```text
sha256(lower(source) | upper(currency) | normalized_event_name | Asia/Jakarta_event_date)[:24]
  + "@red-news-calendar"
```

The event time and forecast are deliberately excluded, so schedule/detail revisions update the existing VEVENT rather than creating duplicates. Event date is based on WIB to make identity stable for the user's calendar. Same-name same-day duplicate source records intentionally collapse to one identity; validation rejects duplicate UIDs.

## Change detection and storage

`data/events.json` is independent of the ICS. Each successful run:

- creates unseen UIDs;
- updates time/details for existing UIDs while retaining `first_seen_at`;
- marks current-week records missing from a valid fresh source as `removed`;
- never deletes historical records immediately;
- generates ICS only from active qualifying records.

The source offers only a current-week feed, so future coverage is limited to what upstream publishes. State is retained long-term for debugging; the visible ICS stays focused on active qualifying events.

## ICS behavior

- RFC 5545 output generated and parsed by Python `icalendar`.
- `DTSTART` uses `Asia/Jakarta`; canonical state remains UTC.
- Fixed 30-minute display block.
- Attached `VALARM` at T-60 and T-15 (not fake events).
- Unique UID, `SEQUENCE`, `LAST-MODIFIED`, `STATUS`, description, and source URL.
- UTF-8 output with CRLF/folding handled by the library.

Calendar applications may choose whether to honor alarms from subscribed calendars. Google also controls how frequently it polls external feeds, so an hourly publisher refresh does not guarantee hourly Google ingestion.

## Local use and testing

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python build.py --test
```

`--test` fetches current data, builds the feed, parses it again, checks duplicate UIDs/timezones/alarms, and prints acceptance counts plus final events. Automated tests cover filtering, name normalization, stable updates, duplicate rejection, WIB timestamps, both alarms, state transitions, malformed-schema protection, and empty/suspicious-source protection.

## Deployment

1. Create a public GitHub repository and push this directory to `main`.
2. In repository **Settings -> Pages**, select **GitHub Actions** as the source.
3. Run **Actions -> Refresh RED NEWS feed -> Run workflow** once.
4. Feed URL: `https://<owner>.github.io/<repo>/red-news.ics`.

No secrets or paid APIs are required. The workflow tests, builds, validates, commits only changed state/feed files, then deploys `public/` to Pages.

## Google Calendar subscription

Desktop browser only:

1. Open Google Calendar.
2. Beside **Other calendars**, click **+**.
3. Choose **From URL**.
4. Paste the public HTTPS `red-news.ics` URL.
5. Click **Add calendar**.

Use **From URL**, not **Import**; Import is a one-time copy. The feed must remain public. Google decides its polling interval.

## Notion Calendar compatibility

Notion Calendar currently has no direct field for an external HTTPS ICS/webcal subscription. Use Google as the supported intermediary:

1. Subscribe in Google Calendar with **Other calendars -> + -> From URL**.
2. In Notion Calendar, open **Settings -> Calendar accounts** and connect that same Google account.
3. Enable the subscribed RED NEWS calendar in the sidebar.

It is read-only and inherits Google's polling delay. This is not a fake direct Notion subscription.

## Troubleshooting

- Workflow source failure: prior published feed remains available; inspect Actions logs and retry next hour.
- No events: the quality filter may correctly find no qualifying current-week releases. The source response itself must still pass the minimum-size sanity check.
- Changed rule does not match: inspect the normalized title and add a focused test before changing regex.
- Google appears stale: verify the HTTPS file changed, then wait for Google's external-calendar polling; it cannot be forced by this project.
- Timezone change: edit `timezone` in `config/rules.json`; update the calendar metadata and UID documentation/tests if identity should follow that local date.

## Future Discord integration

Add a consumer that reads `EventStore.active_events()` and uses the same UIDs/state. Keep webhook delivery downstream from the core pipeline; ICS generation must remain independent. Do not store webhook URLs in the repository—use GitHub Actions secrets.
