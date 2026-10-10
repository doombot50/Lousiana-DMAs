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
from normalize import aliases, bucket, buyer_key, classify, parse_path  # noqa: E402

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

FCC_RECENT_DAYS = 14   # "this fortnight" in the political-file section
FCC_ROWS = 40          # buyers shipped to the page


def fcc_summary(markets_by_call):
    """Roll the FCC political-file listing up to buyers across stations.
    Returns None when the scrape hasn't run, so the page builds without it."""
    try:
        fcc = json.load(open(D('data', 'fcc_political.json'), encoding='utf-8'))
    except FileNotFoundError:
        return None
    scraped = fcc['scraped'][:10]
    since = (date.fromisoformat(scraped) - timedelta(days=FCC_RECENT_DAYS - 1)).isoformat()
    rows = []
    for st in fcc['stations']:
        for f in st['files']:
            level, office, buyer = parse_path(f['path'])
            if not level:
                continue
            name = buyer or office or 'Filed without a buyer folder'
            b = bucket(level)
            year = f['path'].split('/')[1]
            rows.append({'b': b, 'key': buyer_key(name) or name.lower(), 'name': name,
                         'office': office, 'call': st['call'], 'up': (f['uploaded'] or '')[:10],
                         'kind': classify(f['name'] or '', f['path']), 'year': year,
                         'year_folder': st.get('year_folders', {}).get(year)})
    keys = defaultdict(set)
    for r in rows:
        keys[r['b']].add(r['key'])
    alias = aliases(keys)
    groups = defaultdict(list)
    for r in rows:
        groups[(r['b'], alias[(r['b'], r['key'])])].append(r)

    buyers = []
    for (b, _), rs in groups.items():
        recent = [r for r in rs if r['up'] >= since]
        latest = max(rs, key=lambda r: r['up'])
        # For a candidate the fullest spelling reads best ("Bill Cassidy" over
        # "Cassidy-R for US Senate"); for an issue group the shortest does
        # ("Accountability Project", not "… Inc Del Cielo Media", its buyer).
        names = Counter(r['name'] for r in rs)
        words = lambda n: len(buyer_key(n).split())
        name = (min(names, key=lambda n: (words(n), -names[n], len(n))) if b == 'Issue' else
                max(names, key=lambda n: (words(n), names[n], -len(n))))
        offices = Counter(r['office'] for r in rs if r['office'])
        buyers.append({
            'name': name, 'b': b, 'office': offices.most_common(1)[0][0] if offices else None,
            'docs': len(rs), 'recent': len(recent), 'latest': latest['up'],
            'st': [{'c': c, 'k': markets_by_call.get(c)} for c in sorted({r['call'] for r in rs})],
            'stRecent': sorted({r['call'] for r in recent}),
            # The station's political-file folder for that year: the FCC site
            # has no stable deep link to a buyer's subfolder.
            'link': (f"https://publicfiles.fcc.gov/tv-profile/{latest['call'].lower()}/"
                     f"political-files/{latest['year']}/{latest['year_folder']}"
                     if latest['year_folder'] else None),
            'linkCall': latest['call'],
        })
    # Busiest this fortnight first, then the most recently active.
    buyers.sort(key=lambda x: (x['recent'], x['latest']), reverse=True)
    return {
        'scraped': scraped, 'since': since, 'days': FCC_RECENT_DAYS,
        'stations': sum(1 for s in fcc['stations'] if not s.get('stale')),
        'stale': [s['call'] for s in fcc['stations'] if s.get('stale')],
        'noFile': fcc.get('no_online_file', []),
        'docs': sum(x['docs'] for x in buyers),
        'recentDocs': sum(x['recent'] for x in buyers),
        'recentBuyers': sum(1 for x in buyers if x['recent']),
        'byBucket': {k: sum(x['recent'] for x in buyers if x['b'] == k)
                     for k in ('Federal', 'State & local', 'Issue')},
        'buyers': buyers[:FCC_ROWS],
    }


def build_data():
    spend = json.load(open(D('data', 'station_spend.json'), encoding='utf-8'))
    ref = {s['call']: s for s in json.load(open(D('data', 'stations.json'), encoding='utf-8'))}
    geo = json.load(open(D('data', 'map_paths.json'), encoding='utf-8'))

    total = spend['total_spend']
    tot_hh = sum(m[2] for m in MARKETS.values())
    mspend = {BY_NAME[m['name']]: m['spend'] for m in spend['markets']}

    dmas = [{'k': k, 'name': n, 'rank': r, 'hh': hh,
             'spend': round(mspend[k]),
             'pph': round(mspend[k] / hh, 2),
             'index': round((mspend[k] / total) / (hh / tot_hh), 3)}
            for k, (n, r, hh) in MARKETS.items()]
    dmas.sort(key=lambda d: -d['spend'])

    stations = []
    for s in spend['stations']:
        r = ref[s['call']]
        stations.append({
            'call': s['call'], 'k': BY_NAME[s['dma']],
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
        'parishes': [{'n': p['n'], 'k': BY_TOPO[p['dma']], 'd': p['d']} for p in geo['parishes']],
        'dmas': dmas,
        'stations': stations,
        'owners': [{'grp': o['group'], 'spend': round(o['spend']), 'n': o['stations'],
                    'share': round(o['share'] * 100, 1)} for o in spend['owners']],
        'years': [{'y': y, 'v': round(per_year[y]), 'gov': y in GOV_YEARS}
                  for y in sorted(per_year)],
        'buyers': [{'name': b['name'], 'party': b['party'], 'amt': round(b['amount']),
                    'st': b['stations']} for b in spend['top_buyers'][:12]],
        'total': round(total), 'totHH': tot_hh, 'avgPPH': round(total / tot_hh, 2),
        'yearsCovered': spend['years_covered'], 'yearsMissing': spend['years_missing'],
        'rowsScanned': spend['rows_scanned'],
        'fcc': fcc_summary({s['call']: BY_NAME[s['dma']] for s in spend['stations']}),
        'pace': {'from': spend['pace']['weeks'][0], 'to': spend['pace']['weeks'][1],
                 'cycles': [{'y': c['year'], 'primary': c['primary'], 'done': c['complete'],
                             'c': [round(v) for v in c['cumulative']]}
                            for c in spend['pace']['cycles']]},
        'recent': {'through': spend['recent_buyers']['through'],
                   'total': round(spend['recent_buyers']['total']),
                   'committees': spend['recent_buyers']['committees'],
                   'top': [{'name': b['name'], 'party': b['party'], 'amt': round(b['amount']),
                            'last': b['last_buy']} for b in spend['recent_buyers']['top'][:8]]},
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
                     ('__THROUGH__', through)):
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
