#!/usr/bin/env python3
"""
scrape_political_files.py — what the 30 stations' FCC political files show
================================================================================
Every broadcast station must post political ad requests, orders and invoices
to its FCC public inspection file "as soon as possible", in practice within
days. That makes the political file the earliest public signal of a TV buy:
weeks ahead of the committee's own state finance report, and the only public
record at all of federal-race buys, which Louisiana's Ethics filings never see.

    python3 fcc/scrape_political_files.py                    # TV stations
    python3 fcc/scrape_political_files.py --stations WDSU KATC --years 2026
    python3 fcc/scrape_political_files.py --media cable      # cable systems
    python3 fcc/scrape_political_files.py --media radio      # radio stations
    python3 fcc/scrape_political_files.py --media dbs        # DirecTV, Dish (Louisiana's folders)

Cable systems (data/cable_systems.json, from fcc/find_cable.py) and radio
stations (data/radio_stations.json) file the same way, under their own
profile pages; `--media` picks which, each written to its own file
(fcc_political.json, fcc_cable.json, fcc_radio.json) with its own rotation.

For each station in data/stations.json it resolves the FCC facility id,
finds the station's "Political Files" folder, and walks the chosen years'
folder tree, recording every document: its folder path (year / level /
office / buyer, as the station filed it), name, and upload time. Writes
data/fcc_political.json. Facility ids are cached in data/fcc_facilities.json
so a night's run doesn't re-resolve them.

The FCC's CDN blocks scripted traffic it judges heavy: a burst of a few
hundred requests drew 403s that then held for every request, even from a
fresh runner. So a night asks for little. It refreshes at most
--max-stations stations (default 8), least recently scraped first, so the 28
stations with online files rotate through every few nights (faster as an
election nears; see stations_tonight), and the walk is
incremental and slow. Each subfolder listing carries a recursive
file count; when it matches the documents the previous run recorded under
that path, the previous documents are reused instead of re-walked. A steady
night costs about three requests a station plus whatever changed. On a 403
the scraper waits and retries once, then stops, carrying the previous data
forward for every station it didn't reach. Each station records when it
was last scraped (`scraped_at`); one not refreshed in a week is `stale`.

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
PAUSE = 2.0           # seconds between requests
STALE_DAYS = 7
RETRIES = 4
BLOCK_WAIT = 90       # seconds to wait out a CDN 403 before the one retry


class Blocked(Exception):
    """The CDN is refusing us; stop for the night rather than push harder."""


SENT = [0]            # requests made this run, for --budget


def get(url, want_json=True):
    SENT[0] += 1
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
    """(facility id, the FCC's spelling of the call sign) for a call sign, from
    the cache or the facility search; (None, None) when it can't be matched."""
    if call in cache:
        hit = cache[call]
        # Older cache entries are a bare id, written when the spellings agreed.
        return (hit, call) if isinstance(hit, str) else (hit['id'], hit['call'])
    res = get(f'{B}/api/service/facility/search/{call}')
    tv = ((res or {}).get('results') or {}).get('globalSearchResults', {}).get('tvFacilityList') or []
    hits = [f for f in tv if f.get('callSign', '').upper() == call.upper()]
    # The FCC often licenses the bare call with a suffix our filings drop:
    # WBRZ is "WBRZ-TV" there, WVUE "WVUE-DT". Fall back to a match on the
    # base call sign; the uniqueness check below still guards it.
    if not hits:
        base = call.upper().split('-')[0]
        hits = [f for f in tv if f.get('callSign', '').upper().split('-')[0] == base]
    # Prefer a Louisiana licence, but keep a lone exact match elsewhere: KTVE,
    # in the Monroe market, is licensed to El Dorado, Arkansas.
    if len(hits) > 1:
        hits = [f for f in hits if f.get('communityState') == 'LA']
    if len(hits) != 1:
        # Say what the search did return; it costs no extra request, and it's
        # the only way to see why a station doesn't match.
        print(f'  {call}: search returned ' + (', '.join(
            f"{f.get('callSign')} ({f.get('communityCity')}, {f.get('communityState')}; id {f.get('id')})"
            for f in tv[:6]) or 'no TV facilities'))
        return None, None
    fcc_call = hits[0]['callSign']
    cache[call] = hits[0]['id'] if fcc_call.upper() == call.upper() else \
        {'id': hits[0]['id'], 'call': fcc_call}
    return hits[0]['id'], fcc_call


def political_root(profile):
    """Folder id of the "Political Files" root, from the profile page
    (`profile` like "tv-profile/wdsu", "cable-profile/002460")."""
    page = get(f'{B}/{profile}/political-files', want_json=False) or ''
    m = re.search(r'href="/[a-z]+-profile/[^/"]+/political-files/([0-9a-f-]{36})"', page)
    return m.group(1) if m else None


def radio_facility(call, cache):
    """(facility id, profile path) for a radio call sign: the Louisiana AM
    or FM licence whose call sign is this one, with or without -FM."""
    key = 'radio:' + call
    if key in cache:
        return cache[key]['id'], cache[key]['profile']
    res = get(f'{B}/api/service/facility/search/{call}')
    g = ((res or {}).get('results') or {}).get('globalSearchResults', {})
    hits = [(f, band) for band, lst in (('fm', g.get('fmFacilityList')), ('am', g.get('amFacilityList')))
            for f in lst or [] if f.get('communityState') == 'LA'
            and f.get('callSign', '').upper().split('-')[0] == call.upper().split('-')[0]]
    if len(hits) > 1:   # an AM and its FM sister: the call as written decides
        exact = [h for h in hits if h[0]['callSign'].upper() == call.upper()]
        hits = exact or [h for h in hits if h[1] == 'fm']
    if len(hits) != 1:
        print(f'  {call}: radio search returned ' + (', '.join(
            f"{f.get('callSign')} ({f.get('communityCity')}, {f.get('communityState')})" for f, _ in hits[:6])
            or 'no Louisiana match'))
        return None, None
    f, band = hits[0]
    cache[key] = {'id': f['id'], 'profile': f"{band}-profile/{f['callSign'].lower()}"}
    return cache[key]['id'], cache[key]['profile']


# Per medium: where the list comes from, the output file, and how many to
# refresh a night (normally, within 30 days of an election, within 10).
MEDIA = {
    'tv':    {'out': 'fcc_political.json', 'pace': (8, 14, 28)},
    'cable': {'out': 'fcc_cable.json', 'pace': (6, 13, 25)},
    'radio': {'out': 'fcc_radio.json', 'pace': (10, 20, 34)},
    # DirecTV and Dish file nationally, sorted by state; only Louisiana's
    # folders are walked.
    'dbs':   {'out': 'fcc_dbs.json', 'pace': (2, 2, 2)},
}
DBS = {'DIRECTV': 'directv', 'DISH': 'dish'}


def entities(media):
    """The call signs (TV, radio) or PSIDs (cable) a medium covers. Cable
    systems come biggest first and radio stations by political spending, so
    the rotation's first nights, when nothing has been scraped, reach the
    ones that matter (Cox, WWL) before the long tail."""
    if media == 'tv':
        return [s['call'] for s in json.load(open(D('stations.json'), encoding='utf-8'))]
    if media == 'dbs':
        return list(DBS)
    if media == 'cable':
        try:
            systems = json.load(open(D('cable_systems.json'), encoding='utf-8'))
        except FileNotFoundError:
            return []
        return sorted(systems, key=lambda p: (-systems[p].get('units', 0), p))
    try:
        spent = {s['call']: s['spend'] for s in json.load(open(D('radio_spend.json'), encoding='utf-8'))['stations']}
    except (FileNotFoundError, KeyError):
        spent = {}
    calls = [s['call'] for s in json.load(open(D('radio_stations.json'), encoding='utf-8'))]
    return sorted(calls, key=lambda c: -spent.get(c, 0))


def resolve(media, call, cache):
    """(entity id, profile path, the FCC's name for it) or (None, None, None)."""
    if media == 'cable':
        return call, f'cable-profile/{call}', call
    if media == 'dbs':
        return call, f'dbs-profile/{DBS[call]}', call
    if media == 'radio':
        ent, profile = radio_facility(call, cache)
        return ent, profile, profile and profile.split('/')[1].upper()
    ent, fcc_call = facility_id(call, cache)
    return ent, ent and f'tv-profile/{fcc_call.lower()}', fcc_call


def folder(fid, ent):
    j = get(f'{B}/api/manager/folder/id/{fid}.json?entityId={ent}')
    return (j or {}).get('folder')


def under(prev, path):
    """Previous run's documents filed at or below `path`."""
    return [x for x in prev if x['path'] == path or x['path'].startswith(path + '/')]


STATES = set("""Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia
Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky Maine Maryland Massachusetts Michigan Minnesota
Mississippi Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah
Vermont Virginia Washington Wisconsin Wyoming""".split()) | {
    'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota',
    'Rhode Island', 'South Carolina', 'South Dakota', 'West Virginia', 'District of Columbia',
    'Puerto Rico', 'Guam'}


def other_state(name):
    """A folder for another state's races, or for national and multi-state
    buys, in a national file (DirecTV sorts each level by state)."""
    return name.strip() in STATES or bool(re.match(r'multi-?state|national', name.strip(), re.I))


def walk(fid, ent, out, prev, stats, folders, prev_folders, skip=None):
    """Depth-first: append every file under folder `fid` to `out`, reusing the
    previous run's documents for any subfolder whose file count is unchanged.
    Records every folder's id by path in `folders`, so the page can link to a
    buyer's own folder rather than the document subfolder a file sits in.
    Subfolders whose name `skip` accepts aren't walked."""
    f = folder(fid, ent)
    stats['fetched'] += 1
    if not f:
        return
    folders[f['folder_path']] = f['entity_folder_id']
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
        if not n or (skip and skip(s.get('folder_name') or '')):
            continue
        path = s.get('folder_path', '\0')
        folders[path] = s['entity_folder_id']
        old = under(prev, path)
        if len(old) == n:
            out.extend(old)
            folders.update({p: i for p, i in prev_folders.items() if p.startswith(path + '/')})
            stats['reused'] += 1
        else:
            walk(s['entity_folder_id'], ent, out, prev, stats, folders, prev_folders, skip)


def default_years(this):
    """The political-file years a night walks: this year and next, and in an
    odd year the even year before it too. Louisiana's cycle pairs them, the
    federal midterm (2026) then the governor's race (2027), and stations
    file early buys for an odd-year race in the even year's folder, so on
    1 January 2027 the 2026 folders must stay in view rather than drop out.
    In an even year the previous (odd) year's races are over."""
    return ([this - 1] if this % 2 else []) + [this, this + 1]


# Stations a night by days to the next election on data/ballot.json: the
# political files move fastest in the last weeks, so each medium's rotation
# tightens (TV to every other night, then every night). A steady station
# costs about three requests, so even TV, cable and radio together stay well
# under the bursts that drew the CDN's 403s.
def stations_tonight(default, today, ballot=D('ballot.json'), close=(14, 28)):
    """How many stations to refresh tonight: `default`, or `close` (within
    30 days, within 10) when an election on the ballot file is near."""
    try:
        with open(ballot, encoding='utf-8') as f:
            days = sorted(e['date'] for e in json.load(f).get('elections', []))
    except (OSError, ValueError, KeyError):
        return default
    ahead = [(time.mktime(time.strptime(d, '%Y-%m-%d')) - time.mktime(time.strptime(today, '%Y-%m-%d'))) / 86400
             for d in days]
    ahead = [a for a in ahead if a >= 0]
    if not ahead:
        return default
    return max([default] + [n for within, n in ((30, close[0]), (10, close[1])) if min(ahead) <= within])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stations', nargs='*', help='call signs (default: all in stations.json)')
    ap.add_argument('--years', nargs='*', type=int,
                    help='political-file years to walk (default: this year and next, plus last '
                         'year in an odd year; see default_years)')
    ap.add_argument('--max-stations', type=int,
                    help='stations to refresh this run, least recently scraped first '
                         '(default 8, more in the last 30 days before an election)')
    ap.add_argument('--media', choices=sorted(MEDIA), default='tv')
    ap.add_argument('--budget', type=int, default=250,
                    help='requests this run may make; once spent, the stations still due wait '
                         'for the next run (a first walk of a station can cost hundreds)')
    ap.add_argument('--out', help='default: data/fcc_political.json, fcc_cable.json or fcc_radio.json')
    args = ap.parse_args()
    m = MEDIA[args.media]
    args.out = args.out or D(m['out'])

    years = args.years or default_years(time.gmtime().tm_year)
    if args.max_stations is None:
        args.max_stations = stations_tonight(m['pace'][0], time.strftime('%Y-%m-%d', time.gmtime()),
                                             close=m['pace'][1:])
        print(f'Refreshing up to {args.max_stations} {args.media} political files tonight')
    calls = args.stations or entities(args.media)
    try:
        cache = json.load(open(D('fcc_facilities.json'), encoding='utf-8'))
    except FileNotFoundError:
        cache = {}
    try:
        previous = {s['call']: s for s in json.load(open(args.out, encoding='utf-8'))['stations']}
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        previous = {}
    try:
        attempted = json.load(open(args.out, encoding='utf-8')).get('attempted', {})
    except (FileNotFoundError, json.JSONDecodeError):
        attempted = {}

    # Rotation: never-scraped stations first, then the longest-unrefreshed.
    # An explicit --stations list is taken as asked.
    # Low-power (-LD) stations are exempt from the online public file, so they
    # are listed as such without spending a request on them.
    no_file = [c for c in calls if c.endswith('-LD')]
    calls = [c for c in calls if not c.endswith('-LD')]
    if not args.stations:
        # A station that failed counts as attempted, so it goes to the back of
        # the queue instead of taking a slot every night.
        order = sorted(calls, key=lambda c: max(previous.get(c, {}).get('scraped_at', ''),
                                                 attempted.get(c, '')))
        due = set(order[:args.max_stations])
    else:
        due = set(calls)
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    t0 = time.time()
    stations, failed, unmatched = [], [], []
    stats = {'fetched': 0, 'reused': 0}
    blocked = None
    deferred = []
    for call in calls:
        prev = previous.get(call, {})
        if call in due and not blocked and SENT[0] >= args.budget:
            deferred.append(call)
            due.discard(call)
        if blocked or call not in due:
            if prev:
                stations.append(prev)
            continue
        attempted[call] = now
        try:
            ent, profile, fcc_call = resolve(args.media, call, cache)
            if not ent:
                # A listing mismatch, not an outage: it is reported, and the
                # station waits its turn again, but it doesn't count toward the
                # "most of the night failed" check below.
                unmatched.append(call)
                print(f'  {call}: no facility match')
                continue
            root = political_root(profile)
            if not root:
                print(f'  {call}: no political-files folder found')
                failed.append(call)
                continue
            rf = folder(root, ent) or {}
            files, folders = [], {}
            for yf in rf.get('subfolders') or []:
                if yf.get('folder_name', '').isdigit() and int(yf['folder_name']) in years:
                    walk(yf['entity_folder_id'], ent, files, prev.get('files', []), stats,
                         folders, prev.get('folders', {}), other_state if args.media == 'dbs' else None)
            files.sort(key=lambda x: x['uploaded'] or '', reverse=True)
            stations.append({'call': call, 'fcc_call': fcc_call, 'facility_id': ent, 'root_folder': root,
                             'profile': profile,
                             'scraped_at': now,
                             'year_folders': {yf['folder_name']: yf['entity_folder_id']
                                              for yf in rf.get('subfolders') or []
                                              if yf.get('folder_name', '').isdigit()},
                             'folders': dict(sorted(folders.items())),
                             'files': files})
            print(f'  {call:<8} facility {ent:<7} {len(files):>4} documents '
                  f'(newest {files[0]["uploaded"] if files else "—"})')
        except Blocked as e:
            blocked = str(e)
            print(f'  {call}: still blocked after waiting ({e}); stopping, carrying the rest forward')
            if prev:
                stations.append(prev)
        except RuntimeError as e:
            print(f'  {call}: {e}')
            failed.append(call)
            if prev:
                stations.append(prev)

    # A night where most stations fail is an outage, not news: leave the
    # previous night's file in place rather than publish it.
    refreshed = [s for s in stations if s.get('scraped_at') == now]
    if blocked and not refreshed:
        sys.exit(f'Blocked before any station refreshed; keeping the previous {os.path.basename(args.out)}.')
    if len(failed) > len(due) // 2:
        sys.exit(f'{len(failed)} of {len(due)} stations due failed ({failed}); '
                 f'keeping the previous {os.path.basename(args.out)}.')

    json.dump(cache, open(D('fcc_facilities.json'), 'w', encoding='utf-8'), indent=1, sort_keys=True)
    cutoff = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - STALE_DAYS * 86400))
    for st in stations:
        st['stale'] = st.get('scraped_at', '') < cutoff
    doc = {
        'source': 'FCC public inspection files, political file folders (publicfiles.fcc.gov)',
        'media': args.media,
        'scraped': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'years': years,
        'stations': stations,
        'failed': failed,
        'unmatched': unmatched,
        'no_online_file': no_file,
        'blocked': blocked,
        'attempted': dict(sorted(attempted.items())),
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    n = sum(len(s['files']) for s in stations)
    print(f'{n:,} documents across {len(stations)} stations; {len(refreshed)} refreshed in {time.time()-t0:.0f}s '
          f'({stats["fetched"]} folders fetched, {stats["reused"]} reused unchanged)'
          + (f'; failed: {failed}' if failed else '')
          + (f'; no facility match: {unmatched}' if unmatched else '')
          + (f'; {len(deferred)} left for the next run, request budget spent: {deferred}' if deferred else '')
          + f'\n{SENT[0]} requests\nWrote {args.out}')


if __name__ == '__main__':
    main()
