#!/usr/bin/env python3
"""
build_committees_page.py — one profile per committee that bought TV or radio
================================================================================
Every committee in the filings that paid a television or radio station gets a
profile: what it spent on each medium, by year, by market and station, and
(radio) by format. The page is a searchable list; a profile opens at
committees.html#f=<filer number>, so a profile can be linked to directly.

    python3 build_committees_page.py

Reads data/committees_tv.json and data/committees_radio.json (written by the
two spend builders), data/stations.json (TV call sign -> market) and
data/station_spend.json (date stamps). Writes committees.html (standalone, for
GitHub Pages) and committees.artifact.html (body fragment), and
data/filer_media.json, the per-filer summary the campaign-finance dashboard
(finance.charliestephens.xyz) pulls nightly to show each campaign's airtime on
its own profile. Stdlib only.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)
sys.path.insert(0, HERE)
sys.path.insert(0, D('fcc'))
from markets import BY_NAME  # noqa: E402
from summary import fcc_summary  # noqa: E402
from page_shell import SITE, publish  # noqa: E402

URL = SITE + 'committees.html'
DESCRIPTION = ('Every Louisiana political committee that has bought television or radio '
               'time since 2000: what it spent, when, and on which stations.')


def booking(market):
    """filer -> what the FCC political files show it booking, for buyers
    the TV page matched to a state filer; and the file's date stamps."""
    F = fcc_summary(market, full=True)
    if not F:
        return {}, None
    by = {}
    for x in F['all']:
        g = by.setdefault(x['f'], {'n': x['name'], 'o': x['office'], 'docs': 0, 'recent': 0,
                                   'latest': '', 'st': {}, 'live': set()})
        g['docs'] += x['docs']
        g['recent'] += x['recent']
        g['latest'] = max(g['latest'], x['latest'])
        for st in x['st']:
            g['st'].setdefault(st['c'], st)
        g['live'] |= set(x['stRecent'])
    out = {f: {'n': g['n'], 'o': g['o'], 'docs': g['docs'], 'recent': g['recent'], 'latest': g['latest'],
               'st': [dict(v, r=c in g['live']) for c, v in sorted(g['st'].items())]}
           for f, g in by.items()}
    return out, {'scraped': F['scraped'], 'since': F['since'], 'days': F['days']}


def build_data():
    tv = json.load(open(D('data', 'committees_tv.json'), encoding='utf-8'))
    ra = json.load(open(D('data', 'committees_radio.json'), encoding='utf-8'))
    market = {s['call']: BY_NAME[s['dma']] for s in json.load(open(D('data', 'stations.json'), encoding='utf-8'))}
    pf, pf_meta = booking(market)
    filers = json.load(open(D('data', 'filers.json'), encoding='utf-8'))

    rows = []
    # A filer booking airtime it hasn't reported paying for yet gets a
    # profile too: the political file runs weeks ahead of the filings.
    for fn in sorted(set(tv) | set(ra) | set(pf)):
        t, r = tv.get(fn, {}), ra.get(fn, {})
        years = sorted(set(t.get('years', {})) | set(r.get('years', {})))
        # The committee files are written with sorted keys, so rank here.
        tst = sorted(t.get('stations', {}).items(), key=lambda x: -x[1])
        rst = sorted(r.get('stations', {}).items(), key=lambda x: -x[1])
        mk = {}
        for c, v in tst:
            if market.get(c):
                mk[market[c]] = mk.get(market[c], 0) + v
        rows.append({
            'f': fn,
            'n': t.get('name') or r.get('name') or filers.get(fn, {}).get('n') or pf[fn]['n'],
            'p': t.get('party') or r.get('party') or filers.get(fn, {}).get('p') or 'OTH',
            'tv': round(t.get('total', 0)), 'ra': round(r.get('total', 0)),
            # year -> [tv, radio]
            'y': {y: [round(t.get('years', {}).get(y, 0)), round(r.get('years', {}).get(y, 0))]
                  for y in years},
            'ts': [[c, round(v), market.get(c)] for c, v in tst[:12]],
            'nts': len(tst),
            'mk': [[k, round(v)] for k, v in sorted(mk.items(), key=lambda x: -x[1])],
            'rs': [[c, round(v)] for c, v in rst[:8]],
            'nrs': len(rst),
            'fm': [[k, round(v)] for k, v in sorted(r.get('formats', {}).items(), key=lambda x: -x[1])],
            **({'pf': pf[fn]} if fn in pf else {}),
        })
    rows.sort(key=lambda x: (-(x['tv'] + x['ra']), x['f']))   # filer number breaks ties stably
    return rows, pf_meta


def media_export(rows, pf_meta, spend):
    """filer -> its airtime in brief, for the campaign-finance dashboard.

    One line per filer, so a night whose only change is the `generated` stamp
    leaves a diff the nightly commit step ignores. `top` is the biggest TV
    stations, or radio when the committee bought no TV.
    """
    out = {}
    for c in rows:
        ys = sorted(c['y'])
        e = {'n': c['n'], 'tv': c['tv'], 'ra': c['ra'], 'nts': c['nts'], 'nrs': c['nrs']}
        if ys:
            e['y0'], e['y1'] = ys[0], ys[-1]
        top = [s for s, _, _ in c['ts'][:3]] or [s for s, _ in c['rs'][:3]]
        if top:
            e['top'] = top
        if 'pf' in c:
            p = c['pf']
            e['pf'] = {'docs': p['docs'], 'recent': p['recent'], 'latest': p['latest'],
                       'st': len(p['st']), 'live': sum(1 for s in p['st'] if s['r'])}
        out[c['f']] = e
    head = {'generated': spend['generated'], 'data_through': spend['data_through'],
            'site': URL, 'fcc': pf_meta}
    lines = [f'{json.dumps(k)}: {json.dumps(v, separators=(",", ":"), ensure_ascii=False)}'
             for k, v in sorted(out.items())]
    return ('{\n' + ''.join(f'{json.dumps(k)}: {json.dumps(v)},\n' for k, v in head.items())
            + '"filers": {\n' + ',\n'.join(lines) + '\n}}\n')


def main():
    spend = json.load(open(D('data', 'station_spend.json'), encoding='utf-8'))
    rows, pf_meta = build_data()
    blob = ('const DATA = ' + json.dumps(rows, separators=(',', ':'), ensure_ascii=False) + ';\n'
            'const PF = ' + json.dumps(pf_meta, separators=(',', ':')) + ';')
    for name in publish(D('committees.template.html'), blob, spend, 'committees', D('committees.html'),
                        D('committees.artifact.html'), DESCRIPTION, URL,
                        title='Louisiana Airwaves — Committees'):
        print(f'  {os.path.basename(name)}  {os.path.getsize(name):,} bytes')
    with open(D('data', 'filer_media.json'), 'w', encoding='utf-8') as f:
        f.write(media_export(rows, pf_meta, spend))
    print(f'  filer_media.json  {os.path.getsize(D("data", "filer_media.json")):,} bytes')


if __name__ == '__main__':
    main()
