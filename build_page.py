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
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)

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
GOV_YEARS = {2003, 2007, 2011, 2015, 2019, 2023}


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


def main():
    tpl = open(D('page.template.html'), encoding='utf-8').read()
    if '/*__DATA__*/' not in tpl:
        raise SystemExit('page.template.html is missing the /*__DATA__*/ placeholder')
    blob = 'const DATA = ' + json.dumps(build_data(), separators=(',', ':'),
                                        ensure_ascii=False) + ';'
    fragment = tpl.replace('/*__DATA__*/', blob)

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
