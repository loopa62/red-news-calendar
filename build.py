#!/usr/bin/env python3
import argparse
import json
import logging
from pathlib import Path

from rednews.pipeline import PipelineError, run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Ashley RED NEWS ICS feed")
    parser.add_argument("--test", action="store_true", help="run source and output checks with verbose acceptance output")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M")
    try:
        result = run_pipeline()
    except PipelineError as exc:
        logging.error("Pipeline failed safely: %s", exc)
        return 1
    print(f"SOURCE EVENTS FOUND: {result['source_events']}")
    print(f"USD HIGH IMPACT: {result['usd_high_impact']}")
    print(f"QUALITY FILTER PASSED: {result['quality_filter_passed']}")
    print(f"NON-USD SUPER EVENTS: {result['non_usd_super_events']}")
    print(f"FINAL RED NEWS EVENTS: {result['final_red_news']}")
    print("DATE | WIB TIME | EVENT | CURRENCY | CLASSIFICATION")
    for event in sorted(result["events"], key=lambda item: item["datetime_local"]):
        dt = event["datetime_local"]
        print(f"{dt[:10]} | {dt[11:16]} | {event['event_name']} | {event['currency']} | {event['classification']}")
    if args.test:
        print(json.dumps(result["validation"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
