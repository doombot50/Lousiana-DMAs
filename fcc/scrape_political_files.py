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

The FCC's CDN throttles bursts (a 403 after a few hundred quick requests), so
the walk is incremental and slow. Each subfolder listing carries a recursive
file count; when it matches the documents the previous run recorded under
that path, the previous documents are reused instead of re-walked. A steady
night costs about three requests a station plus whatever changed. On a 403
the scraper waits and retries once, then stops, carrying the previous data
forward for every station it didn't reach (marked `stale`).

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
PAUSE = 0.5           # seconds between requests
RETRIES = 4
BLOCK_WAIT = 90       # seconds to wait out a CDN 403 before the one retry


class Blocked(Exception):
    """The CDN is refusing us; stop for the night rather than push harder."""


def get(url, want_json=True):
    blocked_once = False
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                body = r.read().decode('utf-8', 'replace')
            time.sleep(PAUSE)
            return json.loads(body) if want_json else body
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                return None
            if isinstance(e, urllib.error.HTTPError) and e.code == 403:
                if blocked_once:
                    raise Blocked(url) from e
                blocked_once = True
                print(f'  403 from the CDN; waiting {BLOCK_WAIT}s before one retry')
                time.sleep(BLOCK_WAIT)
                continue
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


def under(prev, path):
    """Previous run's documents filed at or below `path`."""
    return [x for x in prev if x['path'] == path or x['path'].startswith(path + '/')]


def walk(fid, ent, out, prev, stats):
    """Depth-first: append every file under folder `fid` to `out`, reusing the
    previous run's documents for any subfolder whose file count is unchanged."""
    f = folder(fid, ent)
    stats['fetched'] += 1
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
        n = int(s.get('file_count') or 0)
        if not n:
            continue
        old = under(prev, s.get('folder_path', '\0'))
        if len(old) == n:
            out.extend(old)
            stats['reused'] += 1
        else:
            walk(s['entity_folder_id'], ent, out, prev, stats)


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
    try:
        previous = {s['call']: s for s in json.load(open(args.out, encoding='utf-8'))['stations']}
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        previous = {}

    t0 = time.time()
    stations, failed, no_file = [], [], []
    stats = {'fetched': 0, 'reused': 0}
    blocked = None
    for call in calls:
        prev = previous.get(call, {})
        if blocked:
            if prev:
                stations.append({**prev, 'stale': True})
            continue
        try:
            ent = facility_id(call, cache)
            if not ent:
                # Low-power (-LD) stations are exempt from the online public
                # file, so a miss there is expected rather than a failure.
                (no_file if call.endswith('-LD') else failed).append(call)
                print(f'  {call}: no LA facility match' + (' (low-power; no online file)' if call.endswith('-LD') else ''))
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
                    walk(yf['entity_folder_id'], ent, files, prev.get('files', []), stats)
            files.sort(key=lambda x: x['uploaded'] or '', reverse=True)
            stations.append({'call': call, 'facility_id': ent, 'root_folder': root,
                             'year_folders': {yf['folder_name']: yf['entity_folder_id']
                                              for yf in rf.get('subfolders') or []
                                              if yf.get('folder_name', '').isdigit()},
                             'files': files})
            print(f'  {call:<8} facility {ent:<7} {len(files):>4} documents '
                  f'(newest {files[0]["uploaded"] if files else "—"})')
        except Blocked as e:
            blocked = str(e)
            print(f'  {call}: still blocked after waiting ({e}); stopping, carrying the rest forward')
            if prev:
                stations.append({**prev, 'stale': True})
        except RuntimeError as e:
            print(f'  {call}: {e}')
            failed.append(call)
            if prev:
                stations.append({**prev, 'stale': True})

    json.dump(cache, open(D('fcc_facilities.json'), 'w', encoding='utf-8'), indent=1, sort_keys=True)
    doc = {
        'source': 'FCC public inspection files, political file folders (publicfiles.fcc.gov)',
        'scraped': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'years': years,
        'stations': stations,
        'failed': failed,
        'no_online_file': no_file,
        'blocked': blocked,
        'requests': stats,
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    n = sum(len(s['files']) for s in stations)
    fresh = sum(1 for s in stations if not s.get('stale'))
    print(f'{n:,} documents, {fresh} stations refreshed in {time.time()-t0:.0f}s '
          f'({stats["fetched"]} folders fetched, {stats["reused"]} reused unchanged)'
          + (f'; failed: {failed}' if failed else '') + f'\nWrote {args.out}')
    # A night where most stations fail is an outage, not news; refuse to publish it.
    if len(failed) > len(calls) // 2:
        sys.exit('More than half the stations failed; not trusting this run.')


if __name__ == '__main__':
    main()
