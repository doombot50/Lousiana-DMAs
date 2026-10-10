#!/usr/bin/env python3
"""Throwaway: KLAF-LD lookup, and the FCC site's URL pattern for subfolders."""
import json, re, urllib.request
B = 'https://publicfiles.fcc.gov'
H = {'User-Agent': 'louisiana-airwaves/1.0 (research)'}
get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read().decode('utf-8', 'replace')

j = json.loads(get(f'{B}/api/service/facility/search/KLAF-LD'))
g = j['results']['globalSearchResults']
print('KLAF-LD search:', j['message'], [(f['callSign'], f['communityState'], f['service'], f['id']) for f in (g.get('tvFacilityList') or [])])
j = json.loads(get(f'{B}/api/service/facility/search/KLAF'))
g = j['results']['globalSearchResults']
print('KLAF search:', j['message'], [(f['callSign'], f['communityState'], f['service'], f['id']) for f in (g.get('tvFacilityList') or [])])

d = json.load(open('data/fcc_political.json'))
for s in d['stations'][:2]:
    page = get(f"{B}/tv-profile/{s['call'].lower()}/political-files")
    year = re.search(r'href="(/tv-profile/[^"]+/political-files/2026/[0-9a-f-]{36})"', page).group(1)
    print(s['call'], 'year url', year)
    yp = get(B + year)
    for href in re.findall(r'class="nav2folder" href="([^"]+)"', yp)[:6]:
        print('   sub', href)
    f = s['files'][0]
    print('   a file folder id', f['folder_id'], f['path'])
    # does a deep folder resolve by id under any path?
    for u in (f"{B}/tv-profile/{s['call'].lower()}/political-files/2026/{f['folder_id']}",):
        try:
            t = get(u); print('   GET', u, 'ok', re.search(r'<title>(.*?)</title>', t).group(1),
                              'mentions file:', f['name'][:30] in t)
        except Exception as e:
            print('   GET', u, e)
