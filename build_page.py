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
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)
sys.path.insert(0, D('fcc'))
from normalize import (aliases, bucket, buyer_folder, buyer_from_filename, buyer_key,  # noqa: E402
                       classify, clean_name, fcc_url, filer_index, match_filer, out_of_state,
                       parse_path, tidy_caps)
from site_nav import NAV_CSS, nav  # noqa: E402

SITE_URL = 'https://airwaves.charliestephens.xyz/'
DESCRIPTION = ('Louisiana political committees have paid the state’s TV stations '
               '$121 million since 2000. Where it went, by Nielsen market, station, '
               'owner and party.')

# Market keys, ranks and 2024-25 Nielsen TV households.
MARKETS = {
    'NO':  ('New Orleans',       50, 672790),
    'SHV': ('Shreveport',        91, 375030),
    'BR':  ('Baton Rouge',       95, 355760),
    'LAF': ('Lafayette',        124, 245210),
    'MON': ('Monroe–El Dorado', 142, 171300),
    'LKC': ('Lake Charles',     177,  97170),
    'ALX': ('Alexandria',       183,  85710),
}
# station_spend.json spells markets out; map_paths.json carries Nielsen's own names.
BY_NAME = {v[0]: k for k, v in MARKETS.items()}
BY_TOPO = {'New Orleans, LA': 'NO', 'Baton Rouge, LA': 'BR', 'Shreveport, LA': 'SHV',
           'Lafayette, LA': 'LAF', 'Lake Charles, LA': 'LKC',
           'Monroe, LA-El Dorado, AR': 'MON', 'Alexandria, LA': 'ALX'}
GOV_YEARS = {2003, 2007, 2011, 2015, 2019, 2023, 2027}
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

FCC_RECENT_DAYS = 14   # "this fortnight" in the political-file section
FCC_ROWS = 40          # buyers shipped to the page


def fcc_summary(markets_by_call, full=False):
    """Roll the FCC political-file listing up to buyers across stations.
    Returns None when the scrape hasn't run, so the page builds without it.
    With `full`, the result also carries every buyer (`all`), not just the
    rows the TV page shows, for the committee profiles."""
    try:
        fcc = json.load(open(D('data', 'fcc_political.json'), encoding='utf-8'))
    except FileNotFoundError:
        return None
    scraped = fcc['scraped'][:10]
    since = (date.fromisoformat(scraped) - timedelta(days=FCC_RECENT_DAYS - 1)).isoformat()
    # Call signs to strip when a buyer is read from a file name; KVHP's
    # sister station MVHP appears in its file names too.
    calls = {s['call'].split('-')[0] for s in json.load(open(D('data', 'stations.json'), encoding='utf-8'))}
    calls |= {'MVHP'}
    rows = []
    for st in fcc['stations']:
        for f in st['files']:
            level, office, buyer = parse_path(f['path'])
            if not level:
                continue
            # No buyer folder (the Lake Charles stations file straight into
            # the office folder): read the buyer from the document's name.
            from_name = None if buyer else buyer_from_filename(f['name'] or '', calls)
            name = buyer or from_name or office or 'Filed without a buyer folder'
            # Another state's race carried on a Louisiana station (East Texas
            # on Shreveport's, network issue buys on sub-channels) is kept
            # apart, so it doesn't count as Louisiana spending.
            state = out_of_state(f['path']) or (from_name and out_of_state('x/x/x/' + from_name))
            b = 'Out of state' if state else bucket(level)
            year = f['path'].split('/')[1]
            # Link to the buyer's own folder at this station: its id comes from
            # the scraper's folder map, or from the file itself when it sits
            # directly in that folder. Older scrapes have neither for files
            # filed under Orders/Invoices; those fall back to the year folder.
            bpath = buyer_folder(f['path'])
            fid = (st.get('folders') or {}).get(bpath) or (f['folder_id'] if f['path'] == bpath else None)
            slug = (st.get('fcc_call') or st['call']).lower()
            yf = st.get('year_folders', {}).get(year)
            link = (fcc_url(slug, bpath, fid) if fid else
                    f"https://publicfiles.fcc.gov/tv-profile/{slug}/political-files/{year}/{yf}" if yf else None)
            rows.append({'link': link, 'deep': bool(fid), 'from_name': bool(from_name), 'b': b, 'level': level, 'key': buyer_key(name) or name.lower(), 'name': name, 'state': state,
                         'office': office, 'call': st['call'], 'up': (f['uploaded'] or '')[:10],
                         'kind': classify(f['name'] or '', f['path']), 'year': year,
                         'year_folder': st.get('year_folders', {}).get(year),
                         'slug': (st.get('fcc_call') or st['call']).lower()})
    # A race one station marks as another state's is that state's at every
    # station: KTBS files Texas's Senate race (Ken Paxton, James Talarico)
    # under plain "Federal/US Senate", KSLA under "US Senate/Texas". Matched on
    # full names only, never a bare surname.
    away_state = defaultdict(Counter)
    for r in rows:
        if r['b'] == 'Out of state':
            away_state[r['key']][r['state']] += 1
    for r in rows:
        if r['b'] != 'Out of state' and len(r['key'].split()) > 1 and r['key'] in away_state:
            r['b'], r['state'] = 'Out of state', away_state[r['key']].most_common(1)[0][0]
    # A candidate runs for one office: a full name some stations file under
    # Federal and others under State (KTVE and KARD put Julia Letlow's and
    # Misti Cordell's congressional races there) is one federal candidate.
    federal = {r['key'] for r in rows if r['b'] == 'Federal' and len(r['key'].split()) > 1}
    for r in rows:
        if r['b'] == 'State & local' and r['key'] in federal:
            r['b'] = 'Federal'
    keys = defaultdict(set)
    for r in rows:
        keys[r['b']].add(r['key'])
    alias = aliases(keys)
    groups = defaultdict(list)
    for r in rows:
        groups[(r['b'], alias[(r['b'], r['key'])])].append(r)

    # The state filer behind a buyer, so the page can link to its committee
    # profile. Federal candidates report to the FEC, not the state, and
    # other states' races aren't in the filings, so neither is matched.
    try:
        fidx = filer_index(json.load(open(D('data', 'filers.json'), encoding='utf-8')))
    except FileNotFoundError:
        fidx = {}

    buyers = []
    for (b, target), rs in groups.items():
        recent = [r for r in rs if r['up'] >= since]
        latest = max(rs, key=lambda r: r['up'])
        # Show the cleanest spelling: one whose cleaned form is the group's own
        # key (so "Bill Cassidy", not the surname-only "Cassidy-R for US
        # Senate"), with the least left over around it ("Hillar Moore", not
        # "Hillar Moore- District Attorney"); then the most common.
        # Candidates lose the office written onto their name ("Don Landry -
        # District Attorney"); issue groups keep theirs whole ("Citizens for
        # Louisiana" is a name, not a race).
        issue = all(r['level'] == 'Issue' for r in rs)
        names = Counter(tidy_caps(clean_name(r['name'], issue)) for r in rs)
        # The spelling the key comes from before ALIASES, so a station's
        # typo ("Mike Johson") never names the group.
        name = min(names, key=lambda n: (buyer_key(n, alias=False) != target, buyer_key(n) != target,
                                         len(n) - len(target), -names[n], n))
        offices = Counter(r['office'] for r in rs if r['office'])
        # One link per station: the buyer's folder there, from that station's
        # most recent document for the buyer.
        links = {}
        for r in sorted(rs, key=lambda r: r['up']):
            if r['link'] and (r['deep'] or not links.get(r['call'], (None, False))[1]):
                links[r['call']] = (r['link'], r['deep'])
        buyers.append({
            'name': re.sub(r'\s+campaign$', '', name, flags=re.I), 'b': b, 'office': tidy_caps(offices.most_common(1)[0][0]) if offices else None,
            'state': Counter(r['state'] for r in rs if r['state']).most_common(1)[0][0]
                     if b == 'Out of state' else None,
            'docs': len(rs), 'recent': len(recent), 'latest': latest['up'],
            'st': [{'c': c, 'k': markets_by_call.get(c), 'u': links.get(c, (None,))[0],
                    'd': links.get(c, (None, False))[1]} for c in sorted({r['call'] for r in rs})],
            'stRecent': sorted({r['call'] for r in recent}),
            'f': match_filer(sorted({clean_name(r['name']) for r in rs}), fidx, person=b != 'Issue')
                 if b in ('State & local', 'Issue') else None,
        })
    # Busiest this fortnight first, then the most recently active.
    buyers.sort(key=lambda x: (x['recent'], x['latest']), reverse=True)
    home = [x for x in buyers if x['b'] != 'Out of state']
    away = [x for x in buyers if x['b'] == 'Out of state']
    return {
        'scraped': scraped, 'since': since, 'days': FCC_RECENT_DAYS,
        'stations': sum(1 for s in fcc['stations'] if not s.get('stale')),
        'markets': sorted({MARKETS[markets_by_call[s['call']]][0] for s in fcc['stations']
                           if markets_by_call.get(s['call'])},
                          key=lambda n: [m[0] for m in MARKETS.values()].index(n)),
        'stale': [s['call'] for s in fcc['stations'] if s.get('stale')],
        'oldest': min((s.get('scraped_at') or scraped)[:10] for s in fcc['stations']) if fcc['stations'] else scraped,
        'noFile': fcc.get('no_online_file', []),
        # Stations where most buyers were read from document names.
        'byName': sorted({r['call'] for r in rows if r['from_name']}
                         - {c for c in {r['call'] for r in rows}
                            if sum(r['from_name'] for r in rows if r['call'] == c) * 2
                            < sum(1 for r in rows if r['call'] == c)}),
        # Headline counts are Louisiana's own races; out-of-state ones are
        # counted separately and listed under their own filter.
        'docs': sum(x['docs'] for x in home),
        'recentDocs': sum(x['recent'] for x in home),
        'recentBuyers': sum(1 for x in home if x['recent']),
        'byBucket': {k: sum(x['recent'] for x in home if x['b'] == k)
                     for k in ('Federal', 'State & local', 'Issue')},
        'away': {'docs': sum(x['docs'] for x in away), 'recent': sum(x['recent'] for x in away),
                 'buyers': len(away),
                 'states': [[s, n] for s, n in Counter(
                     {x['state']: 0 for x in away} | Counter(
                         s for x in away for s in [x['state']] * x['docs'])).most_common()]},
        'buyers': home[:FCC_ROWS] + away[:FCC_ROWS // 2],
        **({'all': [x for x in home if x['f']]} if full else {}),
    }



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


HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{desc}">
<meta name="color-scheme" content="light dark">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Louisiana Airwaves">
<meta property="og:title" content="Louisiana Airwaves">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Louisiana Airwaves">
<meta name="twitter:description" content="{desc}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22><text y=%2214%22 font-size=%2214%22>&#128250;</text></svg>">
<style>
  html,body{{margin:0}}
  img{{max-width:100%}}
  [hidden]{{display:none!important}}
</style>
'''
FOOT = '\n</body>\n</html>\n'


def fill_tokens(tpl, spend):
    """Fill the template's date tokens from the spend file, so the year span and
    "filings through" stamp move with the data instead of being hand-edited."""
    lo, hi = spend['years_covered']
    through = time.strftime('%B %-d, %Y', time.strptime(spend['data_through'], '%Y-%m-%d'))
    for tok, val in (('__SPAN__', f'{lo}–{hi}'), ('__SPAN_WORDS__', f'{lo} to {hi}'),
                     ('__THROUGH__', through), ('__NAV__', nav('tv')), ('__NAV_CSS__', NAV_CSS)):
        tpl = tpl.replace(tok, val)
    left = sorted(set(re.findall(r'__[A-Z_]+__', tpl)))
    if left:
        raise SystemExit(f'unfilled template tokens: {left}')
    return tpl


def main():
    tpl = open(D('page.template.html'), encoding='utf-8').read()
    if '/*__DATA__*/' not in tpl:
        raise SystemExit('page.template.html is missing the /*__DATA__*/ placeholder')
    blob = 'const DATA = ' + json.dumps(build_data(), separators=(',', ':'),
                                        ensure_ascii=False) + ';'
    fragment = tpl.replace('/*__DATA__*/', blob)
    fragment = fill_tokens(fragment, json.load(open(D('data', 'station_spend.json'), encoding='utf-8')))

    # The artifact publisher supplies its own <head>; ship the fragment as-is.
    with open(D('artifact.html'), 'w', encoding='utf-8') as f:
        f.write(fragment)

    # GitHub Pages serves a raw file, so it needs the full document. The
    # template opens with <title>/<link>/<style>, which belong in <head>; the
    # markup after them is body content.
    split = fragment.index('<div class="wrap">')
    head_part, body_part = fragment[:split], fragment[split:]
    standalone = (HEAD.format(desc=DESCRIPTION, url=SITE_URL)
                  + head_part + '</head>\n<body>\n' + body_part + FOOT)
    with open(D('index.html'), 'w', encoding='utf-8') as f:
        f.write(standalone)

    for name in ('index.html', 'artifact.html'):
        print(f'  {name}  {os.path.getsize(D(name)):,} bytes')
    print('Built from page.template.html + data/')


if __name__ == '__main__':
    main()
