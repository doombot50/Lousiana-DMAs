#!/usr/bin/env python3
"""
build_station_spend.py — per-station TV ad dollars from LA expenditure filings
================================================================================
Reads the campaign-finance repo's .la_cache expenditure NDJSON (same source the
vendor-factions graph uses) and sums what Louisiana political committees paid
each television station, then rolls that up by market, by owner, and by buyer.

    python3 build_station_spend.py                     # auto-finds the cache
    python3 build_station_spend.py --cache path/to/.la_cache
    LA_CACHE=path/to/.la_cache python3 build_station_spend.py

Writes data/station_spend.json. Stdlib only.

Why this isn't a one-line grep
------------------------------
Three things make the naive sum wrong, and each is handled explicitly:

1. **Spelling variants.** One station is filed 15-30 ways — `KADN`, `KADN-TV`,
   `KADN - TV`, `KADN TV`, `KADN-FOX`, `KADN-TV CHANNEL 15`. All fold to the
   station's canonical call sign.

2. **Radio sisters.** WWL and KTAL each share a call sign with a radio station
   (WWL-AM/FM, KTAL-FM). A row explicitly marked radio (`WWL-AM`, `WWL RADIO`,
   `KTAL-FM`) is excluded from the TV total and reported separately. Rows
   carrying the *bare* call sign are genuinely ambiguous; they are counted as
   TV and the amount is disclosed in `ambiguous_bare_call` so a reader can
   adjust the figure rather than having to trust it.

3. **Combined buys.** A few rows name two stations at once (`KARD-TV KTVE-TV`,
   `WGMB WVLA-TV`) — co-owned sisters invoiced together. The amount is split
   evenly across the named stations rather than dumped on whichever sorts
   first, and the total so split is reported in `combined_buys`.

Contributions are a separate file; only expenditures are read here. Amounts are
nominal dollars, not inflation-adjusted.
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


def find_cache(explicit=None):
    """Locate .la_cache: --cache, $LA_CACHE, then the usual sibling layouts."""
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


# ── name normalization (mirrors build_vendor_factions.norm_vendor) ────────────
def norm(s):
    s = s.upper()
    s = re.sub(r"[.,'\"/()#]", ' ', s)
    s = re.sub(r"[^A-Z0-9 &-]", ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


# A row is radio when it carries an explicit radio marker. Bare call signs are
# NOT matched here — they are ambiguous and handled separately.
RADIO = re.compile(r'\b(AM|FM|RADIO|ENTERCOM|AUDACY|IHEART|CUMULUS|TOWNSQUARE)\b')

# Station tokens found anywhere in the normalized name, so combined buys
# ("KARD-TV KTVE-TV") surface every station they name.
def stations_in(name, callset):
    """Return the set of known call signs appearing as tokens in `name`."""
    toks = set(re.split(r'[\s-]+', name))
    return {t for t in toks if t in callset}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cache', help='path to .la_cache (default: auto-find)')
    ap.add_argument('--stations', default=os.path.join(HERE, 'data', 'stations.json'),
                    help='station reference file (call sign, DMA, owner)')
    ap.add_argument('--out', default=os.path.join(HERE, 'data', 'station_spend.json'))
    ap.add_argument('--top-committees', type=int, default=12,
                    help='how many buyers to keep per station and overall')
    args = ap.parse_args()

    cache = find_cache(args.cache)
    files = sorted(glob.glob(os.path.join(cache, 'expenditures_yr*.json.gz')))
    if not files:
        sys.exit(f'No expenditures_yr*.json.gz under {cache!r}. '
                 f'Pass --cache <path> or set $LA_CACHE.')

    stations = json.load(open(args.stations, encoding='utf-8'))
    meta = {s['call']: s for s in stations}
    # Filings use the base call sign; our reference uses broadcast names
    # (WWL-TV, KLAF-LD). Map the filed token back to the reference entry.
    base = {}
    for s in stations:
        b = re.split(r'-', s['call'])[0]
        base[b] = s['call']
    callset = set(base)

    years = sorted(int(re.search(r'yr(\d{4})', f).group(1)) for f in files)
    gaps = [y for y in range(min(years), max(years) + 1) if y not in years]

    spend = defaultdict(float)                    # call -> $
    rows_n = defaultdict(int)
    filers = defaultdict(set)
    by_year = defaultdict(lambda: defaultdict(float))   # call -> year -> $
    by_buyer = defaultdict(lambda: defaultdict(float))  # call -> filer -> $
    buyer_name = defaultdict(lambda: defaultdict(int))  # filer -> spelling -> n
    buyer_party = defaultdict(lambda: defaultdict(int))
    radio_excl = defaultdict(float)
    ambiguous = defaultdict(float)
    combined_total = 0.0
    combined_rows = 0
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
                hits = stations_in(n, callset)
                if not hits:
                    continue
                amt = float(r.get('amount') or 0)
                if amt <= 0:
                    continue
                fn = (r.get('filerNumber') or '').strip()
                if r.get('candidate'):
                    buyer_name[fn][r['candidate']] += 1
                if r.get('party'):
                    buyer_party[fn][r['party']] += 1

                if RADIO.search(n):
                    for b in hits:
                        radio_excl[base[b]] += amt / len(hits)
                    continue

                # bare call sign with no TV/network qualifier: ambiguous only
                # for calls that actually have a radio sister
                if len(hits) == 1:
                    b = next(iter(hits))
                    if n == b and b in ('WWL', 'KTAL'):
                        ambiguous[base[b]] += amt

                if len(hits) > 1:
                    combined_total += amt
                    combined_rows += 1
                share = amt / len(hits)
                for b in hits:
                    call = base[b]
                    spend[call] += share
                    rows_n[call] += 1
                    by_year[call][yr] += share
                    if fn:
                        filers[call].add(fn)
                        by_buyer[call][fn] += share

    def bname(fn):
        return max(buyer_name[fn].items(), key=lambda x: x[1])[0] if buyer_name[fn] else f'filer {fn}'

    def bparty(fn):
        return max(buyer_party[fn].items(), key=lambda x: x[1])[0] if buyer_party[fn] else None

    out_stations = []
    for s in stations:
        c = s['call']
        yrs = {str(y): round(v, 2) for y, v in sorted(by_year[c].items()) if v}
        tops = sorted(by_buyer[c].items(), key=lambda x: -x[1])[:args.top_committees]
        out_stations.append({
            'call': c,
            'network': s['network'],
            'dma': s['dma'],
            'dma_rank_2024_25': s['dma_rank_2024_25'],
            'owner': s['owner'],
            'owner_group': s['owner_group'],
            'spend': round(spend[c], 2),
            'rows': rows_n[c],
            'committees': len(filers[c]),
            'first_year': min((int(y) for y in yrs), default=None),
            'last_year': max((int(y) for y in yrs), default=None),
            'by_year': yrs,
            'top_committees': [{'name': bname(fn), 'party': bparty(fn),
                                'amount': round(a, 2)} for fn, a in tops],
        })
    out_stations.sort(key=lambda x: -x['spend'])

    markets = defaultdict(lambda: {'spend': 0.0, 'stations': 0})
    owners = defaultdict(lambda: {'spend': 0.0, 'stations': 0})
    for s in out_stations:
        m = markets[s['dma']]
        m['spend'] += s['spend']
        m['stations'] += 1
        m['rank'] = s['dma_rank_2024_25']
        o = owners[s['owner_group']]
        o['spend'] += s['spend']
        o['stations'] += 1

    all_buyers = defaultdict(float)
    buyer_stations = defaultdict(set)
    for c, m in by_buyer.items():
        for fn, a in m.items():
            all_buyers[fn] += a
            buyer_stations[fn].add(c)
    top_buyers = sorted(all_buyers.items(), key=lambda x: -x[1])[:args.top_committees * 2]

    total = sum(spend.values())
    doc = {
        'generated': time.strftime('%Y-%m-%d'),
        'source': 'Louisiana Ethics Administration expenditure filings via .la_cache',
        'rows_scanned': scanned,
        'years_covered': [min(years), max(years)],
        'years_missing': gaps,
        'total_spend': round(total, 2),
        'stations': out_stations,
        'markets': [{'name': k, 'rank': v['rank'], 'spend': round(v['spend'], 2),
                     'stations': v['stations'],
                     'share': round(v['spend'] / total, 4) if total else 0}
                    for k, v in sorted(markets.items(), key=lambda x: -x[1]['spend'])],
        'owners': [{'group': k, 'spend': round(v['spend'], 2), 'stations': v['stations'],
                    'share': round(v['spend'] / total, 4) if total else 0}
                   for k, v in sorted(owners.items(), key=lambda x: -x[1]['spend'])],
        'top_buyers': [{'name': bname(fn), 'party': bparty(fn), 'amount': round(a, 2),
                        'stations': len(buyer_stations[fn])} for fn, a in top_buyers],
        'caveats': {
            'radio_excluded': {k: round(v, 2) for k, v in sorted(radio_excl.items())},
            'ambiguous_bare_call': {k: round(v, 2) for k, v in sorted(ambiguous.items())},
            'combined_buys': {'amount': round(combined_total, 2), 'rows': combined_rows,
                              'note': 'rows naming two stations; split evenly'},
        },
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)

    print(f'Scanned {scanned:,} expenditure rows from {len(files)} files '
          f'({min(years)}–{max(years)}{", missing " + str(gaps) if gaps else ""}) '
          f'in {time.time()-t0:.0f}s')
    print(f'Total TV spend: ${total:,.0f} across {len(out_stations)} stations\n')
    print(f'{"station":<10} {"market":<18} {"spend":>13}  {"cmtes":>5}')
    for s in out_stations:
        print(f'{s["call"]:<10} {s["dma"][:18]:<18} ${s["spend"]:>12,.0f}  {s["committees"]:>5}')
    print(f'\nBy market:')
    for m in doc['markets']:
        print(f'  {m["name"][:22]:<22} ${m["spend"]:>12,.0f}  {m["share"]*100:>5.1f}%')
    print(f'\nBy owner group:')
    for o in doc['owners']:
        print(f'  {o["group"]:<10} ${o["spend"]:>12,.0f}  {o["share"]*100:>5.1f}%  '
              f'({o["stations"]} stations)')
    print(f'\nExcluded as radio: ${sum(radio_excl.values()):,.0f}; '
          f'ambiguous bare call signs counted as TV: ${sum(ambiguous.values()):,.0f}')
    print(f'Wrote {args.out}')


if __name__ == '__main__':
    main()
