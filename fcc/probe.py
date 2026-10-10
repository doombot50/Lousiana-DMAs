#!/usr/bin/env python3
"""Throwaway: after a full scrape, learn the FCC site's subfolder URL pattern
(two requests) and print a compact summary of what was collected."""
import collections, json, re, time, urllib.request
B = 'https://publicfiles.fcc.gov'
H = {'User-Agent': 'louisiana-airwaves/1.0 (research)'}
get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read().decode('utf-8', 'replace')
d = json.load(open('data/fcc_political.json'))
print('failed', d['failed'], 'no_online_file', d['no_online_file'], 'blocked', d['blocked'], d['requests'])
for s in d['stations']:
    lv = collections.Counter(f['path'].split('/')[2] if f['path'].count('/') >= 2 else '?' for f in s['files'])
    print(f"{s['call']:<8} {len(s['files']):>4}  {dict(lv)}  newest {s['files'][0]['uploaded'] if s['files'] else '-'}")
time.sleep(60)
s = next(s for s in d['stations'] if s['files'])
y = s['year_folders'].get('2026')
try:
    page = get(f"{B}/tv-profile/{s['call'].lower()}/political-files/2026/{y}")
    print('year page subfolder hrefs:', re.findall(r'class="nav2folder" href="([^"]+)"', page)[:5])
except Exception as e:
    print('year page', e)
