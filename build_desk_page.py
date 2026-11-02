#!/usr/bin/env python3
"""
build_desk_page.py — the results desk: shareable result cards for each race
================================================================================
desk.html is a working page for election night, not part of the site's tab
bar. Pick a race, mark who won (or who made the runoff) and, if you like,
each candidate's share of the vote, and it draws a 1200x675 card (the size
X and most social sites show whole) with what the site knows about the race:
each candidate's money raised and spent this cycle, their airtime, and
whether the spending leader won, against how often a leader with that edge
has won since 2000. The image downloads or goes straight to the phone's
share sheet, with a caption to paste. The results themselves come from
whoever is calling the race; the page holds none.

The data is the races page's (build_races_page.build()), cut down to what a
card shows, so build_races_page.py writes this page in the same run:

    python3 build_races_page.py      # races.html and desk.html
    python3 build_desk_page.py       # desk.html alone

Writes desk.html (standalone) and desk.artifact.html (body fragment).
Stdlib only.
"""
import json
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)
sys.path.insert(0, HERE)
from page_shell import SITE, publish  # noqa: E402

URL = SITE + 'desk.html'
DESCRIPTION = ('Result cards for Louisiana races: who won, beside what each candidate raised, '
               'spent and put on the air.')
# Elections this long past still get a desk, for the night after and the runoff.
KEEP_AFTER = timedelta(days=45)


def airtime(c):
    """[dollars, kind, ad orders]: the candidate's airtime as a card shows it.
    The stations' political files are the fuller record this close to an
    election (they run weeks ahead of the finance reports, and are the only
    record of federal buys), but their dollars are read from the documents
    that state one; when fewer than half do, the count of orders is the
    honest figure and the dollars are left out."""
    pf = c.get('pf') or {}
    paid = (c.get('tv') or 0) + (c.get('ra') or 0)
    booked = pf.get('usd') or 0
    docs = pf.get('docs') or 0
    if booked and pf.get('priced', 0) * 2 >= docs and booked >= paid:
        return [booked, 'booked', docs]
    if paid:
        return [paid, 'paid', docs]
    return [0, '', docs]


def slim(c):
    a = airtime(c)
    row = {'n': c['n'], 'p': c.get('p') or 'OTH'}
    for k in ('r', 's'):
        if c.get(k):
            row[k] = c[k]
    if a[0]:
        row['a'], row['ak'] = a[0], a[1]
    if a[2]:
        row['ad'] = a[2]
    if c.get('v'):
        row['v'] = c['v']
    if c.get('w'):
        row['w'] = c['w']
    return row


def weight(r):
    """What a race's candidates spent and put on the air, for the order the
    desk lists races in: the races people will be watching first."""
    return sum((c.get('s') or 0) + (c.get('a') or 0) + 2000 * (c.get('ad') or 0) for c in r['c'])


def desk_data(data):
    today = date.fromisoformat(data['today'])
    elections = []
    for e in data['elections']:
        if not e.get('posted') or date.fromisoformat(e['d']) < today - KEEP_AFTER:
            continue
        races = []
        for r in e['races']:
            rr = {'id': r['id'], 'o': r['o'], 'pa': r.get('pa'), 't': r['t'], 'k': r.get('k', []),
                  'el': r.get('el', 1), 'c': [slim(c) for c in r['c']]}
            if r.get('adv'):
                rr['adv'] = r['adv']
            if r.get('out'):
                rr['og'] = len(r['out'])
            rr['wt'] = weight(rr)
            races.append(rr)
        races.sort(key=lambda r: (-r['wt'], r['o']))
        elections.append({'d': e['d'], 'races': races})
    return {'elections': elections, 'wins': data.get('wins'), 'today': data['today'],
            'fecFetched': data.get('fecFetched'),
            'fccScraped': (data.get('fcc') or {}).get('scraped')}


def write(data, spend, cycle):
    d = desk_data(data)
    blob = 'const DESK = ' + json.dumps(d, separators=(',', ':'), ensure_ascii=False).replace('</', '<\\/') + ';'
    return publish(D('desk.template.html'), blob, spend, 'desk', D('desk.html'), D('desk.artifact.html'),
                   DESCRIPTION, URL, title='Louisiana Airwaves — Results desk', icon='&#128240;',
                   facts={'cycle': cycle.replace('-', '–')})


def main():
    from build_races_page import CYCLE, build
    data, spend = build()
    for name in write(data, spend, CYCLE):
        print(f'  {os.path.basename(name)}  {os.path.getsize(name):,} bytes')


if __name__ == '__main__':
    main()
