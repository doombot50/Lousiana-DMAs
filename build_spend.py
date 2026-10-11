#!/usr/bin/env python3
"""
build_spend.py — the TV and radio spend data in one pass over the filings
================================================================================
Runs build_station_spend.py and build_radio_spend.py together, reading the
1.48M expenditure rows once and handing each row to both, instead of each
script reading them separately. Same outputs as running the two in turn:
data/station_spend.json, data/committees_tv.json, data/filers.json,
data/radio_spend.json and data/committees_radio.json.

    python3 build_spend.py                     # auto-finds the cache
    python3 build_spend.py --cache path/to/.la_cache

Stdlib only.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_radio_spend  # noqa: E402
import build_station_spend  # noqa: E402
from filings import cache_files, find_cache, scan  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cache', help='path to .la_cache (default: auto-find)')
    args = ap.parse_args()
    extra = ['--cache', args.cache] if args.cache else []
    files = cache_files(find_cache(args.cache))
    t0 = time.time()
    tv_add, tv_finish = build_station_spend.builder(build_station_spend.parse_args(extra), files)
    ra_add, ra_finish = build_radio_spend.builder(build_radio_spend.parse_args(extra), files)
    scanned, latest = scan(files, [tv_add, ra_add])
    print(f'Read {scanned:,} rows once for both builds in {time.time() - t0:.0f}s\n')
    tv_finish(scanned, latest)
    print()
    ra_finish(scanned, latest)


if __name__ == '__main__':
    main()
