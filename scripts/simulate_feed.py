#!/usr/bin/env python
import json
import sys
import time
import urllib.request
import urllib.error

FEED_PATH = "data/sample_stix_feed.json"
INGEST_URL = "http://localhost:5000/api/ingest"
DELAY = 0.1


def main():
    try:
        with open(FEED_PATH) as f:
            bundles = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Feed file not found: {FEED_PATH}")
        sys.exit(1)

    total = len(bundles)
    print(f"Loaded {total} bundles from {FEED_PATH}")
    print(f"Posting to {INGEST_URL} with {DELAY}s delay...\n")

    ingested_total = 0
    duplicate_total = 0
    error_total = 0

    for i, bundle in enumerate(bundles, 1):
        payload = json.dumps(bundle).encode("utf-8")
        req = urllib.request.Request(
            INGEST_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            ingested_total += result.get("ingested", 0)
            duplicate_total += result.get("duplicates", 0)
            error_total += result.get("errors", 0)
            tactic = bundle.get("metadata", {}).get("tactic", "unknown")
            raw = bundle.get("metadata", {}).get("raw_text", "")[:80]
            status = "OK" if result.get("errors", 0) == 0 else "ERR"
            print(
                f"  [{i:3d}/{total}] {status:3s}  tactic={tactic:24s}  "
                f"text={raw}"
            )
        except urllib.error.URLError as e:
            error_total += 1
            print(f"  [{i:3d}/{total}] ERR  connection failed: {e.reason}")
        except Exception as e:
            error_total += 1
            print(f"  [{i:3d}/{total}] ERR  {e}")

        time.sleep(DELAY)

    print(f"\n{'='*60}")
    print(f"Summary: {total} sent, {ingested_total} ingested, "
          f"{duplicate_total} duplicates, {error_total} errors")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
