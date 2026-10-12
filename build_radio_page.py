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
import re
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'fcc'))
from page_shell import RADIO_ICON, publish  # noqa: E402
from summary import fcc_summary  # noqa: E402
from prose import ahead_of, dollars, money, pct, series, share_words, words  # noqa: E402
D = lambda *p: os.path.join(HERE, *p)

SITE_TITLE = 'Louisiana Dial'
# How the copy names a format category: as the leader ("urban, gospel and
# Black talk formats take 29%"), in a headline ("…buys Black radio") and as
# the runner-up ("just ahead of news/talk").
CAT_LONG = {'Black-audience': 'urban, gospel and Black talk formats', 'News/Talk': 'news and talk formats'}
CAT_SHORT = {'Black-audience': 'Black radio', 'News/Talk': 'talk radio', 'Country': 'country radio'}
CAT_NEXT = {'Black-audience': 'Black-audience radio', 'News/Talk': 'news/talk'}
# The committees the copy reads a strategy from, by filer number.
EDWARDS, BLANCO, BOASSO, LANDRY, JINDAL, CFC_PAC = '1144', '31', '632', '1625', '631', '4632'
ORDINAL = {2: 'half', 3: 'a third', 4: 'a quarter', 5: 'a fifth', 6: 'a sixth', 7: 'a seventh',
           8: 'an eighth', 9: 'a ninth', 10: 'a tenth', 11: 'an eleventh', 12: 'a twelfth'}


def facts():
    """The figures the page's written copy quotes, from the data (see prose.py)."""
    d = json.load(open(D('data', 'radio_spend.json'), encoding='utf-8'))
    tv = json.load(open(D('data', 'station_spend.json'), encoding='utf-8'))
    cm = json.load(open(D('data', 'committees_radio.json'), encoding='utf-8'))
    total = d['total_spend']
    cats = [c for c in d['categories'] if not c['category'].startswith('Unclassified')]
    top, nxt = cats[0], cats[1]
    k = top['category']
    mix = lambda f, cat: cm[f]['formats'].get(cat, 0) / cm[f]['total'] if f in cm else 0
    jindal = sorted(cm[JINDAL]['formats'].items(), key=lambda x: -x[1])[:3]
    name = {'News/Talk': 'talk', 'Black-audience': 'Black-audience', 'Country': 'country'}
    tv_med = statistics.median(s['spend'] / s['rows'] for s in tv['stations'] if s['rows'] >= 5)
    kvpi = next(s for s in d['stations'] if s['call'] == 'KVPI')
    st = d['stations']
    lead, s2, s3 = st[0], st[1], st[2]
    fmt = re.sub(r'"([^"]+)"', '\u201c\\1\u201d', lead['format'])
    fmt = fmt[0].lower() + fmt[1:] if not fmt.split()[0].isupper() else fmt
    duo = sum(o['share'] for o in tv['owners'] if o['group'] in ('gray', 'nexstar'))
    corp = [o['owner'] for o in d['owners'] if o['owner'] not in ('Local', 'Unknown')][:4]
    local = next((o['share'] for o in d['owners'] if o['owner'] == 'Local'), 0)
    n = round(tv['total_spend'] / total)
    return {
        'tv_fraction': ORDINAL.get(n, f'1/{n}'),
        'top_share_words': share_words(top['share']).capitalize(),
        'top_short': CAT_SHORT.get(k, k.lower() + ' radio'),
        'top_verb': 'dominates' if top['share'] >= 1.25 * nxt['share'] else 'leads',
        'top_long': CAT_LONG.get(k, k.lower() + ' formats'),
        'top_share': pct(top['share']),
        'top_vs_next': f"{ahead_of(top['share'], nxt['share'])} {CAT_NEXT.get(nxt['category'], nxt['category'].lower())}"
                       f" ({pct(nxt['share'])})",
        'edwards_b': pct(mix(EDWARDS, 'Black-audience')), 'blanco_b': pct(mix(BLANCO, 'Black-audience')),
        'boasso_b': pct(mix(BOASSO, 'Black-audience')), 'landry_t': pct(mix(LANDRY, 'News/Talk')),
        'cfc_t': round(mix(CFC_PAC, 'News/Talk') * 100), 'cfc_c': round(mix(CFC_PAC, 'Country') * 100),
        'jindal_mix': series(f"{pct(v / cm[JINDAL]['total'])} {name.get(c, c.lower())}" for c, v in jindal),
        'tv_median_buy': dollars(tv_med),
        'kvpi_n': kvpi['committees'], 'kvpi_avg': dollars(kvpi['avg_buy']),
        'n_stations_words': words(len(st)).capitalize(), 'n_stations': len(st),
        'lead_call': lead['call'], 'lead_city': lead['city'], 'lead_desc': f"{lead['owner']}'s {fmt}",
        'lead_amount': money(lead['spend']),
        'lead_vs': (', more than the next two combined' if lead['spend'] > s2['spend'] + s3['spend']
                    else f", ahead of {s2['call']} ({money(s2['spend'])})"),
        'duopoly_share': pct(duo), 'radio_owners': series(f'<b>{o}</b>' for o in corp),
        'local_share': pct(local),
        'radio_total': money(total), 'radio_since': d['years_covered'][0],
    }
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
                    'stations': b['stations'], 'mix': b['mix'], 'f': b['filer']} for b in d['top_buyers']],
    }


def booking():
    """Who the radio stations' FCC political files show booking now: the
    buyers with documents in the last two weeks, busiest first. None until
    the radio scrape has run."""
    F = fcc_summary({}, full=True, media=('radio',))
    if not F:
        return None
    rows = [{'n': x['name'], 'b': x['b'], 'o': x['office'], 'recent': x['recent'], 'docs': x['docs'],
             'latest': x['latest'], 'f': x['f'], 'fresh': len(x['fresh']),
             'st': [[s['c'], s['u'], s['c'] in x['stRecent']] for s in x['st']],
             **({'onAir': x['onAir']} if 'onAir' in x else {})}
            for x in F['all'] if x['recent']]
    return {'scraped': F['scraped'], 'days': F['days'], 'stations': F['media'].get('radio', 0),
            'buyers': rows[:20], 'more': max(0, len(rows) - 20)}


def main():
    data = build_data()
    data['pf'] = booking()
    blob = 'const DATA = ' + json.dumps(data, separators=(',', ':'), ensure_ascii=False) + ';'
    spend = json.load(open(D('data', 'radio_spend.json'), encoding='utf-8'))
    f = facts()
    desc = (f"Louisiana campaigns have put {f['radio_total']} into radio since {spend['years_covered'][0]}, "
            f"and {f['top_share_words'].lower()} of it buys {f['top_short'].replace(' radio', '')}-audience "
            f"stations." if f['top_short'] == 'Black radio' else
            f"Louisiana campaigns have put {f['radio_total']} into radio since {spend['years_covered'][0]}.")
    desc += ' Political radio spending by format, station and buyer.'
    for name in publish(D('radio.template.html'), blob, spend, 'radio', D('radio.html'),
                        D('radio.artifact.html'), desc, CANONICAL,
                        title=SITE_TITLE, site_name=SITE_TITLE, icon=RADIO_ICON, facts=f):
        print(f'  {os.path.basename(name)}  {os.path.getsize(name):,} bytes')


if __name__ == '__main__':
    main()
