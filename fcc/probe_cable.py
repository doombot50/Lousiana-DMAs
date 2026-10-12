#!/usr/bin/env python3
"""
probe_cable.py — what do Louisiana cable systems' FCC political files look like?
================================================================================
A one-off look before building anything: cable operators (and DirecTV and
Dish) post political files to publicfiles.fcc.gov like TV stations do, but
filed per cable system. This searches for the operators serving Louisiana,
prints what the search returns for cable, opens a few systems' profile
pages, and lists their political-file folders, so the real scraper can be
written against what's actually there. It stays small: about 30 requests,
two seconds apart, through scrape_political_files.get (same user agent,
same 403 handling). Prints only; writes nothing.

    python3 fcc/probe_cable.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape_political_files import B, Blocked, get  # noqa: E402

TERMS = ['Cox', 'Charter', 'Spectrum', 'Suddenlink', 'Comcast', 'EATEL', 'DIRECTV', 'DISH']
MAX_SYSTEMS = 4


def short(x, n=600):
    s = json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + '…'


def main():
    found = {}
    for term in TERMS:
        res = get(f'{B}/api/service/facility/search/{term}')
        g = ((res or {}).get('results') or {}).get('globalSearchResults') or {}
        print(f'\n== search {term}: lists {sorted(g)}')
        for key, items in g.items():
            if not isinstance(items, list) or key == 'tvFacilityList' or not items:
                continue
            print(f'  {key}: {len(items)} results; first: {short(items[0])}')
            for it in items:
                blob = json.dumps(it).upper()
                if '"LA"' in blob or 'LOUISIANA' in blob:
                    found.setdefault(key, {})[json.dumps(it, sort_keys=True)] = it
    print('\n== Louisiana entries by list')
    for key, items in found.items():
        print(f'  {key}: {len(items)}')
        for it in list(items.values())[:40]:
            print('    ' + short(it, 300))

    # A few systems' profile pages: what links do they carry, and where is
    # the political file?
    tried = 0
    for key, items in found.items():
        for it in items.values():
            if tried >= MAX_SYSTEMS:
                break
            ids = {k: v for k, v in it.items() if re.search(r'id|psid|cuid|unit|slug|code', k, re.I)}
            print(f'\n== {key} entry ids: {ids}')
            for pat in ('cable-profile', 'dbs-profile'):
                for v in list(ids.values())[:3]:
                    url = f'{B}/{pat}/{v}/political-files'
                    page = get(url, want_json=False)
                    tried += 1
                    if not page:
                        print(f'  {url}: nothing')
                        continue
                    links = sorted(set(re.findall(r'href="(/[^"]*political[^"]*)"', page)))[:15]
                    print(f'  {url}: {len(page)} bytes; political links {links}')
                    m = re.search(r'/political-files/([0-9a-f-]{36})', page)
                    ent = re.search(r'entityId["\':= ]+["\']?([0-9a-zA-Z-]+)', page)
                    print(f'  folder id {m and m.group(1)}; entityId hint {ent and ent.group(1)}')
                    if m:
                        for e in filter(None, [ent and ent.group(1), v]):
                            j = get(f'{B}/api/manager/folder/id/{m.group(1)}.json?entityId={e}')
                            tried += 1
                            print(f'  folder listing (entityId={e}): {short(j, 1500)}')
                            if j:
                                break
                    break
                if tried >= MAX_SYSTEMS * 3:
                    break


if __name__ == '__main__':
    try:
        main()
    except Blocked as e:
        print(f'Blocked by the CDN at {e}; stopping.')
