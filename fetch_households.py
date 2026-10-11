#!/usr/bin/env python3
"""
fetch_households.py — Census household counts for every county in the markets
================================================================================
Nielsen's TV-household count for a market covers all of it, Texas, Arkansas
and Mississippi counties included, so dividing Louisiana committees' spending
by it understates what they pay per Louisiana household. This fetches the
Census Bureau's household count (ACS 5-year table B11001, total households)
for every county in data/county_dma.json, so the page can split each market
into its Louisiana and out-of-state shares.

    python3 fetch_households.py

Tries the newest ACS 5-year release first and falls back a year at a time.
api.census.gov needs no key at this volume (four requests). It is not
reachable from every network; the "Reference data" workflow runs this on
GitHub's runners and commits the result. Writes data/households.json.
Stdlib only.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)
STATES = {'LA': '22', 'TX': '48', 'AR': '05', 'MS': '28'}
TABLE = 'B11001_001E'      # households, total


class Unavailable(Exception):
    """The API has no such release (it answers some of those with an empty
    or HTML body rather than an error status)."""


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'louisiana-airwaves/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        if e.code in (204, 400, 404):
            raise Unavailable(f'HTTP {e.code}')
        raise
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise Unavailable(f'not JSON: {body[:160]!r}')


def main():
    counties = json.load(open(D('data', 'county_dma.json'), encoding='utf-8'))
    need = {STATES[c['st']] for c in counties.values()}
    this = time.gmtime().tm_year
    for year in range(this - 1, this - 5, -1):
        try:
            hh = {}
            for st in sorted(need):
                rows = get(f'https://api.census.gov/data/{year}/acs/acs5'
                           f'?get=NAME,{TABLE}&for=county:*&in=state:{st}')
                head = rows[0]
                for r in rows[1:]:
                    rec = dict(zip(head, r))
                    hh[rec['state'] + rec['county']] = int(rec[TABLE])
            break
        except Unavailable as e:
            print(f'  ACS {year} 5-year not available ({e}); trying {year - 1}')
    else:
        sys.exit('No ACS 5-year release found.')

    missing = sorted(f for f in counties if f not in hh)
    if missing:
        sys.exit(f'No household count for {missing}')
    doc = {'source': f'U.S. Census Bureau, American Community Survey {year - 4}-{year} 5-year '
                     f'estimates, table B11001 (total households)',
           'year': year,
           'counties': {f: hh[f] for f in sorted(counties)}}
    with open(D('data', 'households.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)
    tot = {}
    for fips, c in counties.items():
        k = (c['dma'], c['st'] == 'LA')
        tot[k] = tot.get(k, 0) + hh[fips]
    for dma in sorted({c['dma'] for c in counties.values()}):
        la, out = tot.get((dma, True), 0), tot.get((dma, False), 0)
        print(f'  {dma:28} Louisiana {la:>9,}  out of state {out:>9,}  ({la / (la + out):.0%} Louisiana)')
    print(f'Wrote data/households.json (ACS {year} 5-year, {len(counties)} counties)')


if __name__ == '__main__':
    main()
