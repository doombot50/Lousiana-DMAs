"""
summary.py — the FCC political files rolled up to buyers across stations
================================================================================
Reads data/fcc_political.json (fcc/scrape_political_files.py's listing of
every station's political-file documents) and, when asked, the cable
systems' and radio stations' (fcc_cable.json, fcc_radio.json), sorts each document to a level,
office and buyer with fcc/normalize.py, merges each buyer's spellings across
stations, and matches state candidates and PACs to their state filer
(data/filers.json). The TV page shows the result; the committee profiles
show each filer's share of it ("Booking now").
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, *p)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'fcc'))
from markets import MARKETS  # noqa: E402
from documents import agency_key  # noqa: E402
from normalize import (aliases, bucket, buyer_folder, buyer_from_filename, buyer_key,  # noqa: E402
                       classify, clean_name, dbs_buyer, fcc_url, filer_index, flight, match_filer, out_of_state,
                       parse_path, revised, tidy_caps)


def load(*p):
    with open(D(*p), encoding='utf-8') as f:
        return json.load(f)


FCC_RECENT_DAYS = 14   # "this fortnight" in the political-file section
FCC_ROWS = 40          # buyers shipped to the page
FRESH_DAYS = 3         # "new" on the races page
WEEKS = 10             # weekly document counts, for the races page's sparklines
FILES = {'tv': 'fcc_political.json', 'cable': 'fcc_cable.json', 'radio': 'fcc_radio.json',
         'dbs': 'fcc_dbs.json'}
DBS_LABEL = {'DIRECTV': 'DirecTV', 'DISH': 'Dish'}
ORDER = ['tv', 'cable', 'dbs', 'radio']   # how a buyer's stations are listed
# DirecTV files each level by state ("State/Louisiana/<buyer>"; once as
# "Louisana"): the state folder is dropped before the path is read.
LA_FOLDER = re.compile(r'/(?:Louisiana|Louisana)(?=/|$)', re.I)
RADIO_MARKET = {'Monroe': 'MON'}


def media_labels():
    """Cable PSID and radio call sign -> (label, market key), for the media
    beyond TV."""
    out = {}
    try:
        for psid, c in load('data', 'cable_systems.json').items():
            out[('cable', psid)] = (c['name'], c.get('market'))
    except FileNotFoundError:
        pass
    by_name = {v[0]: k for k, v in MARKETS.items()} | RADIO_MARKET
    for r in load('data', 'radio_stations.json'):
        out[('radio', r['call'])] = (r['call'], by_name.get(r.get('market')))
    for k, v in DBS_LABEL.items():
        out[('dbs', k)] = (v, None)
    return out


def load_documents():
    """What fcc/read_documents.py read inside the documents, by file id,
    each agency under one spelling; empty before it has run."""
    from documents import canonical_agencies
    try:
        return canonical_agencies(load('data', 'fcc_documents.json').get('documents', {}))
    except FileNotFoundError:
        return {}


def booked_totals(spent, scraped):
    """The dollars counted for Louisiana's buyers, by the week they were
    filed (Monday first; federal, state & local, issue) and by station and
    market: the same orders, each once, that the buyers' totals count."""
    if not spent:
        return None
    monday = lambda d: (date.fromisoformat(d) - timedelta(days=date.fromisoformat(d).weekday())).isoformat()
    weeks = defaultdict(lambda: [0.0, 0.0, 0.0])
    col = {'Federal': 0, 'State & local': 1, 'Issue': 2}
    calls, markets = defaultdict(float), defaultdict(float)
    for b, up, g, r in spent:
        if not up or b not in col:
            continue
        weeks[monday(up)][col[b]] += g
        calls[r['call']] += g
        if r['k']:
            markets[r['k']] += g
    first, last = min(weeks), monday(scraped)
    out, d = [], date.fromisoformat(first)
    while d.isoformat() <= last:
        out.append([d.isoformat()] + [round(v) for v in weeks.get(d.isoformat(), [0, 0, 0])])
        d += timedelta(days=7)
    return {'weeks': out, 'calls': {c: round(v) for c, v in sorted(calls.items())},
            'markets': {k: round(v) for k, v in sorted(markets.items())}}


def order_key(media, call, fname, d, did):
    """Which order a priced document belongs to, so each counts once. A
    station's order number is the station's; cable systems and radio groups
    file one order wherever it runs (every system of a sales market,
    iHeart's WYNK and KRVE), so theirs is the medium's, and a cable file
    with no number is one order by its file name."""
    no = d.get('order_no')
    if media != 'tv' and no:
        return (media, no)
    where = ('name', fname) if media in ('cable', 'dbs') else call
    return (where, no or did)


def booked(rs, docs, lines=None):
    """The dollars a buyer's documents show, from those read so far.

    An order's revisions restate the whole order, so each station order
    number counts once, at its latest revision; an invoice bills part of an
    order, so invoices count only for an order whose own document hasn't
    been read (each invoice once: a reissue repeats one). Gross, before
    agency commission: what the buyer pays. Returns None when none of the
    buyer's documents has been read. With `lines`, each dollar counted is
    appended to it as (date filed, gross, row), for totals by week, station
    and market that count exactly what the buyers' totals do."""
    orders, invoices = {}, defaultdict(dict)
    agencies = defaultdict(Counter)
    read = priced = 0
    for r in rs:
        d = docs.get(r['id'])
        if not d or d.get('status') not in ('read', 'scan'):
            continue
        read += 1
        if d.get('agency'):
            agencies[agency_key(d['agency'])][d['agency']] += 1
        if d.get('gross') is None or d.get('gross') <= 0:
            continue
        priced += 1
        key = order_key(r['m'], r['call'], r['fname'], d, r['id'])
        if d['kind'] == 'order':
            if key not in orders or r['up'] > orders[key][0]:
                orders[key] = (r['up'], d['gross'], r)
        elif d['kind'] == 'invoice' and not d.get('reissue'):
            invoices[key][d.get('invoice_no') or r['id']] = (d['gross'], r)
    if not read:
        return None
    if lines is not None:
        lines += [(up, g, r) for up, g, r in orders.values()]
        lines += [(r['up'], g, r) for k, v in invoices.items() if k not in orders for g, r in v.values()]
    invoices = {k: {i: g for i, (g, _) in v.items()} for k, v in invoices.items()}
    ordered = sum(g for _, g, _ in orders.values())
    invoiced = sum(sum(v.values()) for v in invoices.values())
    usd = ordered + sum(sum(v.values()) for k, v in invoices.items() if k not in orders)
    ag = sorted(((sum(c.values()), c.most_common(1)[0][0]) for k, c in agencies.items() if k), reverse=True)
    return {'usd': round(usd), 'ordered': round(ordered), 'invoiced': round(invoiced),
            'read': read, 'priced': priced, 'ag': [n for _, n in ag]}


def fcc_summary(markets_by_call, full=False, media=('tv',), ids=False):
    """Roll the FCC political-file listing up to buyers across stations.
    Returns None when the scrape hasn't run, so the page builds without it.
    With `full`, the result also carries every buyer (`all`), not just the
    rows the TV page shows, for the committee profiles and the races page,
    and `fresh`: the documents uploaded in the last FRESH_DAYS days.
    `media` picks the files: TV's alone by default, or with (or without)
    cable systems', satellite's and radio stations'; each buyer's stations
    then carry their medium (`m`). With `ids`, it also carries `awayIds`:
    the file ids of every document filed for another state's race, by the
    same rules that put a buyer under Out of state (build_agency_spend.py
    splits each agency's dollars with it)."""
    docs = {}
    for md in media:
        try:
            docs[md] = load('data', FILES[md])
        except FileNotFoundError:
            pass
    if not docs:
        return None
    # The first medium's file dates the rollup (TV's, unless TV isn't asked).
    fcc = docs[next(md for md in media if md in docs)]
    labels = media_labels() if set(media) - {'tv'} else {}
    entries = [(md, st) for md, d in docs.items() for st in d['stations']]
    label = {(m, st['call']): labels.get((m, st['call']), (st['call'], None))[0] if m != 'tv' else st['call']
             for m, st in entries}
    mkt = lambda m, c: markets_by_call.get(c) if m == 'tv' else labels.get((m, c), (None, None))[1]
    scraped = fcc['scraped'][:10]
    since = (date.fromisoformat(scraped) - timedelta(days=FCC_RECENT_DAYS - 1)).isoformat()
    fresh_since = (date.fromisoformat(scraped) - timedelta(days=FRESH_DAYS - 1)).isoformat()
    # Call signs to strip when a buyer is read from a file name; KVHP's
    # sister station MVHP appears in its file names too.
    calls = {s['call'].split('-')[0] for s in load('data', 'stations.json')}
    calls |= {'MVHP'}
    rows = []
    for medium, st in entries:
        for f in st['files']:
            fpath = LA_FOLDER.sub('', f['path']) if medium == 'dbs' else f['path']
            level, office, buyer = parse_path(fpath)
            if medium == 'dbs' and buyer:
                buyer = dbs_buyer(buyer)
            if not level:
                continue
            # No buyer folder (the Lake Charles stations file straight into
            # the office folder): read the buyer from the document's name.
            from_name = None if buyer else buyer_from_filename(f['name'] or '', calls)
            name = buyer or from_name or office or 'Filed without a buyer folder'
            # Another state's race carried on a Louisiana station (East Texas
            # on Shreveport's, network issue buys on sub-channels) is kept
            # apart, so it doesn't count as Louisiana spending.
            state = out_of_state(f['path']) or (from_name and out_of_state('x/x/x/' + from_name))
            b = 'Out of state' if state else bucket(level)
            year = f['path'].split('/')[1]
            # Link to the buyer's own folder at this station: its id comes from
            # the scraper's folder map, or from the file itself when it sits
            # directly in that folder. Older scrapes have neither for files
            # filed under Orders/Invoices; those fall back to the year folder.
            bpath = buyer_folder(f['path'])
            fid = (st.get('folders') or {}).get(bpath) or (f['folder_id'] if f['path'] == bpath else None)
            profile = st.get('profile') or f"tv-profile/{(st.get('fcc_call') or st['call']).lower()}"
            yf = st.get('year_folders', {}).get(year)
            link = (fcc_url(profile, bpath, fid) if fid else
                    f"https://publicfiles.fcc.gov/{profile}/political-files/{year}/{yf}" if yf else None)
            rows.append({'id': f.get('file_manager_id') or f.get('file_id'), 'link': link, 'deep': bool(fid), 'from_name': bool(from_name), 'b': b, 'level': level, 'key': buyer_key(name) or name.lower(), 'name': name, 'state': state,
                         # One document, however many times it is listed: Spectrum
                         # files the same order once per ad zone and in every
                         # system of a sales market (John Fleming's 3,048
                         # listings are 68 files), so cable and satellite count
                         # a file name once per buyer.
                         'dk': (medium, f['name']) if medium in ('cable', 'dbs') and f['name']
                               else (st['call'], f['path'], f['name'], f['uploaded']),
                         'office': office, 'call': label[(medium, st['call'])], 'm': medium,
                         'k': mkt(medium, st['call']), 'up': (f['uploaded'] or '')[:10],
                         'flight': flight(f['name'], year), 'rev': revised(f['name']),
                         'kind': classify(f['name'] or '', f['path']), 'year': year, 'fname': f['name'] or '',
                         'year_folder': st.get('year_folders', {}).get(year),
                         })
    # A race one station marks as another state's is that state's at every
    # station: KTBS files Texas's Senate race (Ken Paxton, James Talarico)
    # under plain "Federal/US Senate", KSLA under "US Senate/Texas". Matched on
    # full names only, never a bare surname.
    away_state = defaultdict(Counter)
    for r in rows:
        if r['b'] == 'Out of state':
            away_state[r['key']][r['state']] += 1
    for r in rows:
        if r['b'] != 'Out of state' and len(r['key'].split()) > 1 and r['key'] in away_state:
            r['b'], r['state'] = 'Out of state', away_state[r['key']].most_common(1)[0][0]
    # A candidate runs for one office: a full name some stations file under
    # Federal and others under State (KTVE and KARD put Julia Letlow's and
    # Misti Cordell's congressional races there) is one federal candidate.
    federal = {r['key'] for r in rows if r['b'] == 'Federal' and len(r['key'].split()) > 1}
    for r in rows:
        if r['b'] == 'State & local' and r['key'] in federal:
            r['b'] = 'Federal'
    keys = defaultdict(set)
    for r in rows:
        keys[r['b']].add(r['key'])
    alias = aliases(keys)
    groups = defaultdict(list)
    for r in rows:
        groups[(r['b'], alias[(r['b'], r['key'])])].append(r)

    # The state filer behind a buyer, so the page can link to its committee
    # profile. Federal candidates report to the FEC, not the state, and
    # other states' races aren't in the filings, so neither is matched.
    try:
        fidx = filer_index(load('data', 'filers.json'))
    except FileNotFoundError:
        fidx = {}

    documents = load_documents()
    buyers = []
    spent = []          # (bucket, date filed, gross, row) for every dollar counted
    for (b, target), rs in groups.items():
        # Each document once, dated by its first listing.
        uniq = list({r['dk']: r for r in sorted(rs, key=lambda r: r['up'], reverse=True)}.values())
        recent = [r for r in uniq if r['up'] >= since]
        fresh = sorted({(r['up'], r['call'], r['kind']) for r in rs if r['up'] >= fresh_since}, reverse=True)
        # Flights the document names give that haven't ended: when the
        # buyer is booked to be on the air, and where.
        ahead = [(r['flight'], r['call']) for r in rs if r['flight'] and r['flight'][1] >= scraped]
        wk = [0] * WEEKS
        for r in uniq:
            if r['up']:
                i = (date.fromisoformat(scraped) - date.fromisoformat(r['up'])).days // 7
                if 0 <= i < WEEKS:
                    wk[WEEKS - 1 - i] += 1
        latest = max(rs, key=lambda r: r['up'])
        # Show the cleanest spelling: one whose cleaned form is the group's own
        # key (so "Bill Cassidy", not the surname-only "Cassidy-R for US
        # Senate"), with the least left over around it ("Hillar Moore", not
        # "Hillar Moore- District Attorney"); then the most common.
        # Candidates lose the office written onto their name ("Don Landry -
        # District Attorney"); issue groups keep theirs whole ("Citizens for
        # Louisiana" is a name, not a race).
        issue = all(r['level'] == 'Issue' for r in rs)
        names = Counter(tidy_caps(clean_name(r['name'], issue)) for r in rs)
        # The spelling the key comes from before ALIASES, so a station's
        # typo ("Mike Johson") never names the group.
        name = min(names, key=lambda n: (buyer_key(n, alias=False) != target, buyer_key(n) != target,
                                         len(n) - len(target), -names[n], n))
        offices = Counter(r['office'] for r in rs if r['office'])
        # One link per station: the buyer's folder there, from that station's
        # most recent document for the buyer.
        links = {}
        for r in sorted(rs, key=lambda r: r['up']):
            if r['link'] and (r['deep'] or not links.get(r['call'], (None, False))[1]):
                links[r['call']] = (r['link'], r['deep'])
        ln = []
        money = booked(uniq, documents, ln)
        if b != 'Out of state':
            spent += [(b, up, g, r) for up, g, r in ln]
        buyers.append({
            'name': re.sub(r'\s+campaign$', '', name, flags=re.I), 'b': b, 'office': tidy_caps(offices.most_common(1)[0][0]) if offices else None,
            'state': Counter(r['state'] for r in rs if r['state']).most_common(1)[0][0]
                     if b == 'Out of state' else None,
            'docs': len(uniq), 'recent': len(recent), 'latest': latest['up'],
            'st': [{'c': c, 'k': mk, 'm': m, 'u': links.get(c, (None,))[0],
                    'd': links.get(c, (None, False))[1]}
                   for c, mk, m in sorted({(r['call'], r['k'], r['m']) for r in rs},
                                          key=lambda x: (ORDER.index(x[2]), x[0]))],
            'wk': wk,
            'revs': sum(1 for r in recent if r['rev']),
            # Recent documents certifying spots that ran (cable affidavits),
            # as against orders and requests for time still to come.
            'aired': sum(1 for r in recent if r['kind'] == 'aired'),
            # An issue group's document names, for the races page to read
            # which race it is in ("LA CD6", "Liberal Letlow").
            **({'docnames': sorted({r['fname'] for r in uniq if r['fname']})}
               if full and b == 'Issue' else {}),
            **({'onAir': [min(f[0] for f, _ in ahead), max(f[1] for f, _ in ahead),
                          sorted({c for _, c in ahead})]} if ahead else {}),
            'stRecent': sorted({r['call'] for r in rs if r['up'] >= since}),
            'fresh': [list(x) for x in fresh],
            'f': match_filer(sorted({clean_name(r['name']) for r in rs}), fidx, person=b != 'Issue')
                 if b in ('State & local', 'Issue') else None,
            **({'usd': money} if money else {}),
        })
    # Busiest this fortnight first, then the most recently active.
    buyers.sort(key=lambda x: (x['recent'], x['latest']), reverse=True)
    home = [x for x in buyers if x['b'] != 'Out of state']
    away = [x for x in buyers if x['b'] == 'Out of state']
    return {
        'scraped': scraped, 'since': since, 'days': FCC_RECENT_DAYS,
        'stations': sum(1 for s in fcc['stations'] if not s.get('stale')),
        'media': {m: sum(1 for mm, s in entries if mm == m and not s.get('stale')) for m in media},
        'weeks': WEEKS,
        'markets': sorted({MARKETS[markets_by_call[s['call']]][0] for s in fcc['stations']
                           if markets_by_call.get(s['call'])},
                          key=lambda n: [m[0] for m in MARKETS.values()].index(n)),
        'stale': [s['call'] for s in fcc['stations'] if s.get('stale')],
        'oldest': min((s.get('scraped_at') or scraped)[:10] for s in fcc['stations']) if fcc['stations'] else scraped,
        'noFile': fcc.get('no_online_file', []),
        # Stations where most buyers were read from document names.
        'byName': sorted({r['call'] for r in rows if r['from_name']}
                         - {c for c in {r['call'] for r in rows}
                            if sum(r['from_name'] for r in rows if r['call'] == c) * 2
                            < sum(1 for r in rows if r['call'] == c)}),
        # Headline counts are Louisiana's own races; out-of-state ones are
        # counted separately and listed under their own filter.
        'docs': sum(x['docs'] for x in home),
        'recentDocs': sum(x['recent'] for x in home),
        'recentBuyers': sum(1 for x in home if x['recent']),
        'byBucket': {k: sum(x['recent'] for x in home if x['b'] == k)
                     for k in ('Federal', 'State & local', 'Issue')},
        'away': {'docs': sum(x['docs'] for x in away), 'recent': sum(x['recent'] for x in away),
                 'buyers': len(away),
                 'states': [[s, n] for s, n in Counter(
                     {x['state']: 0 for x in away} | Counter(
                         s for x in away for s in [x['state']] * x['docs'])).most_common()]},
        # What the documents read so far add up to (fcc/read_documents.py
        # reads a few dozen a night, newest orders first).
        'usd': {'docs': sum(x['usd']['read'] for x in home if 'usd' in x),
                'priced': sum(x['usd']['priced'] for x in home if 'usd' in x),
                'total': sum(x['usd']['usd'] for x in home if 'usd' in x),
                'byBucket': {k: sum(x['usd']['usd'] for x in home if 'usd' in x and x['b'] == k)
                             for k in ('Federal', 'State & local', 'Issue')}},
        'booked': booked_totals(spent, scraped),
        'buyers': home[:FCC_ROWS] + away[:FCC_ROWS // 2],
        **({'all': home, 'freshSince': fresh_since} if full else {}),
        **({'awayIds': sorted({r['id'] for r in rows if r['b'] == 'Out of state' and r['id']})} if ids else {}),
    }
