"""
scan_runner.py — WhaleWatch staggered sector scanner

Scans ONE sector and stores the result in SQLite. Designed to be called by cron
one sector at a time across a quiet overnight window (AWST morning), so all 11
GICS sectors are freshly stored by the time you check mid-afternoon.

Usage:
    python3 scan_runner.py <batch_index>      # scan one sector by index 0-10
    python3 scan_runner.py all                # scan every sector sequentially (manual)

Trading-calendar guard: skips weekends. (Holiday handling: see TODO — add
pandas-market-calendars when you want full US holiday awareness.)
"""
import sys
from datetime import datetime, timezone

from sectors import SECTORS
import store


def is_trading_day():
    """
    Cheap guard: skip Saturday/Sunday. US market holidays still pass through here
    (a holiday scan just re-stores slightly stale bars — harmless, not wrong).
    TODO: pandas-market-calendars for true holiday/half-day awareness.
    """
    wd = datetime.now(timezone.utc).weekday()  # 0=Mon .. 6=Sun
    return wd < 5


def scan_one(batch_index):
    if batch_index < 0 or batch_index >= len(SECTORS):
        print(f"ERROR: batch_index {batch_index} out of range 0-{len(SECTORS)-1}")
        return False

    sector = SECTORS[batch_index]
    name = sector["name"]
    tickers = sector["tickers"]

    # Import the engine lazily so a missing-key/env problem surfaces clearly here.
    from core import analyze
    from options import build_options_signal

    results = []
    failed = []
    for t in tickers:
        try:
            r = analyze(t)
            r["options"] = build_options_signal(r)
            results.append(r)
        except Exception as e:
            # One bad ticker never kills the sector — log and move on.
            failed.append((t, str(e)[:80]))
            continue

    results.sort(key=lambda x: x.get("conviction", 0), reverse=True)
    ts = store.save_sector(name, batch_index, results)

    print(f"[{ts}] {name}: stored {len(results)} ok, {len(failed)} failed")
    if failed:
        for t, err in failed:
            print(f"    FAIL {t}: {err}")
    return True


def main():
    if len(sys.argv) < 2:
        print("usage: python3 scan_runner.py <batch_index|all>")
        sys.exit(1)

    store.init_db()

    if not is_trading_day():
        print("Not a trading day (weekend) — skipping scan.")
        sys.exit(0)

    arg = sys.argv[1]
    if arg == "all":
        for i in range(len(SECTORS)):
            scan_one(i)
    else:
        try:
            idx = int(arg)
        except ValueError:
            print(f"ERROR: '{arg}' is not a valid batch index or 'all'")
            sys.exit(1)
        scan_one(idx)


if __name__ == "__main__":
    main()
