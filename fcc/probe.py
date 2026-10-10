#!/usr/bin/env python3
"""Throwaway: map the FCC public-file API from inside GitHub Actions, where
publicfiles.fcc.gov is reachable. Prints status + a head of each response."""
import json, sys, urllib.request, urllib.error

B = 'https://publicfiles.fcc.gov'
URLS = sys.argv[1:] or [
    f'{B}/api/service/facility/search/WDSU.json',
    f'{B}/api/service/tv/facility/search/WDSU.json',
    f'{B}/api/service/facility/search/WDSU',
    f'{B}/api/manager/search/key/WDSU.json',
    f'{B}/tv-profile/wdsu',
    f'{B}/tv-profile/wdsu/political-files',
    f'{B}/api/manager/folder/path/tv/wdsu/political_file.json',
    f'{B}/developer/',
]

for u in URLS:
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'louisiana-airwaves/1.0 (research)',
                                                 'Accept': 'application/json, text/html'})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            print(f'=== {r.status} {u}  ({len(body):,} bytes, {r.headers.get("content-type")})')
    except urllib.error.HTTPError as e:
        body = e.read()
        print(f'=== {e.code} {u}')
    except Exception as e:
        print(f'=== ERR {u}: {e}'); continue
    text = body.decode('utf-8', 'replace')
    print(text[:2500])
    # surface any API paths the HTML references
    import re
    for m in sorted(set(re.findall(r'["\'](/api/[^"\']{3,120})["\']', text)))[:60]:
        print('  ref:', m)
