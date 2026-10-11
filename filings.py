"""
filings.py — reading the Louisiana expenditure filings, shared by the builders
================================================================================
build_station_spend.py (TV) and build_radio_spend.py (radio) both sum what
committees paid stations, from the same 1.48M rows of the la-campaign-finance
`.la_cache` NDJSON. What they share lives here, once: finding the cache,
reading it (scan(), which hands every row to each builder in a single pass),
normalizing vendor names, the party-label corrections, the
committee-detail writer, and the governor's-race calendar.

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
# Party comes from the filings' `party` field, which la-campaign-finance sets
# by matching the filer's name, then corrects by filer number from its
# la_party_corrections.json: a namesake's label (filer 1314, Judge Blair
# Downing Edwards, matched a Democratic official of the same name) or a
# publicly aligned committee left as OTH. That file is the one list both sites
# apply; fetch_cache.py syncs it here nightly as data/party_corrections.json,
# and party_of() applies the same rule in case a row predates the upstream
# retag. Corrections are added upstream, never here.
PARTY_FILE = os.path.join(HERE, 'data', 'party_corrections.json')


def load_party_corrections(path=PARTY_FILE):
    """filer -> {party, when, name, why}; empty (with a warning) if missing."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)['filers']
    except (OSError, ValueError, KeyError) as e:
        print(f'  WARNING: no party corrections ({e}); using filed labels as-is', file=sys.stderr)
        return {}


PARTY_CORRECTIONS = load_party_corrections()


def party_of(filed, filer=None, fixes=None):
    """The filed party after this filer's correction: `when: always` replaces
    it, `when: oth` fills it only where it is OTH (or missing)."""
    c = (PARTY_CORRECTIONS if fixes is None else fixes).get(str(filer or '').strip())
    if c and (c['when'] == 'always' or filed in (None, '', 'OTH')):
        return c['party']
    return filed


def corrections_applied():
    """The corrections, as echoed into each output's caveats."""
    return {'applied': {f: c['party'] for f, c in sorted(PARTY_CORRECTIONS.items())},
            'source': 'la-campaign-finance la_party_corrections.json (data/party_corrections.json); '
                      'each entry carries its public source'}


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
