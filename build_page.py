#!/usr/bin/env python3
"""
build_page.py — assemble the Louisiana Airwaves page from data/ + template
================================================================================
One source, two outputs, because the page ships to two places with different
requirements:

  index.html     a COMPLETE standalone document — doctype, charset, viewport,
                 social-preview metadata. This is what GitHub Pages serves at
                 airwaves.charliestephens.xyz. Without the doctype browsers fall
                 into quirks mode, and without the viewport meta the page renders
                 at desktop width on phones.
  artifact.html  the same page as a BODY FRAGMENT, because the Claude Artifact
                 publisher supplies its own <head> and wrapping a second one
                 inside it produces malformed nesting.

Keeping both generated from page.template.html means the two can't drift.

    python3 build_page.py

Reads data/station_spend.json (money), data/stations.json (station reference),
data/map_paths.json (projected parish geometry). Stdlib only.
"""
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)
sys.path.insert(0, D('fcc'))
from filings import GOV_YEARS  # noqa: E402
from markets import BY_NAME, BY_TOPO, MARKETS  # noqa: E402
from page_shell import publish  # noqa: E402
from prose import money, money_words, series, words  # noqa: E402
from summary import fcc_summary  # noqa: E402

SITE_URL = 'https://airwaves.charliestephens.xyz/'
# Each governor's race, for the copy's "the 2019 Edwards–Rispone runoff".
RACES = {2003: 'Blanco–Jindal runoff', 2007: 'Jindal first-round win', 2011: 'Jindal re-election',
         2015: 'Edwards–Vitter runoff', 2019: 'Edwards–Rispone runoff', 2023: 'Landry first-round win'}
# The outside groups the copy names as the 2019 and 2023 air war, by filer.
OUTSIDE = {'6034': "RGA's Right Direction PAC", '3354': 'Gumbo PAC', '2820': "The Fund for Louisiana's Future"}


def facts(spend):
    """The figures the page's written copy quotes, from the data (see prose.py)."""
    total, (lo, _) = spend['total_spend'], spend['years_covered']
    per_year = defaultdict(float)
    for st in spend['stations']:
        for y, v in st['by_year'].items():
            per_year[int(y)] += v
    this_year = int(spend['data_through'][:4])
    gov_done = [y for y in sorted(GOV_YEARS) if y < this_year and y in per_year]
    peak = max(per_year, key=per_year.get)
    # How many of the quietest years it takes to add up to the peak year.
    quiet, acc = 0, 0.0
    for v in sorted(v for y, v in per_year.items() if y != peak):
        if acc + v >= per_year[peak]:
            break
        acc, quiet = acc + v, quiet + 1
    n_st = len(spend['stations'])
    own = {o['group']: o for o in spend['owners']}
    nex, gray = own['nexstar'], own['gray']
    b1, b2 = spend['top_buyers'][:2]
    outside = {b['filer']: b for b in spend['top_buyers'] if b['filer'] in OUTSIDE}
    reach = sorted(outside[f]['stations'] for f in OUTSIDE if f in outside)
    gap = spend['years_missing'][0] if spend['years_missing'] else None
    near = [y for y in (gap - 2, gap - 1, gap + 1, gap + 2) if y in per_year and y not in GOV_YEARS][:2] if gap else []
    return {
        'tv_total': money_words(total), 'tv_since': lo,
        'gov_years': ', '.join(map(str, gov_done)),
        'peak_race': f"{peak} {RACES[peak]}" if peak in RACES else str(peak),
        'peak_amount': money(per_year[peak]), 'quiet_years': words(quiet),
        'nex_n': words(nex['stations']), 'gray_n': words(gray['stations']), 'stations_n': words(n_st),
        'nex_most': ' — the most of any group —' if nex['stations'] == max(o['stations'] for o in own.values()) else '',
        'nex_share': f"{nex['share'] * 100:.1f}%", 'gray_share': f"{gray['share'] * 100:.1f}%",
        'b1_name': b1['name'], 'b1_amount': money(b1['amount']), 'b1_stations': b1['stations'],
        'b2_name': b2['name'], 'b2_amount': money(b2['amount']), 'n_stations': n_st,
        'outside_reach': (f'each buying between {reach[0]} and {reach[-1]} of the {n_st} stations'
                          if reach and reach[0] != reach[-1] else f'each buying {reach[0]} of the {n_st} stations'),
        'rows_m': f"{spend['rows_scanned'] / 1e6:.2f} million",
        'gap_year': gap,
        'gap_near': series(f'{money(per_year[y])} in {y}' for y in near) if near else 'little',
    }

# Map labels and city dots, by longitude/latitude; build_map.py's projection
# places them. Market labels sit inside each market's Louisiana side.
MAP_LABELS = {'NO': (-89.918, 30.216), 'BR': (-91.23, 30.569), 'SHV': (-93.565, 32.362),
              'LAF': (-92.086, 30.054), 'LKC': (-93.32, 30.407), 'MON': (-92.086, 32.295),
              'ALX': (-92.631, 31.456)}
MAP_CITIES = {'New Orleans': (-90.071, 29.951), 'Baton Rouge': (-91.14, 30.451),
              'Shreveport': (-93.75, 32.525), 'Lafayette': (-92.02, 30.224),
              'Lake Charles': (-93.218, 30.226), 'Monroe': (-92.119, 32.509),
              'Alexandria': (-92.445, 31.311)}
# Out-of-state cities in the markets, drawn smaller.
MAP_TOWNS = {'Texarkana': (-94.047, 33.425), 'El Dorado': (-92.666, 33.208),
             'Marshall': (-94.367, 32.545), 'Picayune': (-89.679, 30.526)}
# Mississippi's counties sit at both ends of the state line (Baton Rouge's
# Amite and Wilkinson, New Orleans's Pearl River and Hancock), so the middle
# of its outlines falls on Louisiana; its label goes between them, above it.
STATE_LABEL_AT = {'MS': (-90.2, 31.22)}
STATE_NAMES = {'TX': 'Texas', 'AR': 'Arkansas', 'MS': 'Mississippi', 'LA': 'Louisiana'}


def louisiana_households():
    """Per market: the Louisiana share of its Census households (ACS), and
    Nielsen's TV households scaled by that share. Nielsen publishes TV
    households for a market only as a whole; the Census counts say how much
    of that whole is in Louisiana."""
    hh = json.load(open(D('data', 'households.json'), encoding='utf-8'))
    cd = json.load(open(D('data', 'county_dma.json'), encoding='utf-8'))
    la, allc = defaultdict(int), defaultdict(int)
    for fips, c in cd.items():
        k = BY_TOPO[c['dma']]
        allc[k] += hh['counties'][fips]
        if c['st'] == 'LA':
            la[k] += hh['counties'][fips]
    return {k: {'share': la[k] / allc[k], 'censusLA': la[k], 'censusAll': allc[k]}
            for k in MARKETS}, hh['source']

def benchmarks(spend, la_hh):
    """TV dollars by market in each governor's-race year, nominal, with the
    CPI-U factor that restates each year in base-year dollars. The page
    derives share, real dollars and per-household figures from these;
    `hh` is each market's Louisiana TV households."""
    cpi = json.load(open(D('data', 'cpi.json'), encoding='utf-8'))
    base = cpi['annual'][str(cpi['base_year'])]
    # Only governor years already over and with a CPI figure: a race still
    # under way (2027) is the pace chart's job, not a benchmark's.
    this_year = int(spend['data_through'][:4])
    years = [y for y in sorted(GOV_YEARS) if y < this_year and str(y) in cpi['annual']]
    by = defaultdict(lambda: defaultdict(float))
    for s in spend['stations']:
        for y in years:
            by[BY_NAME[s['dma']]][y] += s['by_year'].get(str(y), 0)
    return {
        'years': years, 'base': cpi['base_year'], 'source': cpi['source'],
        'factor': [round(base / cpi['annual'][str(y)], 4) for y in years],
        'rows': [{'k': k, 'name': n, 'hh': la_hh[k], 'v': [round(by[k][y]) for y in years]}
                 for k, (n, _, hh) in MARKETS.items()],
    }


def project(geo, lon, lat):
    p = geo['proj']
    return [round((lon - p['lon0']) * p['kx'], 1), round((p['lat1'] - lat) * p['s'], 1)]


def state_labels(geo):
    """A name for each neighbouring state, at the middle of its counties' outlines."""
    pts = defaultdict(list)
    for c in geo['counties']:
        if c['st'] != 'LA':
            nums = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', c['d'])]
            pts[c['st']] += list(zip(nums[::2], nums[1::2]))
    out = []
    for st, ps in sorted(pts.items()):
        if st in STATE_LABEL_AT:
            out.append([STATE_NAMES[st], *project(geo, *STATE_LABEL_AT[st])])
            continue
        xs, ys = [p[0] for p in ps], [p[1] for p in ps]
        out.append([STATE_NAMES[st], round(sum(xs) / len(xs)), round(sum(ys) / len(ys))])
    return out


def build_data():
    spend = json.load(open(D('data', 'station_spend.json'), encoding='utf-8'))
    ref = {s['call']: s for s in json.load(open(D('data', 'stations.json'), encoding='utf-8'))}
    geo = json.load(open(D('data', 'map_paths.json'), encoding='utf-8'))

    total = spend['total_spend']
    tot_hh = sum(m[2] for m in MARKETS.values())
    mspend = {BY_NAME[m['name']]: m['spend'] for m in spend['markets']}

    lah, hh_source = louisiana_households()
    la_hh = {k: round(hh * lah[k]['share']) for k, (_, _, hh) in MARKETS.items()}
    tot_la = sum(la_hh.values())
    dmas = [{'k': k, 'name': n, 'rank': r, 'hh': hh,
             'spend': round(mspend[k]),
             'pph': round(mspend[k] / hh, 2),
             'index': round((mspend[k] / total) / (hh / tot_hh), 3),
             # The Louisiana side: Nielsen's count scaled by the Census share.
             'laHH': la_hh[k], 'laShare': round(lah[k]['share'], 4),
             'pphLA': round(mspend[k] / la_hh[k], 2),
             'indexLA': round((mspend[k] / total) / (la_hh[k] / tot_la), 3)}
            for k, (n, r, hh) in MARKETS.items()]
    dmas.sort(key=lambda d: -d['spend'])

    # Each station's political file at the FCC, for the map panel.
    try:
        pf = {st['call']: f"https://publicfiles.fcc.gov/tv-profile/{(st.get('fcc_call') or st['call']).lower()}/political-files"
              for st in json.load(open(D('data', 'fcc_political.json'), encoding='utf-8'))['stations']}
    except FileNotFoundError:
        pf = {}
    stations = []
    for s in spend['stations']:
        r = ref[s['call']]
        stations.append({
            'call': s['call'], 'k': BY_NAME[s['dma']], 'pf': pf.get(s['call']),
            'ch': r.get('virtual_channel') or '', 'net': s['network'],
            'owner': s['owner'], 'grp': s['owner_group'],
            'note': r.get('ownership_note'), 'spend': round(s['spend']),
            'cm': s['committees'],
            'top': [{'n': t['name'], 'a': round(t['amount'])} for t in s['top_committees'][:5]],
        })

    per_year = defaultdict(float)
    for s in spend['stations']:
        for y, v in s['by_year'].items():
            per_year[int(y)] += v

    return {
        'w': geo['w'], 'h': geo['h'],
        'counties': [{'n': c['n'], 'k': BY_TOPO[c['dma']], 'st': c['st'], 'd': c['d']}
                     for c in geo['counties']],
        'mapLabels': {k: project(geo, *ll) for k, ll in MAP_LABELS.items()},
        'cities': [[n, *project(geo, *ll)] for n, ll in MAP_CITIES.items()],
        'towns': [[n, *project(geo, *ll)] for n, ll in MAP_TOWNS.items()],
        'states': state_labels(geo),
        'hhSource': hh_source,
        'dmas': dmas,
        'stations': stations,
        'owners': [{'grp': o['group'], 'spend': round(o['spend']), 'n': o['stations'],
                    'share': round(o['share'] * 100, 1)} for o in spend['owners']],
        'years': [{'y': y, 'v': round(per_year[y]), 'gov': y in GOV_YEARS}
                  for y in sorted(per_year)],
        'buyers': [{'name': b['name'], 'party': b['party'], 'amt': round(b['amount']),
                    'st': b['stations'], 'f': b['filer']} for b in spend['top_buyers'][:12]],
        'total': round(total), 'totHH': tot_hh, 'avgPPH': round(total / tot_hh, 2),
        'totLA': tot_la, 'avgPPHLA': round(total / tot_la, 2),
        'yearsCovered': spend['years_covered'], 'yearsMissing': spend['years_missing'],
        'rowsScanned': spend['rows_scanned'],
        'bench': benchmarks(spend, la_hh),
        'fcc': fcc_summary({s['call']: BY_NAME[s['dma']] for s in spend['stations']}),
        'agencies': agencies(spend),
        'pace': {'from': spend['pace']['weeks'][0], 'to': spend['pace']['weeks'][1],
                 'cycles': [{'y': c['year'], 'primary': c['primary'], 'done': c['complete'],
                             'c': [round(v) for v in c['cumulative']]}
                            for c in spend['pace']['cycles']]},
        'recent': {'through': spend['recent_buyers']['through'],
                   'total': round(spend['recent_buyers']['total']),
                   'committees': spend['recent_buyers']['committees'],
                   'top': [{'name': b['name'], 'party': b['party'], 'amt': round(b['amount']),
                            'last': b['last_buy'], 'f': b['filer']} for b in spend['recent_buyers']['top'][:8]]},
        'radioExcl': round(sum(spend['caveats']['radio_excluded'].values())),
        'ambig': round(sum(spend['caveats']['ambiguous_bare_call'].values())),
        'combined': round(spend['caveats']['combined_buys']['amount']),
    }


AGENCY_ROWS = 25


def agencies(spend):
    """The media agencies (data/agencies.json, from build_agency_spend.py)
    beside what committees paid stations directly over the same years; None
    before that build has run."""
    try:
        ag = json.load(open(D('data', 'agencies.json'), encoding='utf-8'))
    except FileNotFoundError:
        return None
    since = ag['cycle_from']
    direct = sum(v for st in spend['stations'] for y, v in st['by_year'].items() if int(y) >= since)
    # The biggest by media dollars, plus every agency a political file names
    # (federal buyers have no state payments to rank them by).
    ranked = [r for r in ag['agencies'] if r.get('fcc') or r.get('paid', {}).get('media_cycle')]
    keep = {id(r) for r in ranked[:AGENCY_ROWS]} | {id(r) for r in ranked if r.get('fcc')}
    rows = [r for r in ranked if id(r) in keep][:AGENCY_ROWS * 2]
    return {
        'from': since, 'read': ag.get('documents_read', 0), 'stations': round(direct),
        'media': sum(r.get('paid', {}).get('media_cycle', 0) for r in ag['agencies']),
        'rows': [{'name': r['name'],
                  **({'fcc': {**{k: r['fcc'][k] for k in ('docs', 'usd', 'stations', 'clients')},
                              **({'away': r['fcc']['away']} if r['fcc'].get('away', {}).get('docs') else {})}}
                     if r.get('fcc') else {}),
                  **({'paid': {'mediaCycle': r['paid']['media_cycle'], 'cycle': r['paid']['cycle'],
                               'committees': r['paid']['committees'],
                               'top': [{'f': t['f'], 'n': t['n'], 'usd': t['usd'], 'cycle': t['cycle']}
                                       for t in r['paid']['top'][:4] if t['cycle'] > 0]}} if r.get('paid') else {})}
                 for r in rows],
    }


def main():
    blob = 'const DATA = ' + json.dumps(build_data(), separators=(',', ':'), ensure_ascii=False) + ';'
    spend = json.load(open(D('data', 'station_spend.json'), encoding='utf-8'))
    f = facts(spend)
    desc = (f"Louisiana political committees have paid the state’s TV stations {f['tv_total']} "
            f"since {f['tv_since']}. Where it went, by Nielsen market, station, owner and party.")
    for name in publish(D('page.template.html'), blob, spend, 'tv', D('index.html'), D('artifact.html'),
                        desc, SITE_URL, facts=f):
        print(f'  {os.path.basename(name)}  {os.path.getsize(name):,} bytes')
    print('Built from page.template.html + data/')


if __name__ == '__main__':
    main()
