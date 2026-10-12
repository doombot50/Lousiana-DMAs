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

It also syncs `la_party_corrections.json`, the filer-keyed party corrections
both sites apply, into data/party_corrections.json (committed with the
nightly rebuild). If the release doesn't carry it, or it doesn't parse, the
committed copy stays.

For the races page it also fetches, into the same cache, the finance site's
per-filer totals (`la_filer_index.json.gz`, from the release) and four files
that repo commits: the Secretary of State candidacy history, the name-to-filer
lookup, certified cash on hand from the annual reports, and the "does money
win" rates. These are optional: one that can't be fetched is reported and
the races page goes without it.

Stdlib only.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = 'https://github.com/doombot50/la-campaign-finance/releases/download/data-cache'
FIRST_YEAR = 2000
RETRIES = 4   # per file, backoff 2s, 4s, 8s
RAW = 'https://raw.githubusercontent.com/doombot50/la-campaign-finance/main'
# Inputs to build_races_page.py: (url, file name in the cache).
FINANCE = [(f'{BASE}/la_filer_index.json.gz', 'la_filer_index.json.gz'),
           (f'{RAW}/la_candidacies_raw.json.gz', 'la_candidacies_raw.json.gz'),
           (f'{RAW}/la_filer_lookup.json', 'la_filer_lookup.json'),
           (f'{RAW}/ethics_coh_cache.json', 'ethics_coh_cache.json'),
           (f'{RAW}/la_money_wins.json', 'la_money_wins.json')]


def fetch(url, dest, required=True):
    """Download atomically: write .part, rename on success. Returns False on
    404, and on any failure when not `required`."""
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
    if not required:
        print(f'  {os.path.basename(dest)}: FAILED ({err}); going without it')
        return False
    sys.exit(f'FAILED {os.path.basename(dest)}: {err}')


def sync_party_corrections(dest=os.path.join(HERE, 'data', 'party_corrections.json')):
    """Replace data/party_corrections.json with the release's copy, keeping
    the committed one when the asset is missing or malformed."""
    tmp = dest + '.new'
    if not fetch(f'{BASE}/la_party_corrections.json', tmp):
        print('  la_party_corrections.json not in release; keeping the committed copy')
        return
    try:
        with open(tmp, encoding='utf-8') as f:
            n = len(json.load(f)['filers'])
    except (ValueError, KeyError, TypeError) as e:
        os.remove(tmp)
        print(f'  la_party_corrections.json unreadable ({e}); keeping the committed copy')
        return
    os.replace(tmp, dest)
    print(f'  party_corrections.json  {n} filer(s)')


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
    sync_party_corrections()
    for url, name in FINANCE:
        if fetch(url, os.path.join(args.dest, name), required=False):
            print(f'  {name}  {os.path.getsize(os.path.join(args.dest, name)):,} bytes')
        else:
            print(f'  {name}: not available')


if __name__ == '__main__':
    main()
