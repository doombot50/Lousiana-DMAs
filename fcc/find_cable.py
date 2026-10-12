#!/usr/bin/env python3
"""
find_cable.py — the cable systems serving Louisiana, for their political files
================================================================================
Cable operators post political files to publicfiles.fcc.gov like broadcast
stations, but per cable system (a PSID), each serving a list of community
units in named parishes. The FCC's facility search finds systems by name;
this searches the operators and place names that turn up Louisiana systems
and keeps every system with a Louisiana community unit:

    data/cable_systems.json
    {"002460": {"name": "Cox Baton Rouge", "operator": "Cox", "legal": "COX COMMUNICATIONS LOUISIANA LLC",
                "parishes": {"East Baton Rouge": 7, ...}, "market": "BR"}, ...}

`parishes` counts the system's community units in each parish; `market` is
the TV market most of them are in. The nightly scraper
(scrape_political_files.py --media cable) reads this list. Run it when the
systems change (an operator sells, a system merges); the "FCC cable
systems" workflow runs it on GitHub's runners, where publicfiles.fcc.gov is
reachable, and commits the result. About fifteen requests. Stdlib only.
"""
import json
import os
import re
import sys
import urllib.parse
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from markets import BY_TOPO, MARKETS  # noqa: E402
from scrape_political_files import B, D, get  # noqa: E402

# Operators and places that turn up Louisiana systems in the facility search
# (it matches names, not service areas, and returns at most a few hundred).
TERMS = ['Louisiana', 'Cox Communications Louisiana', 'Comcast of Louisiana', 'Spectrum Gulf Coast',
         'Cequel', 'Vyve', 'EATEL', 'Classic Cable', 'Cable One', 'Reserve Telephone', 'Allen',
         'Shreveport', 'Monroe', 'Lake Charles', 'Alexandria']
OPERATORS = [(r'\bCOX\b', 'Cox'), (r'COMCAST', 'Comcast'), (r'SPECTRUM|CHARTER', 'Spectrum'),
             (r'CEQUEL|CEBRIDGE|SUDDENLINK|ALTICE|OPTIMUM', 'Optimum'), (r'ALLENS? TV', "Allen's TV Cable"),
             (r'CABLESOUTH', 'CableSouth'), (r'CAMERON COMM', 'Cameron Communications'), (r'VYVE', 'Vyve'), (r'EATEL|REV\b', 'EATEL'),
             (r'CLASSIC CABLE', 'Classic Cable'), (r'CABLE ONE|SPARKLIGHT', 'Sparklight')]
CITY = {'NO': 'New Orleans', 'BR': 'Baton Rouge', 'SHV': 'Shreveport', 'LAF': 'Lafayette',
        'MON': 'Monroe', 'LKC': 'Lake Charles', 'ALX': 'Alexandria'}


def operator(legal):
    return next((short for pat, short in OPERATORS if re.search(pat, legal, re.I)),
                legal.title().split(',')[0])


def name_systems(out):
    """Name each system "Cox Baton Rouge": the operator and its market's
    city for the operator's biggest system there, its biggest parish for any
    other ("Cox St. Mary"), and the PSID if that still collides."""
    groups = {}
    for psid, s in out.items():
        groups.setdefault((s['operator'], s['market']), []).append(psid)
    for (op, market), psids in groups.items():
        psids.sort(key=lambda p: (-out[p]['units'], p))
        for i, p in enumerate(psids):
            place = CITY.get(market, 'Louisiana') if i == 0 else next(iter(out[p]['parishes']), p)
            out[p]['name'] = f'{op} {place}'
    seen = Counter(s['name'] for s in out.values())
    for p, s in out.items():
        if seen[s['name']] > 1:
            s['name'] += f' ({p})'


def main():
    parish_dma = json.load(open(D('parish_dma.json'), encoding='utf-8'))
    canon = {p.lower(): p for p in parish_dma}
    systems = {}
    for term in TERMS:
        res = get(f'{B}/api/service/facility/search/{urllib.parse.quote(term)}')
        g = ((res or {}).get('results') or {}).get('globalSearchResults') or {}
        for it in g.get('cableSystemsList') or []:
            units = [c for c in it.get('cableCommunities') or []
                     if (c.get('communityUnitId') or '').startswith('LA')]
            # Searches return a system's communities that match the term, so
            # the same system can come back with a partial list: keep the
            # longest.
            if units and len(units) > len(systems.get(it['psid'], (None, []))[1]):
                systems[it['psid']] = (it, units)
        print(f'  {term}: {len(g.get("cableSystemsList") or [])} systems; {len(systems)} Louisiana so far')

    out = {}
    for psid, (it, units) in sorted(systems.items()):
        parishes = Counter(canon.get((c.get('countyName') or '').lower().replace('saint ', 'st. '),
                                     (c.get('countyName') or '').title()) for c in units)
        mk = Counter(BY_TOPO[parish_dma[p]] for p in parishes.elements() if p in parish_dma)
        market = mk.most_common(1)[0][0] if mk else None
        op = operator(it.get('legalName') or '')
        out[psid] = {'operator': op, 'legal': it.get('legalName'), 'market': market,
                     'units': len(units), 'parishes': dict(parishes.most_common())}
    name_systems(out)
    with open(D('cable_systems.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(out.items())), f, indent=1, ensure_ascii=False)
    for psid, s in out.items():
        print(f"  {psid} {s['name']:<32} {MARKETS[s['market']][0] if s['market'] else '—':<18} "
              f"{', '.join(s['parishes'])}")
    print(f'Wrote data/cable_systems.json ({len(out)} systems)')

    # DirecTV and Dish file political ads too, nationally; a look at how
    # their files are laid out, for a later scraper. Prints only.
    for slug in ('directv', 'dish'):
        page = get(f'{B}/dbs-profile/{slug}/political-files', want_json=False) or ''
        m = re.search(r'/political-files/([0-9a-f-]{36})"', page)
        print(f'\n{slug}: political-files root {m and m.group(1)}')
        if m:
            root = get(f'{B}/api/manager/folder/id/{m.group(1)}.json?entityId={slug.upper()}') or {}
            subs = (root.get('folder') or {}).get('subfolders') or []
            print('  ' + ', '.join(f"{s['folder_name']} ({s.get('file_count')})" for s in subs[:20]))
            year = next((s for s in subs if s['folder_name'] == '2026'), None)
            if year:
                y = get(f"{B}/api/manager/folder/id/{year['entity_folder_id']}.json?entityId={slug.upper()}") or {}
                ys = (y.get('folder') or {}).get('subfolders') or []
                print('  2026: ' + ', '.join(f"{s['folder_name']} ({s.get('file_count')})" for s in ys[:40]))


if __name__ == '__main__':
    main()
