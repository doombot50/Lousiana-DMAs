#!/usr/bin/env python3
"""
scrape_political_files.py — what the 30 stations' FCC political files show
================================================================================
Every broadcast station must post political ad requests, orders and invoices
to its FCC public inspection file "as soon as possible", in practice within
days. That makes the political file the earliest public signal of a TV buy:
weeks ahead of the committee's own state finance report, and the only public
record at all of federal-race buys, which Louisiana's Ethics filings never see.

    python3 fcc/scrape_political_files.py                    # all stations
    python3 fcc/scrape_political_files.py --stations WDSU KATC --years 2026

For each station in data/stations.json it resolves the FCC facility id,
finds the station's "Political Files" folder, and walks the chosen years'
folder tree, recording every document: its folder path (year / level /
office / buyer, as the station filed it), name, and upload time. Writes
data/fcc_political.json. Facility ids are cached in data/fcc_facilities.json
so a night's run doesn't re-resolve them.

Documents are listed, not read: amounts live inside PDFs whose layout varies
by station and sales system, so the file names and folders are the record.
Stdlib only. Must run where publicfiles.fcc.gov is reachable (GitHub Actions).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
D = lambda *p: os.path.join(ROOT, 'data', *p)
B = 'https://publicfiles.fcc.gov'
UA = {'User-Agent': 'louisiana-airwaves/1.0 (+https://airwaves.charliestephens.xyz/)',
      'Accept': 'application/json, text/html'}
PAUSE = 0.15          # seconds between requests: a few thousand a night, gently
RETRIES = 4


def get(url, want_json=True):
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                body = r.read().decode('utf-8', 'replace')
            time.sleep(PAUSE)
            return json.loads(body) if want_json else body
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                return None
            if attempt == RETRIES:
                raise RuntimeError(f'{url}: {e}') from e
            time.sleep(2 ** attempt)


def facility_id(call, cache):
    """FCC facility id for a call sign, from the cache or the facility search."""
    if call in cache:
        return cache[call]
    res = get(f'{B}/api/service/facility/search/{call}')
    tv = ((res or {}).get('results') or {}).get('globalSearchResults', {}).get('tvFacilityList') or []
    hits = [f for f in tv if f.get('callSign', '').upper() == call.upper()
            and f.get('communityState') == 'LA']
    if len(hits) != 1:
        print(f'  {call}: {len(hits)} exact LA matches in facility search; skipped')
        return None
    cache[call] = hits[0]['id']
    return cache[call]


def political_root(call):
    """Folder id of the station's "Political Files" root, from its profile page."""
    page = get(f'{B}/tv-profile/{call.lower()}/political-files', want_json=False) or ''
    m = re.search(r'href="/tv-profile/[^/"]+/political-files/([0-9a-f-]{36})"', page)
    return m.group(1) if m else None


def folder(fid, ent):
    j = get(f'{B}/api/manager/folder/id/{fid}.json?entityId={ent}')
    return (j or {}).get('folder')


def walk(fid, ent, out):
    """Depth-first: append every file under folder `fid` to `out`."""
    f = folder(fid, ent)
    if not f:
        return
    for x in f.get('files') or []:
        out.append({
            'path': f['folder_path'],
            'name': x.get('file_name'),
            'ext': x.get('file_extension'),
            'uploaded': x.get('create_ts'),
            'folder_id': f['entity_folder_id'],
            'file_id': x.get('file_id'),
            'file_manager_id': x.get('file_manager_id'),
        })
    for s in f.get('subfolders') or []:
        if int(s.get('file_count') or 0) > 0:
            walk(s['entity_folder_id'], ent, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stations', nargs='*', help='call signs (default: all in stations.json)')
    ap.add_argument('--years', nargs='*', type=int,
                    help='political-file years to walk (default: this year and next)')
    ap.add_argument('--out', default=D('fcc_political.json'))
    args = ap.parse_args()

    this = time.gmtime().tm_year
    years = args.years or [this, this + 1]
    calls = args.stations or [s['call'] for s in json.load(open(D('stations.json'), encoding='utf-8'))]
    try:
        cache = json.load(open(D('fcc_facilities.json'), encoding='utf-8'))
    except FileNotFoundError:
        cache = {}

    t0 = time.time()
    stations, failed = [], []
    for call in calls:
        try:
            ent = facility_id(call, cache)
            if not ent:
                failed.append(call)
                continue
            root = political_root(call)
            if not root:
                print(f'  {call}: no political-files folder found')
                failed.append(call)
                continue
            rf = folder(root, ent) or {}
            files = []
            for yf in rf.get('subfolders') or []:
                if yf.get('folder_name', '').isdigit() and int(yf['folder_name']) in years:
                    walk(yf['entity_folder_id'], ent, files)
            files.sort(key=lambda x: x['uploaded'] or '', reverse=True)
            stations.append({'call': call, 'facility_id': ent, 'root_folder': root, 'files': files})
            print(f'  {call:<8} facility {ent:<7} {len(files):>4} documents '
                  f'(newest {files[0]["uploaded"] if files else "—"})')
        except RuntimeError as e:
            print(f'  {call}: {e}')
            failed.append(call)

    json.dump(cache, open(D('fcc_facilities.json'), 'w', encoding='utf-8'), indent=1, sort_keys=True)
    doc = {
        'source': 'FCC public inspection files, political file folders (publicfiles.fcc.gov)',
        'scraped': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'years': years,
        'stations': stations,
        'failed': failed,
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    n = sum(len(s['files']) for s in stations)
    print(f'{n:,} documents from {len(stations)} stations in {time.time()-t0:.0f}s'
          + (f'; failed: {failed}' if failed else '') + f'\nWrote {args.out}')
    # A night where most stations fail is an outage, not news; refuse to publish it.
    if len(failed) > len(calls) // 2:
        sys.exit('More than half the stations failed; not trusting this run.')


if __name__ == '__main__':
    main()
