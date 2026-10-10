#!/usr/bin/env python3
"""Throwaway: does a subfolder URL depend on its slug? Two requests, 2s apart."""
import re, time, urllib.request, urllib.error
B = 'https://publicfiles.fcc.gov'
H = {'User-Agent': 'louisiana-airwaves/1.0 (+https://airwaves.charliestephens.xyz/)'}

def get(path):
    time.sleep(2)
    try:
        with urllib.request.urlopen(urllib.request.Request(B + path, headers=H), timeout=30) as r:
            body = r.read().decode('utf-8', 'replace')
            return r.status, r.geturl(), body
    except urllib.error.HTTPError as e:
        return e.code, '', ''

# 1. Cassidy's real folder id under a deliberately wrong slug.
st, final, html = get('/tv-profile/wdsu/political-files/2026/x/y/z/e07623df-f039-af36-c77e-99510141d777')
print('wrong slug:', st, final, 'lists Cassidy file:', 'Bill Cassidy 5-9 to 5-16' in html)
# 2. A folder whose name has a double space: what slug does the site itself use?
st, final, html = get('/tv-profile/katc/political-files/2026/non-candidate-issue-ads/'
                      'accountability-project-inc-del-cielo-media/0e769588-cad3-e520-dbda-7d47a5643a57')
print('double-space folder:', st, final, 'has file rows:', html.count('file-name') or html.count('.pdf'))
crumbs = re.findall(r'href="(/tv-profile/katc/political-files/[^"]+)"', html)
print('site links on that page:', [c for c in crumbs if 'accountab' in c.lower()][:3])
