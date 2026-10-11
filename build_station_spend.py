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
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from filings import (PRIMARIES, cache_files, corrections_applied,  # noqa: E402
                      find_cache, norm, party_of, scan, write_committees)


# A row is radio when it carries an explicit radio marker. Bare call signs are
# NOT matched here — they are ambiguous and handled separately.
RADIO = re.compile(r'\b(AM|FM|RADIO|ENTERCOM|AUDACY|IHEART|CUMULUS|TOWNSQUARE)\b')

# Station tokens found anywhere in the normalized name, so combined buys
# ("KARD-TV KTVE-TV") surface every station they name.
def stations_in(name, callset):
    """Return the set of known call signs appearing as tokens in `name`."""
    toks = set(re.split(r'[\s-]+', name))
    return {t for t in toks if t in callset}


PACE_FROM, PACE_TO = -104, 7      # weeks: two years out through the runoff
RECENT_DAYS = 365                 # the "buying now" window


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cache', help='path to .la_cache (default: auto-find)')
    ap.add_argument('--stations', default=os.path.join(HERE, 'data', 'stations.json'),
                    help='station reference file (call sign, DMA, owner)')
    ap.add_argument('--out', default=os.path.join(HERE, 'data', 'station_spend.json'))
    ap.add_argument('--top-committees', type=int, default=12,
                    help='how many buyers to keep per station and overall')
    return ap.parse_args(argv)


def builder(args, files):
    """Set up this build over `files`; returns add(row, year), which takes
    each filing row in turn, and finish(scanned, latest), which writes the
    output once every row has been seen."""

    stations = json.load(open(args.stations, encoding='utf-8'))
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
    by_day = defaultdict(float)                         # date -> $, statewide
    buyer_year = defaultdict(lambda: defaultdict(float))  # filer -> year -> $
    buyer_days = defaultdict(lambda: defaultdict(float))  # filer -> date -> $
    buyer_name = defaultdict(lambda: defaultdict(int))  # filer -> spelling -> n
    buyer_party = defaultdict(lambda: defaultdict(int))
    radio_excl = defaultdict(float)
    ambiguous = defaultdict(float)
    combined_total = 0.0
    combined_rows = 0
    today = time.strftime('%Y-%m-%d')
    # Every filer active in the last three years, TV buyer or not, so the
    # page can match the FCC political file's buyers to their state filer
    # (a campaign books time weeks before it reports paying for it).
    recent_from = int(today[:4]) - 2
    filer_name = defaultdict(Counter)
    filer_party = defaultdict(Counter)

    t0 = time.time()

    def add(r, yr):
        nonlocal combined_total, combined_rows
        if yr >= recent_from and r.get('filerNumber') and r.get('candidate'):
            filer_name[r['filerNumber']][r['candidate']] += 1
            if r.get('party'):
                filer_party[r['filerNumber']][r['party']] += 1
        raw = (r.get('contributor') or '').strip()
        if not raw:
            return
        n = norm(raw)
        hits = stations_in(n, callset)
        if not hits:
            return
        amt = float(r.get('amount') or 0)
        if amt <= 0:
            return
        fn = (r.get('filerNumber') or '').strip()
        if r.get('candidate'):
            buyer_name[fn][r['candidate']] += 1
        if r.get('party'):
            buyer_party[fn][r['party']] += 1

        if RADIO.search(n):
            for b in hits:
                radio_excl[base[b]] += amt / len(hits)
            return

        # bare call sign with no TV/network qualifier: ambiguous only
        # for calls that actually have a radio sister
        if len(hits) == 1:
            b = next(iter(hits))
            if n == b and b in ('WWL', 'KTAL'):
                ambiguous[base[b]] += amt

        if len(hits) > 1:
            combined_total += amt
            combined_rows += 1
        d = r.get('date') or ''
        if len(d) == 10 and d <= today:
            by_day[d] += amt
            if fn:
                buyer_days[fn][d] += amt
        share = amt / len(hits)
        for b in hits:
            call = base[b]
            spend[call] += share
            rows_n[call] += 1
            by_year[call][yr] += share
            if fn:
                filers[call].add(fn)
                by_buyer[call][fn] += share
                buyer_year[fn][yr] += share

    def finish(scanned, latest):
        def bname(fn):
            return max(buyer_name[fn].items(), key=lambda x: x[1])[0] if buyer_name[fn] else f'filer {fn}'

        def bparty(fn):
            filed = max(buyer_party[fn].items(), key=lambda x: x[1])[0] if buyer_party[fn] else None
            return party_of(filed, fn)

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
                'top_committees': [{'name': bname(fn), 'party': bparty(fn), 'filer': fn,
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

        # Pace: cumulative statewide TV dollars, week by week, from two years
        # before each governor's primary through its runoff. The running cycle
        # stops at the newest filing, so its line ends where the data does.
        through = date.fromisoformat(latest) if latest else date.today()
        cycles = []
        for cyc, pd in sorted(PRIMARIES.items()):
            primary = date.fromisoformat(pd)
            weeks = [0.0] * (PACE_TO - PACE_FROM + 1)
            for d, a in by_day.items():
                w = (date.fromisoformat(d) - primary).days // 7
                if PACE_FROM <= w <= PACE_TO:
                    weeks[w - PACE_FROM] += a
            last = min(PACE_TO, (through - primary).days // 7)
            if last < PACE_FROM:
                continue
            cum, run = [], 0.0
            for v in weeks[:last - PACE_FROM + 1]:
                run += v
                cum.append(round(run, 2))
            cycles.append({'year': cyc, 'primary': pd, 'complete': last == PACE_TO,
                           'cumulative': cum})

        # Buying now: committees' TV dollars over the trailing year of filings.
        since = (through - timedelta(days=RECENT_DAYS - 1)).isoformat()
        recent = []
        for fn, days in buyer_days.items():
            a = sum(v for d, v in days.items() if d >= since)
            if a > 0:
                recent.append({'name': bname(fn), 'party': bparty(fn), 'filer': fn, 'amount': round(a, 2),
                               'last_buy': max(d for d in days if d >= since)})
        recent.sort(key=lambda x: -x['amount'])

        doc = {
            'generated': time.strftime('%Y-%m-%d'),
            'source': 'Louisiana Ethics Administration expenditure filings via .la_cache',
            'rows_scanned': scanned,
            'data_through': latest or None,
            'years_covered': [min(years), max(years)],
            'years_missing': gaps,
            'total_spend': round(total, 2),
            'pace': {'weeks': [PACE_FROM, PACE_TO], 'cycles': cycles,
                     'note': 'cumulative TV dollars from every state committee, by week '
                             'relative to the governor\'s-race primary; includes the '
                             'legislative and local races on the same ballots'},
            'recent_buyers': {'since': since, 'through': latest or None,
                              'total': round(sum(b['amount'] for b in recent), 2),
                              'committees': len(recent), 'top': recent[:12]},
            'stations': out_stations,
            'markets': [{'name': k, 'rank': v['rank'], 'spend': round(v['spend'], 2),
                         'stations': v['stations'],
                         'share': round(v['spend'] / total, 4) if total else 0}
                        for k, v in sorted(markets.items(), key=lambda x: -x[1]['spend'])],
            'owners': [{'group': k, 'spend': round(v['spend'], 2), 'stations': v['stations'],
                        'share': round(v['spend'] / total, 4) if total else 0}
                       for k, v in sorted(owners.items(), key=lambda x: -x[1]['spend'])],
            'top_buyers': [{'name': bname(fn), 'party': bparty(fn), 'filer': fn, 'amount': round(a, 2),
                            'stations': len(buyer_stations[fn])} for fn, a in top_buyers],
            'caveats': {
                'radio_excluded': {k: round(v, 2) for k, v in sorted(radio_excl.items())},
                'ambiguous_bare_call': {k: round(v, 2) for k, v in sorted(ambiguous.items())},
                'combined_buys': {'amount': round(combined_total, 2), 'rows': combined_rows,
                                  'note': 'rows naming two stations; split evenly'},
                'party_corrections': corrections_applied(),
            },
        }
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        n_cm = write_committees(os.path.join(os.path.dirname(args.out), 'committees_tv.json'),
                                by_buyer, buyer_year, bname, bparty)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
        with open(os.path.join(os.path.dirname(args.out), 'filers.json'), 'w', encoding='utf-8') as f:
            # Most frequent spelling, ties to the alphabetically first, so the
            # file doesn't churn between runs.
            top = lambda c: min(c, key=lambda k: (-c[k], k))
            json.dump({fn: {'n': top(filer_name[fn]),
                            'p': party_of(top(filer_party[fn]) if filer_party[fn] else None, fn)}
                       for fn in sorted(filer_name)},
                      f, indent=0, ensure_ascii=False, sort_keys=True)

        print(f'Scanned {scanned:,} expenditure rows from {len(files)} files '
              f'({min(years)}–{max(years)}{", missing " + str(gaps) if gaps else ""}) '
              f'in {time.time()-t0:.0f}s')
        print(f'Total TV spend: ${total:,.0f} across {len(out_stations)} stations\n')
        print(f'{"station":<10} {"market":<18} {"spend":>13}  {"cmtes":>5}')
        for s in out_stations:
            print(f'{s["call"]:<10} {s["dma"][:18]:<18} ${s["spend"]:>12,.0f}  {s["committees"]:>5}')
        print('\nBy market:')
        for m in doc['markets']:
            print(f'  {m["name"][:22]:<22} ${m["spend"]:>12,.0f}  {m["share"]*100:>5.1f}%')
        print('\nBy owner group:')
        for o in doc['owners']:
            print(f'  {o["group"]:<10} ${o["spend"]:>12,.0f}  {o["share"]*100:>5.1f}%  '
                  f'({o["stations"]} stations)')
        print(f'\nExcluded as radio: ${sum(radio_excl.values()):,.0f}; '
              f'ambiguous bare call signs counted as TV: ${sum(ambiguous.values()):,.0f}')
        print(f'Wrote {args.out} and committees_tv.json ({n_cm:,} committees)')

    return add, finish


def main(argv=None):
    args = parse_args(argv)
    files = cache_files(find_cache(args.cache))
    add, finish = builder(args, files)
    finish(*scan(files, [add]))


if __name__ == '__main__':
    main()
