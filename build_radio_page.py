#!/usr/bin/env python3
"""
build_radio_page.py — assemble the Louisiana Dial page from data/radio_spend.json
================================================================================
Same two-output pattern as build_page.py, for the same reason: GitHub Pages
serves a raw file and needs a complete document (doctype, charset, viewport),
while the Claude Artifact publisher supplies its own <head> and needs a body
fragment.

    python3 build_radio_page.py

Writes radio.html (standalone) and radio.artifact.html (fragment).
Edit radio.template.html, never the generated files. Stdlib only.
"""
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)

SITE_TITLE = 'Louisiana Dial'
DESCRIPTION = ('Louisiana campaigns have put $11.7M into radio since 2000, and a third of it '
               'buys Black-audience stations. Political radio spending by format, station and buyer.')
CANONICAL = 'https://airwaves.charliestephens.xyz/radio.html'


def build_data():
    d = json.load(open(D('data', 'radio_spend.json'), encoding='utf-8'))
    per_buy = [s['avg_buy'] for s in d['stations'] if s['rows'] >= 5]
    return {
        'total': d['total_spend'],
        'classifiedShare': d['caveats']['classified_share'],
        'rowsScanned': d['rows_scanned'],
        'collisions': d['caveats']['name_collisions_rejected']['amount'],
        'sisters': round(sum(d['caveats']['tv_sister_radio_rows'].values()), 2),
        'medianBuy': round(statistics.median(per_buy), 2) if per_buy else 0,
        'govShare': d['gov_year_share'],
        'yearsMissing': d['years_missing'],
        'categories': d['categories'],
        'owners': d['owners'],
        'stations': [{k: s[k] for k in ('call', 'city', 'market', 'format', 'category',
                                        'owner', 'bands', 'spend', 'rows', 'committees', 'avg_buy')}
                     for s in d['stations']],
        'buyers': [{'name': b['name'], 'party': b['party'], 'amount': b['amount'],
                    'stations': b['stations'], 'mix': b['mix']} for b in d['top_buyers']],
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
<meta property="og:site_name" content="{title}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22><text y=%2214%22 font-size=%2214%22>&#128251;</text></svg>">
<style>
  html,body{{margin:0}}
  img{{max-width:100%}}
  [hidden]{{display:none!important}}
</style>
'''


def main():
    tpl = open(D('radio.template.html'), encoding='utf-8').read()
    if '/*__DATA__*/' not in tpl:
        raise SystemExit('radio.template.html is missing the /*__DATA__*/ placeholder')
    blob = 'const DATA = ' + json.dumps(build_data(), separators=(',', ':'),
                                        ensure_ascii=False) + ';'
    frag = tpl.replace('/*__DATA__*/', blob)

    with open(D('radio.artifact.html'), 'w', encoding='utf-8') as f:
        f.write(frag)

    split = frag.index('<div class="wrap">')
    standalone = (HEAD.format(desc=DESCRIPTION, url=CANONICAL, title=SITE_TITLE)
                  + frag[:split] + '</head>\n<body>\n' + frag[split:] + '\n</body>\n</html>\n')
    with open(D('radio.html'), 'w', encoding='utf-8') as f:
        f.write(standalone)

    for n in ('radio.html', 'radio.artifact.html'):
        print(f'  {n}  {os.path.getsize(D(n)):,} bytes')


if __name__ == '__main__':
    main()
