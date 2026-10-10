#!/usr/bin/env python3
"""Throwaway: summarize a trial scrape and test the document download URL."""
import collections, json, urllib.request, urllib.error
d = json.load(open('data/fcc_political.json'))
for s in d['stations']:
    paths = collections.Counter(f['path'] for f in s['files'])
    depth = collections.Counter(len(p.split('/')) for p in paths)
    print(f"== {s['call']} {len(s['files'])} docs, {len(paths)} folders, depth {dict(depth)}")
    for p, n in paths.most_common(12):
        print(f'   {n:>3}  {p}')
    for f in s['files'][:4]:
        print('   newest:', f['uploaded'], '|', f['name'])
f = next(f for s in d['stations'] for f in s['files'])
for u in (f"https://publicfiles.fcc.gov/api/manager/download/{f['folder_id']}/{f['file_manager_id']}.pdf",):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'louisiana-airwaves/1.0'}), timeout=30) as r:
            print('DOWNLOAD', r.status, r.headers.get('content-type'), r.read(8), u)
    except urllib.error.HTTPError as e:
        print('DOWNLOAD', e.code, u)
