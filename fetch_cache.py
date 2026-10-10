#!/usr/bin/env python3
"""
fetch_cache.py — download the expenditure filings the builders read
================================================================================
Pulls `expenditures_yr<YEAR>.json.gz` for every year from 2000 through the
current one off the rolling `data-cache` release of doombot50/la-campaign-finance,
which that repo refreshes nightly from the Louisiana Ethics Administration.

    python3 fetch_cache.py                 # into ./.la_cache
    python3 fetch_cache.py --dest path/to/.la_cache

Assets are fetched by their direct release-download URL rather than through
api.github.com, so no token is needed and the 60-requests-an-hour anonymous
API limit never applies. A year with no asset (2008, absent upstream) is
skipped and reported; any other failure exits non-zero so a nightly rebuild
never publishes from a partial cache.

Stdlib only.
"""
import argparse
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = 'https://github.com/doombot50/la-campaign-finance/releases/download/data-cache'
FIRST_YEAR = 2000
RETRIES = 4   # per file, backoff 2s, 4s, 8s


def fetch(url, dest):
    """Download atomically: write .part, rename on success. Returns False on 404."""
    part = dest + '.part'
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'louisiana-airwaves/1.0'})
            with urllib.request.urlopen(req, timeout=120) as resp, open(part, 'wb') as out:
                while chunk := resp.read(1 << 16):
                    out.write(chunk)
            os.replace(part, dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            err = e
        except Exception as e:
            err = e
        if os.path.exists(part):
            os.remove(part)
        if attempt < RETRIES:
            print(f'    {os.path.basename(dest)}: attempt {attempt} failed ({err}); '
                  f'retrying in {2 ** attempt}s')
            time.sleep(2 ** attempt)
    sys.exit(f'FAILED {os.path.basename(dest)}: {err}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dest', default=os.path.join(HERE, '.la_cache'))
    args = ap.parse_args()
    os.makedirs(args.dest, exist_ok=True)

    # The release only carries a year once filings exist for it, so asking for
    # next year too would just 404. The current year is always tried.
    missing = []
    for yr in range(FIRST_YEAR, time.gmtime().tm_year + 1):
        name = f'expenditures_yr{yr}.json.gz'
        if fetch(f'{BASE}/{name}', os.path.join(args.dest, name)):
            print(f'  {name}  {os.path.getsize(os.path.join(args.dest, name)):,} bytes')
        else:
            missing.append(yr)
    print(f'Fetched into {args.dest}' + (f'; not in release: {missing}' if missing else ''))


if __name__ == '__main__':
    main()
