#!/usr/bin/env python3
"""Throwaway: map the FCC public-file API from inside GitHub Actions."""
import json, re, urllib.request, urllib.error

B = 'https://publicfiles.fcc.gov'
H = {'User-Agent': 'louisiana-airwaves/1.0 (research)', 'Accept': 'application/json'}
ENT, Y2026 = '71357', 'aacced6c-0648-e0ff-e515-407aec48edf7'

def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')

st, body = get(f'{B}/api/manager/folder/id/{Y2026}.json?entityId={ENT}')
print('=== folder 2026', st, len(body))
d = json.loads(body)
def shape(o, depth=0):
    if isinstance(o, dict):
        return {k: shape(v, depth+1) if depth < 3 else type(v).__name__ for k, v in o.items()}
    if isinstance(o, list):
        return [f'{len(o)} items', shape(o[0], depth+1)] if o else []
    return o if not isinstance(o, str) or len(o) < 60 else o[:60]
print(json.dumps(shape(d), indent=1)[:3500])

# walk two levels down: 2026 -> Federal/State/Local/... -> race/candidate
def kids(fid):
    st, b = get(f'{B}/api/manager/folder/id/{fid}.json?entityId={ENT}')
    j = json.loads(b)
    return j
lvl1 = d
txt = json.dumps(lvl1)
sub = re.findall(r'"folder_id":\s*"([0-9a-f-]{36})"', txt)
print('subfolder ids found at 2026:', len(sub))
for fid in sub[:6]:
    j = kids(fid)
    s = json.dumps(j)
    names = re.findall(r'"folder_name":\s*"([^"]+)"', s)[:15]
    files = re.findall(r'"file_name":\s*"([^"]+)"', s)[:5]
    print('  ', fid, 'folders:', names, 'files:', files)

# search: how many results, is it paged?
st, b = get(f'{B}/api/manager/search/key/2026.json?entityId={ENT}')
j = json.loads(b)
print('=== search 2026', st, {k: (len(v) if isinstance(v, list) else v) for k, v in j.get('searchResult', {}).items()})
