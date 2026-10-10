#!/usr/bin/env python3
"""Throwaway: learn the FCC site's URL for a buyer's subfolder (a handful of
requests, 2s apart) by reading the site's own subfolder links, then confirm
the pattern against a folder whose documents we already know."""
import re, time, urllib.request, urllib.error
B = 'https://publicfiles.fcc.gov'
H = {'User-Agent': 'louisiana-airwaves/1.0 (+https://airwaves.charliestephens.xyz/)'}
YEAR = '/tv-profile/wdsu/political-files/2026/aacced6c-0648-e0ff-e515-407aec48edf7'
CASSIDY = 'e07623df-f039-af36-c77e-99510141d777'
KNOWN = 'Bill Cassidy 5-9 to 5-16'

def get(path):
    time.sleep(2)
    try:
        with urllib.request.urlopen(urllib.request.Request(B + path, headers=H), timeout=30) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''

def links(html):
    return re.findall(r'class="nav2folder" href="([^"]+)"', html)

st, html = get(YEAR)
print('year', st, links(html)[:6])
fed = next((h for h in links(html) if 'federal' in h.lower()), None)
st, html = get(fed) if fed else (None, '')
print('federal', st, fed, links(html)[:6])
sen = next((h for h in links(html) if 'senate' in h.lower()), None)
st, html = get(sen) if sen else (None, '')
print('senate', st, sen, links(html)[:8])
cas = next((h for h in links(html) if CASSIDY in h), None)
print('cassidy link from site:', cas)
if cas:
    st, html = get(cas)
    print('cassidy page', st, 'lists known file:', KNOWN in html)
