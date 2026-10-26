#!/usr/bin/env python3
"""
build_agency_spend.py — the media agencies between committees and stations
================================================================================
The TV and radio pages count what committees paid stations directly. Much of
the money doesn't go that way: a campaign pays a media-buying agency, and
the agency pays the stations, so the filings name the agency and never the
station. This finds those agencies two ways and joins them:

  1. **The stations name them.** fcc/read_documents.py reads the political
     file's orders, invoices and request forms, which name the agency that
     placed each buy ("Agency Name: Kingfish Communications LLC"). For each
     agency: the stations, the clients, and the gross its orders read so far
     add up to.
  2. **The filings pay them.** Every expenditure row whose payee is one of
     those agencies, under any spelling (fcc/documents.py's agency_key), and,
     for the history the political files don't reach, every payee committees
     paid at least $100,000 for work their reports describe as TV, broadcast
     or a media buy.

What a committee paid an agency isn't all airtime: the same firm may be paid
for production and consulting. `media` is the part whose description says
TV, broadcast, air time or media; `total` is everything.

    python3 build_agency_spend.py                     # auto-finds the cache

Writes data/agencies.json. Run after fcc/read_documents.py. Stdlib only.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'fcc'))
from build_station_spend import stations_in  # noqa: E402
from documents import agency_key, canonical_agencies, same_agency, same_party  # noqa: E402
from summary import order_key  # noqa: E402
from filings import cache_files, find_cache, norm, party_of, scan  # noqa: E402

D = lambda *p: os.path.join(HERE, 'data', *p)

# A payment the filer describes as airtime or a media buy.
MEDIA = re.compile(r'media\s*buy|media\s*placement|\btv\b|television|air\s*time|broadcast|'
                   r'cable\s*buy|tv\s*buy|spot\s*buy', re.I)
# Payees that sell time rather than buy it: cable and satellite ad sales,
# station groups and their reps, radio groups, the big digital platforms.
SELLER = re.compile(r'\b(?:COX|NCC|AMPERSAND|SPECTRUM|CHARTER|COMCAST|EFFECTV|DIRECTV|DISH|SUDDENLINK|'
                    r'VIAMEDIA|GOOGLE|FACEBOOK|META|IHEART|CUMULUS|TOWNSQUARE|AUDACY|ENTERCOM|GRAY|'
                    r'NEXSTAR|TEGNA|HEARST|SINCLAIR|KATZ|BELO|RAYCOM|LIBCO|AT\s?T|U\s?VERSE|YOUTUBE|HULU|ROKU|AMAZON|'
                    r'TWITTER|SNAPCHAT|SPOTIFY|PANDORA)\b')
HISTORY_MIN = 100_000      # media dollars for a payee to count without a station naming it
CYCLE_YEARS = 4            # "this cycle": the four filing years through this one


def documents():
    try:
        return canonical_agencies(json.load(open(D('fcc_documents.json'), encoding='utf-8')).get('documents', {}))
    except FileNotFoundError:
        return {}


def client_name(s):
    """An advertiser as read off a document, without the station's prefix
    ("POL/"), dates a contract prints beside it, or OCR's brackets."""
    s = re.sub(r'^(?:POL|ISS)\s*/\s*', '', s or '', flags=re.I)
    s = re.sub(r'[«»\[\]{}|]', ' ', s)
    s = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}(?:\s*/\s*)?', ' ', s)
    return re.sub(r'\s+', ' ', s).strip(' .,:;-/')


def top_clients(counter, n):
    """The most frequent clients, each once: spellings whose letters one
    contains the other's ("Accountability Project, Inc", "ountability
    Project") are one client, named by its most frequent spelling."""
    out = []
    for name, _ in counter.most_common():
        k = re.sub(r'[^a-z]', '', re.sub(r'\b(?:inc|llc|the)\b', '', name.lower()))
        if len(k) < 4 or any(k in o or o in k for o, _ in out):
            continue
        out.append((k, name))
    return [nm for _, nm in out[:n]]


def away_ids():
    """File ids of the political-file documents filed for another state's
    race (Texas's on Shreveport stations, network issue buys on
    sub-channels), as fcc/summary.py sorts them; empty before a scrape."""
    from summary import fcc_summary
    F = fcc_summary({}, media=('tv', 'cable', 'radio', 'dbs'), ids=True)
    return set((F or {}).get('awayIds', []))


def fcc_agencies(docs, away=frozenset()):
    """Agency key -> what the political-file documents say about it, each
    figure kept apart for Louisiana's races and other states' (`away`, file
    ids): an agency buying Texas's Senate race on Shreveport stations isn't
    Louisiana money."""
    side = lambda: {'clients': Counter(), 'docs': 0, 'orders': {}}
    out = defaultdict(lambda: {'names': Counter(), 'stations': set(), 'first': None, 'last': None,
                               'la': side(), 'away': side()})
    for did, d in docs.items():
        a = d.get('agency')
        if d.get('status') != 'read' or not a or same_party(a, d.get('advertiser')):
            continue
        k = agency_key(a)
        if not k or len(k) < 3:
            continue
        x = out[k]
        x['names'][a] += 1
        x['stations'].add((d.get('media') or 'tv', d.get('call')))
        up = (d.get('uploaded') or '')[:10]
        x['first'] = min(filter(None, [x['first'], up])) if up else x['first']
        x['last'] = max(filter(None, [x['last'], up])) if up else x['last']
        y = x['away' if did in away else 'la']
        y['docs'] += 1
        client = client_name(d.get('advertiser'))
        if client:
            y['clients'][client] += 1
        # Each order once at its latest revision; invoices only stand in
        # for an order not read (as fcc/summary.py's booked()).
        if d.get('gross') and d['gross'] > 0 and d.get('kind') in ('order', 'invoice') and not d.get('reissue'):
            key = order_key(d.get('media') or 'tv', d.get('call'), d.get('name'), d, did)
            prev = y['orders'].get(key)
            if d['kind'] == 'order':
                if not prev or prev[0] != 'order' or up > prev[1]:
                    y['orders'][key] = ('order', up, d['gross'], {})
            else:
                inv = prev[3] if prev and prev[0] == 'invoice' else {}
                inv[d.get('invoice_no') or did] = d['gross']
                if not prev or prev[0] == 'invoice':
                    y['orders'][key] = ('invoice', up, sum(inv.values()), inv)
    return out


def builder(args, files):
    docs = documents()
    stations = json.load(open(D('stations.json'), encoding='utf-8'))
    callset = {s['call'].split('-')[0] for s in stations}
    fcc = fcc_agencies(docs, away_ids())
    fcc_keys = sorted(fcc, key=len, reverse=True)
    this_year = int(time.strftime('%Y'))

    paid = defaultdict(lambda: {'total': 0.0, 'media': 0.0, 'media_cycle': 0.0, 'rows': 0, 'years': defaultdict(float),
                                'by': defaultdict(lambda: [0.0, 0.0]), 'names': Counter()})
    fname = defaultdict(Counter)
    fparty = defaultdict(Counter)
    match = {}

    def which(raw):
        """The FCC agency a payee is, its own key, or None for a station or
        a seller of time."""
        if raw in match:
            return match[raw]
        n = norm(raw)
        if stations_in(n, callset) or SELLER.search(n):
            match[raw] = None
            return None
        k = agency_key(raw)
        hit = next((fk for fk in fcc_keys if same_agency(k, fk)), None)
        match[raw] = hit or k or None
        return match[raw]

    def add(r, yr):
        raw = (r.get('contributor') or '').strip()
        amt = float(r.get('amount') or 0)
        if not raw or amt <= 0:
            return
        k = which(raw)
        if not k:
            return
        fn = (r.get('filerNumber') or '').strip()
        p = paid[k]
        media = bool(MEDIA.search(r.get('description') or ''))
        p['total'] += amt
        p['media'] += amt if media else 0
        p['media_cycle'] += amt if media and yr > this_year - CYCLE_YEARS else 0
        p['rows'] += 1
        p['years'][yr] += amt
        p['names'][raw.upper()] += 1
        if fn:
            p['by'][fn][0] += amt
            p['by'][fn][1] += amt if yr > this_year - CYCLE_YEARS else 0
            if r.get('candidate'):
                fname[fn][r['candidate']] += 1
            if r.get('party'):
                fparty[fn][r['party']] += 1

    def finish(scanned, latest):
        def name(fn):
            return fname[fn].most_common(1)[0][0] if fname[fn] else f'filer {fn}'

        def party(fn):
            return party_of(fparty[fn].most_common(1)[0][0] if fparty[fn] else None, fn)

        keys = set(fcc) | {k for k, p in paid.items() if p['media'] >= HISTORY_MIN}
        rows = []
        for k in keys:
            f, p = fcc.get(k), paid.get(k)
            label = (f['names'].most_common(1)[0][0] if f else
                     p['names'].most_common(1)[0][0].title())
            label = re.sub(r'[\s,.]+(?:LLC|Inc|L\.L\.C)\.?$', '', label, flags=re.I).strip()
            row = {'key': k, 'name': label, 'found_by': 'political file' if f else 'filings'}
            if f:
                la, aw = f['la'], f['away']
                row['fcc'] = {'docs': la['docs'], 'priced': len(la['orders']),
                              'usd': round(sum(o[2] for o in la['orders'].values())),
                              'stations': sorted(c for _, c in f['stations'] if c),
                              'clients': top_clients(la['clients'], 12),
                              'first': f['first'], 'last': f['last'],
                              # Other states' races the agency bought on Louisiana stations.
                              'away': {'docs': aw['docs'], 'usd': round(sum(o[2] for o in aw['orders'].values())),
                                       'clients': top_clients(aw['clients'], 6)}}
            if p and p['rows']:
                # This cycle's payers first; all-time only breaks ties.
                top = sorted(p['by'].items(), key=lambda x: (-x[1][1], -x[1][0]))
                row['paid'] = {
                    'total': round(p['total']), 'media': round(p['media']), 'rows': p['rows'],
                    'media_cycle': round(p['media_cycle']),
                    'cycle': round(sum(v for y, v in p['years'].items() if y > this_year - CYCLE_YEARS)),
                    'years': {str(y): round(v) for y, v in sorted(p['years'].items())},
                    'committees': len(p['by']),
                    'top': [{'f': fn, 'n': name(fn), 'p': party(fn), 'usd': round(v[0]), 'cycle': round(v[1])}
                            for fn, v in top[:15]],
                    'spellings': [s for s, _ in p['names'].most_common(6)],
                }
            rows.append(row)
        rows.sort(key=lambda r: (-(r.get('fcc', {}).get('usd', 0) + r.get('paid', {}).get('media_cycle', 0)),
                                 -r.get('paid', {}).get('media', 0), r['name']))
        # Per committee, for its profile: the agencies it paid.
        by_filer = defaultdict(list)
        for r in rows:
            for fn, v in (paid.get(r['key'], {}).get('by') or {}).items():
                if v[0] >= 1000:
                    by_filer[fn].append({'k': r['key'], 'n': r['name'], 'usd': round(v[0]), 'cycle': round(v[1]),
                                         'fcc': 'fcc' in r})
        for v in by_filer.values():
            v.sort(key=lambda x: -x['usd'])
        out = {
            'generated': time.strftime('%Y-%m-%d'),
            'data_through': latest,
            'cycle_from': this_year - CYCLE_YEARS + 1,
            'documents_read': sum(1 for d in docs.values() if d.get('status') == 'read'),
            'caveats': [
                'An agency named in a political-file document placed that buy; what committees paid it in '
                'the state filings can include production and consulting as well as airtime. `media` is the '
                'part whose description says TV, television, broadcast, air time or a media buy.',
                'Federal campaigns report to the FEC, not the state, so an agency that buys only for federal '
                'candidates shows political-file orders and no state payments.',
                f'Agencies not named in a political-file document are listed only when committees paid them at '
                f'least ${HISTORY_MIN:,} for described media work, and never if they sell time themselves '
                f'(cable, satellite and station groups).',
            ],
            'agencies': rows,
            'by_filer': dict(sorted(by_filer.items())),
            'filers': {fn: [name(fn), party(fn)] for fn in sorted(by_filer)},
        }
        with open(args.out, 'w', encoding='utf-8') as fh:
            json.dump(out, fh, indent=1, ensure_ascii=False)
        named = [r for r in rows if r['found_by'] == 'political file']
        print(f'{len(rows)} agencies ({len(named)} named in political-file documents); '
              f'committees paid them ${sum(r.get("paid", {}).get("total", 0) for r in rows):,.0f} in all, '
              f'${sum(r.get("paid", {}).get("media", 0) for r in rows):,.0f} described as media')
        for r in rows[:15]:
            print(f'  {r["name"][:34]:<34} fcc ${r.get("fcc", {}).get("usd", 0):>11,}  '
                  f'paid this cycle ${r.get("paid", {}).get("cycle", 0):>11,}  media ${r.get("paid", {}).get("media", 0):>11,}')
        print(f'Wrote {args.out}')

    return add, finish


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cache', help='path to .la_cache (default: auto-find)')
    ap.add_argument('--out', default=D('agencies.json'))
    args = ap.parse_args()
    files = cache_files(find_cache(args.cache))
    add, finish = builder(args, files)
    scanned, latest = scan(files, [add])
    finish(scanned, latest)


if __name__ == '__main__':
    main()
