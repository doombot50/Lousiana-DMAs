#!/usr/bin/env python3
"""
probe_cable.py — what do Louisiana cable systems' FCC political files look like?
================================================================================
A one-off look before building anything: cable operators (and DirecTV and
Dish) post political files to publicfiles.fcc.gov like TV stations do, but
filed per cable system (PSID), each serving a list of community units in
named parishes. This finds the Louisiana systems through the facility
search, then opens two systems' profile pages, printing redirects and the
political-file links they carry, so the scraper can be written against
what's there. About 30 requests, two seconds apart, with the TV scraper's
user agent and 403 handling. Prints only; writes nothing.

    python3 fcc/probe_cable.py
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape_political_files import B, PAUSE, UA, Blocked, get  # noqa: E402

TERMS = ['Cox Communications Louisiana', 'Spectrum Gulf Coast', 'Spectrum Mid-America', 'Spectrum South',
         'Cequel', 'Optimum', 'Comcast of Louisiana', 'Sparklight', 'Vyve', 'EATEL', 'Reveille', 'Louisiana']


def louisiana(it):
    return [c for c in it.get('cableCommunities') or [] if (c.get('communityUnitId') or '').startswith('LA')]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def peek(url):
    """Status, Location and body of one request, without following redirects."""
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=UA), timeout=45) as r:
            out = (r.status, None, r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise Blocked(url)
        out = (e.code, e.headers.get('Location'), (e.read() or b'').decode('utf-8', 'replace'))
    time.sleep(PAUSE)
    return out


def main():
    systems = {}
    for term in TERMS:
        res = get(f'{B}/api/service/facility/search/{urllib.request.quote(term)}')
        g = ((res or {}).get('results') or {}).get('globalSearchResults') or {}
        items = g.get('cableSystemsList') or []
        la = [it for it in items if louisiana(it)]
        print(f'== {term}: {len(items)} cable systems ({g.get("cableResultsCount")} counted), {len(la)} in Louisiana')
        for it in la:
            systems[it['psid']] = it
    print(f'\n== {len(systems)} Louisiana systems')
    for psid, it in sorted(systems.items()):
        cs = louisiana(it)
        parishes = sorted({c.get('countyName') for c in cs})
        print(f'  {psid} {it.get("legalName")} · {len(cs)} community units · parishes {parishes}')
    if systems:
        first = next(iter(systems.values()))
        print('\n== one entry, every key except communities:')
        print(json.dumps({k: v for k, v in first.items() if k != 'cableCommunities'}, indent=1)[:3000])

    # Profile pages for two systems, by PSID and by a community unit id.
    for psid, it in list(sorted(systems.items()))[:2]:
        cuid = louisiana(it)[0]['communityUnitId']
        for path in (f'cable-profile/{psid}', f'cable-profile/{psid}/political-files',
                     f'cable-profile/{cuid}', f'cable-profile/{cuid}/political-files'):
            status, loc, body = peek(f'{B}/{path}')
            links = sorted(set(re.findall(r'href="(/[^"]*(?:political|cable-profile)[^"]*)"', body)))[:20]
            apis = sorted(set(re.findall(r'/api/[A-Za-z0-9_/.\-{}]+', body)))[:20]
            print(f'\n== /{path}: {status} location={loc} bytes={len(body)}')
            print(f'  links {links}')
            print(f'  api refs {apis}')
            m = re.search(r'/political-files/([0-9a-f-]{36})', body)
            if m:
                for ent in (psid, cuid):
                    j = get(f'{B}/api/manager/folder/id/{m.group(1)}.json?entityId={ent}')
                    print(f'  folder {m.group(1)} entityId={ent}: {json.dumps(j)[:1500] if j else None}')
                    if j:
                        break
                break


if __name__ == '__main__':
    try:
        main()
    except Blocked as e:
        print(f'Blocked by the CDN at {e}; stopping.')
