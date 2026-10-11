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

Reads the ACS table-based summary file for B11001 (one file, every
geography; the Census API now requires a key, the bulk file doesn't),
newest 5-year release first, falling back a year at a time. www2.census.gov
is not reachable from every network; the "Reference data" workflow runs
this on GitHub's runners and commits the result. Writes data/households.json.
Stdlib only.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)


class Unavailable(Exception):
    """No such release (yet)."""


BASE = 'https://www2.census.gov/programs-surveys/acs/summary_file/'


def listing(url):
    """The links in a www2.census.gov directory page."""
    req = urllib.request.Request(url, headers={'User-Agent': 'louisiana-airwaves/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            page = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            raise Unavailable(f'HTTP {e.code} for {url}')
        raise
    return re.findall(r'href="([^"?/][^"]*)"', page)


def find_table(year):
    """URL of the 5-year table-based summary file for B11001, found by
    walking the release's directory pages rather than assuming a layout:
    summary_file/<year>/ ... down to a file named like acsdt5y<year>-b11001.dat."""
    url = f'{BASE}{year}/'
    target = re.compile(rf'acs(dt)?5y{year}[-_]b11001\.(dat|txt)$', re.I)
    # At most four levels: <year>/table-based-SF/data/5YRData/<file>.
    for _ in range(4):
        links = listing(url)
        hit = [l for l in links if target.search(l)]
        if hit:
            return url + hit[0]
        sub = ([l for l in links if re.match(r'(table-based-sf|data|5yrdata|5-?year)/?$', l, re.I)]
               or [l for l in links if l.endswith('/') and '5' in l and 'y' in l.lower()])
        if not sub:
            raise Unavailable(f'no table-based 5-year folder under {url} (saw {links[:20]})')
        url += sub[0] if sub[0].endswith('/') else sub[0] + '/'
    raise Unavailable(f'B11001 file not found under {url}')


def summary_file(year, want):
    """Households for the `want` counties from the ACS table-based summary
    file: one pipe-delimited file per table, every geography, no API key.
    The API (api.census.gov) now refuses keyless requests."""
    url = find_table(year)
    print(f'  reading {url}')
    req = urllib.request.Request(url, headers={'User-Agent': 'louisiana-airwaves/1.0'})
    hh = {}
    with urllib.request.urlopen(req, timeout=300) as r:
        head = None
        for raw in r:
            line = raw.decode('utf-8', 'replace').rstrip('\r\n')
            if head is None:
                head = line.split('|')
                gi = next(i for i, h in enumerate(head) if h.upper() == 'GEO_ID')
                vi = next(i for i, h in enumerate(head) if re.fullmatch(r'B11001_E0*01', h, re.I))
                continue
            if not line.startswith('0500000US'):
                continue
            cols = line.split('|')
            fips = cols[gi][len('0500000US'):]
            if fips in want:
                hh[fips] = int(float(cols[vi]))
    return hh


def main():
    counties = json.load(open(D('data', 'county_dma.json'), encoding='utf-8'))
    this = time.gmtime().tm_year
    for year in range(this - 1, this - 5, -1):
        try:
            hh = summary_file(year, set(counties))
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
