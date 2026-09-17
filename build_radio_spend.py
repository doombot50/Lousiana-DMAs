#!/usr/bin/env python3
"""
build_radio_spend.py — per-station radio ad dollars from LA expenditure filings
================================================================================
The radio sibling of build_station_spend.py. Same source (.la_cache expenditure
NDJSON), different problem: radio is ~300 stations splitting a tenth of the TV
money, so the analysis is about WHO each buy reaches, not where it lands.

    python3 build_radio_spend.py                     # auto-finds the cache
    python3 build_radio_spend.py --cache path/to/.la_cache

Writes data/radio_spend.json. Stdlib only.

Why radio needs its own matcher
-------------------------------
Four-letter call signs collide with ordinary English, and radio has ten times
as many of them as TV. A bare `\b[KW][A-Z]{3}\b` regex over these filings
returns Total WINE, Smoothie KING Center, Last WORD Strategies, Ryan WEST,
KYLE Ardoin and KIRK Talbot as "radio stations" — together a seven-figure
phantom. Three rules keep that out:

1. **Allowlist, not pattern.** A row counts only if its call sign appears in
   data/radio_stations.json (the verified reference) or carries an explicit
   band marker (-AM/-FM/RADIO). Nothing is matched on shape alone.
2. **Marker or short name.** For an allowlisted call with no band marker, the
   vendor name must be short (<= 3 tokens). "KBON" is a station; "KIRK TALBOT
   FOR SHERIFF" is a person, even though KIRK looks like a call sign.
3. **TV sisters stay with TV.** WWL and KTAL share call signs with television
   stations, and the Airwaves page already counts their bare-call rows as TV.
   Only rows explicitly marked radio (`WWL-AM`, `KTAL-FM`) are counted here, so
   the two pages never double-count the same dollar.

AM/FM simulcasts fold into one station: WYLD-AM (gospel) and WYLD-FM (urban AC)
are one line, because the filings rarely distinguish them and campaigns buy the
cluster. The `bands` field records which were named.
"""
import argparse
import glob
import gzip
import json
import os
import re
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# Call signs that are also television stations — see rule 3 above.
TV_SISTERS = {'WWL', 'KTAL'}
GOV_YEARS = {2003, 2007, 2011, 2015, 2019, 2023}


def find_cache(explicit=None):
    if explicit:
        return explicit
    if os.environ.get('LA_CACHE'):
        return os.environ['LA_CACHE']
    for c in (os.path.join(HERE, '..', 'la-campaign-finance', '.la_cache'),
              os.path.join(HERE, '..', 'doombot50', 'la-campaign-finance', '.la_cache'),
              os.path.join(HERE, '..', '.la_cache')):
        if os.path.isdir(c):
            return c
    return os.path.join(HERE, '..', 'la-campaign-finance', '.la_cache')


def norm(s):
    s = s.upper()
    s = re.sub(r"[.,'\"/()#]", ' ', s)
    s = re.sub(r"[^A-Z0-9 &-]", ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


CALL = re.compile(r'\b([KW][A-Z]{3})\b')
BAND = re.compile(r'\b([KW][A-Z]{3})\s*-?\s*(AM|FM)\b')
RADIO_WORD = re.compile(r'\b(RADIO|BROADCAST(?:ING)?)\b')
# Louisiana files most PACs as OTH; see the TV build for the same treatment.
PARTY_OVERRIDE = {
    'RGA (Republican Governors Association) Right Direction PAC': 'REP',
    'Gumbo PAC': 'DEM',
    'Walter J. Boasso': 'DEM',
    'John L. (Jay) Dardenne': 'REP',
    'Claude (Buddy) Leach, Jr.': 'DEM',
}


def party_of(name, filed):
    if filed in (None, '', 'OTH'):
        return PARTY_OVERRIDE.get(name, filed)
    return filed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cache')
    ap.add_argument('--stations', default=os.path.join(HERE, 'data', 'radio_stations.json'))
    ap.add_argument('--out', default=os.path.join(HERE, 'data', 'radio_spend.json'))
    ap.add_argument('--top', type=int, default=14, help='buyers to keep per list')
    args = ap.parse_args()

    cache = find_cache(args.cache)
    files = sorted(glob.glob(os.path.join(cache, 'expenditures_yr*.json.gz')))
    if not files:
        sys.exit(f'No expenditures_yr*.json.gz under {cache!r}. Pass --cache or set $LA_CACHE.')

    ref = {s['call']: s for s in json.load(open(args.stations, encoding='utf-8'))}
    known = set(ref)

    spend = defaultdict(float)
    rows_n = defaultdict(int)
    filers = defaultdict(set)
    bands = defaultdict(set)
    by_year = defaultdict(lambda: defaultdict(float))
    by_buyer = defaultdict(lambda: defaultdict(float))
    buyer_cat = defaultdict(lambda: defaultdict(float))   # filer -> category -> $
    buyer_name = defaultdict(lambda: defaultdict(int))
    buyer_party = defaultdict(lambda: defaultdict(int))
    unclassified = defaultdict(float)                      # station-shaped, not in ref
    rejected_collisions = defaultdict(float)               # kept for disclosure
    tv_sister_radio = defaultdict(float)
    year_tot = defaultdict(float)
    scanned = 0

    t0 = time.time()
    for path in files:
        yr = int(re.search(r'yr(\d{4})', path).group(1))
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                scanned += 1
                raw = (r.get('contributor') or '').strip()
                if not raw:
                    continue
                n = norm(raw)
                calls = set(CALL.findall(n))
                if not calls:
                    continue
                amt = float(r.get('amount') or 0)
                if amt <= 0:
                    continue
                banded = {c: b for c, b in BAND.findall(n)}
                marked = bool(banded) or bool(RADIO_WORD.search(n))
                short = len(n.split()) <= 3

                hits = set()
                for c in calls:
                    if c in TV_SISTERS:
                        # only an explicit radio marker pulls these away from TV
                        if c in banded or RADIO_WORD.search(n):
                            tv_sister_radio[c] += amt
                            hits.add(c)
                        continue
                    if c in known and (marked or short):
                        hits.add(c)
                    elif marked and c not in known:
                        unclassified[c] += amt
                    elif not marked and not short:
                        rejected_collisions[c] += amt

                if not hits:
                    continue
                share = amt / len(hits)
                fn = (r.get('filerNumber') or '').strip()
                if r.get('candidate'):
                    buyer_name[fn][r['candidate']] += 1
                if r.get('party'):
                    buyer_party[fn][r['party']] += 1
                for c in hits:
                    spend[c] += share
                    rows_n[c] += 1
                    by_year[c][yr] += share
                    year_tot[yr] += share
                    if c in banded:
                        bands[c].add(banded[c])
                    if fn:
                        filers[c].add(fn)
                        by_buyer[c][fn] += share
                        cat = ref[c]['category'] if c in ref else 'Unclassified'
                        buyer_cat[fn][cat] += share

    def bname(fn):
        return max(buyer_name[fn].items(), key=lambda x: x[1])[0] if buyer_name[fn] else f'filer {fn}'

    def bparty(fn):
        filed = max(buyer_party[fn].items(), key=lambda x: x[1])[0] if buyer_party[fn] else None
        return party_of(bname(fn), filed)

    stations = []
    tail_extra = 0.0
    tail_calls = 0
    for c, amt in spend.items():
        if c not in ref:
            # a TV-sister radio row or anything else without a reference entry
            # belongs in the disclosed tail, not in a format category
            tail_extra += amt
            tail_calls += 1
            continue
        meta = ref.get(c, {})
        tops = sorted(by_buyer[c].items(), key=lambda x: -x[1])[:5]
        stations.append({
            'call': c, 'city': meta.get('city'), 'market': meta.get('market'),
            'format': meta.get('format'), 'category': meta.get('category', 'Unclassified'),
            'owner': meta.get('owner'), 'bands': sorted(bands[c]),
            'spend': round(amt, 2), 'rows': rows_n[c], 'committees': len(filers[c]),
            'avg_buy': round(amt / rows_n[c], 2) if rows_n[c] else 0,
            'by_year': {str(y): round(v, 2) for y, v in sorted(by_year[c].items()) if v},
            'top_committees': [{'name': bname(f), 'party': bparty(f), 'amount': round(a, 2)}
                               for f, a in tops],
        })
    stations.sort(key=lambda s: -s['spend'])
    classified = sum(s['spend'] for s in stations)
    tail_amt = sum(unclassified.values()) + tail_extra
    tail_n = len(unclassified) + tail_calls
    # Every dollar this build can identify as radio, classified or not. Category
    # shares are quoted against this, so the tail dilutes them honestly instead
    # of vanishing from the denominator.
    total = classified + tail_amt

    cats = defaultdict(lambda: {'spend': 0.0, 'stations': 0, 'rows': 0, 'committees': set()})
    owners = defaultdict(lambda: {'spend': 0.0, 'stations': 0})
    for s in stations:
        k = cats[s['category']]
        k['spend'] += s['spend']; k['stations'] += 1; k['rows'] += s['rows']
        k['committees'] |= filers[s['call']]
        o = owners[s['owner'] or 'Unknown']
        o['spend'] += s['spend']; o['stations'] += 1

    all_b = defaultdict(float)
    for c, m in by_buyer.items():
        for fn, a in m.items():
            all_b[fn] += a
    top_buyers = []
    for fn, a in sorted(all_b.items(), key=lambda x: -x[1])[:args.top]:
        mix = sorted(buyer_cat[fn].items(), key=lambda x: -x[1])
        top_buyers.append({'name': bname(fn), 'party': bparty(fn), 'amount': round(a, 2),
                           'stations': sum(1 for c in by_buyer if fn in by_buyer[c]),
                           'mix': [{'category': k, 'amount': round(v, 2)} for k, v in mix]})

    years = sorted(year_tot)
    doc = {
        'generated': time.strftime('%Y-%m-%d'),
        'source': 'Louisiana Ethics Administration expenditure filings via .la_cache',
        'rows_scanned': scanned,
        'years_covered': [min(years), max(years)] if years else [],
        'years_missing': [y for y in range(min(years), max(years) + 1) if y not in year_tot] if years else [],
        'total_spend': round(total, 2),
        'gov_year_share': round(sum(v for y, v in year_tot.items() if y in GOV_YEARS) / total, 4) if total else 0,
        'by_year': {str(y): round(year_tot[y], 2) for y in years},
        'stations': stations,
        'classified_spend': round(classified, 2),
        'unclassified_tail': {'amount': round(tail_amt, 2), 'stations': tail_n,
                              'note': 'identifiable as radio by an explicit band marker, but not '
                                      'in the verified station reference — a long tail of small '
                                      'stations, the largest about $55K'},
        'categories': [{'category': k, 'spend': round(v['spend'], 2), 'stations': v['stations'],
                        'rows': v['rows'], 'committees': len(v['committees']),
                        'avg_buy': round(v['spend'] / v['rows'], 2) if v['rows'] else 0,
                        'share': round(v['spend'] / total, 4) if total else 0}
                       for k, v in sorted(cats.items(), key=lambda x: -x[1]['spend'])]
                      + [{'category': 'Unclassified (long tail)', 'spend': round(tail_amt, 2),
                          'stations': tail_n, 'rows': 0, 'committees': 0, 'avg_buy': 0,
                          'share': round(tail_amt / total, 4) if total else 0}],
        'owners': [{'owner': k, 'spend': round(v['spend'], 2), 'stations': v['stations'],
                    'share': round(v['spend'] / total, 4) if total else 0}
                   for k, v in sorted(owners.items(), key=lambda x: -x[1]['spend'])],
        'top_buyers': top_buyers,
        'caveats': {
            'classified_share': round(classified / total, 4) if total else 0,
            'unclassified_station_shaped': {'amount': round(tail_amt, 2),
                                            'calls': tail_n,
                                            'note': 'in the total and shown as its own bucket, but '
                                                    'absent from the format breakdown'},
            'name_collisions_rejected': {'amount': round(sum(rejected_collisions.values()), 2),
                                         'examples': sorted(rejected_collisions,
                                                            key=lambda c: -rejected_collisions[c])[:10],
                                         'note': 'four-letter words that look like call signs '
                                                 '(Total WINE, Smoothie KING) — correctly excluded'},
            'tv_sister_radio_rows': {k: round(v, 2) for k, v in sorted(tv_sister_radio.items())},
            'party_overrides': PARTY_OVERRIDE,
        },
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(doc, open(args.out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

    print(f'Scanned {scanned:,} rows in {time.time()-t0:.0f}s')
    print(f'Radio total: ${total:,.0f} across {len(stations)} stations '
          f'({doc["caveats"]["classified_share"]*100:.0f}% of dollars classified)')
    print(f'Governor-year share: {doc["gov_year_share"]*100:.0f}%\n')
    print(f'{"category":24s} {"spend":>11s} {"share":>6s} {"stns":>5s} {"avg buy":>9s}')
    for c in doc['categories']:
        print(f'{c["category"]:24s} ${c["spend"]:>10,.0f} {c["share"]*100:>5.1f}% '
              f'{c["stations"]:>5} ${c["avg_buy"]:>8,.0f}')
    print(f'\nExcluded — name collisions: ${sum(rejected_collisions.values()):,.0f}; '
          f'unclassified station-shaped: ${sum(unclassified.values()):,.0f}')
    print(f'Wrote {args.out}')


if __name__ == '__main__':
    main()
