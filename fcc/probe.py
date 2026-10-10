#!/usr/bin/env python3
"""Throwaway: map the FCC public-file API from inside GitHub Actions, where
publicfiles.fcc.gov is reachable."""
import re, sys, urllib.request, urllib.error

B = 'https://publicfiles.fcc.gov'
H = {'User-Agent': 'louisiana-airwaves/1.0 (research)', 'Accept': 'application/json, text/html, */*'}

def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return 'ERR', str(e)

st, html = get(f'{B}/tv-profile/wdsu/political-files')
scripts = sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', html)))
print('SCRIPTS:', scripts)
inline = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
for s in inline:
    s = s.strip()
    if s and ('api' in s or 'folder' in s.lower() or 'entity' in s.lower()):
        print('INLINE:', s[:1500])
for m in sorted(set(re.findall(r'(?:data-[a-z-]+|id)="([^"]*(?:folder|entity|facility)[^"]*)"', html, re.I)))[:40]:
    print('ATTR:', m)
for src in scripts:
    if src.startswith('//'): src = 'https:' + src
    elif src.startswith('/'): src = B + src
    if 'fcc.gov' not in src or 'ruxit' in src or 'akam' in src: continue
    st, js = get(src)
    hits = sorted(set(re.findall(r'["\'`]([^"\'`\s]*/api/[^"\'`\s]{2,160})', js)))
    print(f'--- {st} {src} ({len(js):,} chars) {len(hits)} api refs')
    for h in hits[:80]:
        print('   ', h)
