"""
filings.py — reading the Louisiana expenditure filings, shared by the builders
================================================================================
build_station_spend.py (TV) and build_radio_spend.py (radio) both sum what
committees paid stations, from the same 1.48M rows of the la-campaign-finance
`.la_cache` NDJSON. What they share lives here, once: finding the cache,
reading it (scan(), which hands every row to each builder in a single pass),
normalizing vendor names, the party-label rules, the committee-detail
writer, and the governor's-race calendar.

Stdlib only.
"""
import glob
import gzip
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def find_cache(explicit=None):
    """Locate .la_cache: --cache, $LA_CACHE, then the usual sibling layouts."""
    if explicit:
        return explicit
    if os.environ.get('LA_CACHE'):
        return os.environ['LA_CACHE']
    for c in (os.path.join(HERE, '.la_cache'),   # fetch_cache.py's default
              os.path.join(HERE, '..', 'la-campaign-finance', '.la_cache'),
              os.path.join(HERE, '..', 'doombot50', 'la-campaign-finance', '.la_cache'),
              os.path.join(HERE, '..', '.la_cache')):
        if os.path.isdir(c):
            return c
    return os.path.join(HERE, '..', 'la-campaign-finance', '.la_cache')


def cache_files(cache):
    """The cache's expenditure files, oldest year first; exits if there are none."""
    files = sorted(glob.glob(os.path.join(cache, 'expenditures_yr*.json.gz')))
    if not files:
        sys.exit(f'No expenditures_yr*.json.gz under {cache!r}. '
                 f'Pass --cache <path> or set $LA_CACHE.')
    return files


def file_year(path):
    return int(re.search(r'yr(\d{4})', path).group(1))


def scan(files, handlers):
    """Read every expenditure row once, calling each handler(row, year).
    Returns (rows scanned, newest filed date). A handful of rows carry
    typo'd future dates, so a date after today never counts as the newest."""
    scanned, latest, today = 0, '', time.strftime('%Y-%m-%d')
    for path in files:
        yr = file_year(path)
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                scanned += 1
                d = r.get('date') or ''
                if latest < d <= today:
                    latest = d
                for h in handlers:
                    h(r, yr)
    return scanned, latest


# ── name normalization (mirrors build_vendor_factions.norm_vendor) ────────────
def norm(s):
    s = s.upper()
    s = re.sub(r"[.,'\"/()#]", ' ', s)
    s = re.sub(r"[^A-Z0-9 &-]", ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


# ── party labels ─────────────────────────────────────────────────────────────
# Party normally comes from the filing itself. But Louisiana files PACs and
# many candidates as "OTH", which tells a reader nothing about which side of a
# race bought the airtime — so for filers whose alignment is a matter of public
# record, the label is corrected here. Only filers filed as OTH are overridden;
# a filing that states REP or DEM is left alone. Each entry is an editorial
# call, listed explicitly so it can be audited or reverted.
PARTY_OVERRIDE = {
    # Republican Governors Association's Louisiana IE vehicle.
    'RGA (Republican Governors Association) Right Direction PAC': 'REP',
    # Democratic-aligned super PAC; ran the anti-Landry air war in 2023.
    'Gumbo PAC': 'DEM',
    # Elected to the state Senate as a Republican, switched to the Democratic
    # Party to run for governor in 2007 — the cycle this spending is from.
    'Walter J. Boasso': 'DEM',
    # Republican; former Secretary of State and Lieutenant Governor.
    'John L. (Jay) Dardenne': 'REP',
    # Democrat; former congressman and chairman of the Louisiana Democratic Party.
    'Claude (Buddy) Leach, Jr.': 'DEM',
}
# A filing that states the wrong party, corrected by filer number. Unlike
# the OTH overrides above, these replace what the committee itself filed, so
# each needs a public source.
PARTY_CORRECTION = {
    # Blair Downing Edwards, First Circuit Court of Appeal judge, ran as a
    # Republican for the open 1st District Supreme Court seat in the May 2026
    # closed GOP primary (WAFB, WBRZ, Louisiana Illuminator), but her
    # committee's reports are filed as DEM.
    '1314': 'REP',
}


def party_of(name, filed, filer=None):
    """Filed party: corrected outright for a filer in PARTY_CORRECTION, and
    otherwise only where the filing says OTH (or nothing)."""
    if filer in PARTY_CORRECTION:
        return PARTY_CORRECTION[filer]
    if filed in (None, '', 'OTH'):
        return PARTY_OVERRIDE.get(name, filed)
    return filed


def write_committees(path, by_buyer, buyer_year, bname, bparty, extra=None):
    """Per-committee detail for the committee pages: total, by year, by
    station (and anything else `extra(fn)` adds), keyed by filer number."""
    out = {}
    for fn, years in buyer_year.items():
        st = {c: round(m[fn], 2) for c, m in by_buyer.items() if fn in m}
        out[fn] = {'name': bname(fn), 'party': bparty(fn),
                   'total': round(sum(st.values()), 2),
                   'years': {str(y): round(v, 2) for y, v in sorted(years.items())},
                   'stations': dict(sorted(st.items(), key=lambda x: -x[1]))}
        if extra:
            out[fn].update(extra(fn))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=0, ensure_ascii=False, sort_keys=True)
    return len(out)


# ── governor's-race primaries ────────────────────────────────────────────────
# The first-round (open primary) date of each governor's race, the anchor the
# pace chart measures "weeks before the election" from. Past dates are the
# Secretary of State's own results data; 2027 is from the SoS 2027 elections
# calendar, which notes dates are subject to change by the legislature.
PRIMARIES = {
    2003: '2003-10-04', 2007: '2007-10-20', 2011: '2011-10-22',
    2015: '2015-10-24', 2019: '2019-10-12', 2023: '2023-10-14',
    2027: '2027-10-09',
}
GOV_YEARS = set(PRIMARIES)
