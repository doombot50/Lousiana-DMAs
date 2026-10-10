#!/usr/bin/env python3
"""Throwaway: map the FCC public-file API from inside GitHub Actions."""
import json, re, urllib.request, urllib.error, html as H_

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

st, page = get(f'{B}/tv-profile/wdsu/political-files')
# every element carrying a folder id, with the text right after it
for m in re.finditer(r'<([a-z]+)[^>]*id="folder([0-9a-f-]{36})"[^>]*>(.{0,400}?)</\1>', page, re.S):
    txt = re.sub(r'\s+', ' ', H_.unescape(re.sub(r'<[^>]+>', ' ', m.group(3)))).strip()
    print('FOLDER', m.group(2), '|', txt[:120])
# any links
for href, txt in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
    if 'political' in href or 'folder' in href or 'manager' in href:
        print('LINK', href, '|', re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', txt)).strip()[:80])
i = page.find('folder07baaddf')
print('CONTEXT:', re.sub(r'\s+', ' ', page[max(0, i-1500):i+1500]))

ids = re.findall(r'id="folder([0-9a-f-]{36})"', page)
fid = ids[0] if ids else '07baaddf-105d-460a-9c33-c79d790cb790'
for u in [f'{B}/api/manager/folder/id/{fid}.json',
          f'{B}/api/manager/folder/id/{fid}',
          f'{B}/api/service/tv/facility/id/71357.json',
          f'{B}/api/manager/folder/parentFolders/71357.json',
          f'{B}/api/manager/search/key/political.json?entityId=71357']:
    st, body = get(u)
    print(f'=== {st} {u}\n{body[:1800]}')
