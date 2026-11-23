#!/usr/bin/env python3
"""
build_players_page.py — the outside groups: who they are and what they buy
================================================================================
Candidates are on the races page. This page is the money that isn't a
candidate's: the PACs, independent-expenditure committees and party and
caucus committees that spend the most in Louisiana's state elections. Each
gets a profile built from its own expenditure filings:

  * what it spent in each four-year cycle (2015, 2019, 2023, and 2027 so far),
    from la-campaign-finance's per-filer cycle totals;
  * where the money went, split three ways: to candidates and committees
    (contributions), to airtime (TV and radio stations and the media-buying
    agencies the political files name), and to everything else a campaign
    buys (consultants, mail, polling, staff);
  * the candidates it backed with the most money, in its latest active cycle;
  * the firms it hired (people paid as individuals are left out by name);
  * its TV and radio spending by cycle, from the same station matching as
    the TV and radio pages.

Which groups: every filer the Ethics Board registers as a PAC (or files as a
political committee) that spent at least $300,000 in the 2019 or 2023 cycle,
or $100,000 so far in 2027. Party is the filing's, with the shared corrections.

    python3 build_players_page.py

Reads the filings cache (fetch_cache.py). Writes players.html and
players.artifact.html. Stdlib only.
"""
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)
sys.path.insert(0, HERE)
sys.path.insert(0, D('fcc'))
from build_races_page import Finance  # noqa: E402
from filings import cache_files, cycle_of, find_cache, file_year, norm, party_of  # noqa: E402
from normalize import filer_index, match_filer  # noqa: E402
from page_shell import SITE, publish  # noqa: E402

URL = SITE + 'players.html'
DESCRIPTION = ("Louisiana's outside groups: the PACs, independent-expenditure and party committees "
               'spending in state elections, what they spent each cycle, who they backed, and who they hired.')
CYCLES = {2015: '2012-2015', 2019: '2016-2019', 2023: '2020-2023', 2027: '2024-2027'}
FIRST_YEAR = 2012
PARTYISH = re.compile(r'\b(party|caucus|democrats|republicans|democratic campaign committee|republican legislative|'
                      r'parish (democratic|republican) executive)\b', re.I)
CALL = re.compile(r'^[KW][A-Z]{2,3}\b(?:[ -]?(?:TV|AM|FM|LD|CD|DT|RADIO))?')
# Airtime and the firms that buy it: stations, cable and digital sellers, and
# media-buying firms (most carry MEDIA in the name; a few known buyers don't).
MEDIA_WORDS = re.compile(r'\b(AMPERSAND|NCC|COMCAST|SPECTRUM|COX (CABLE|MEDIA)|VIAMEDIA|IHEART|'
                         r'CUMULUS|TOWNSQUARE|BROADCASTING|TELEVISION|RADIO|DIRECTV|GOOGLE|FACEBOOK|META|'
                         r'MEDIA|PEOPLE WHO THINK|KATZ|SCREEN STRATEGIES|MENTZER|ABAR HUTTON)\b')
# Money to a committee or campaign that isn't a Louisiana filer: federal and
# out-of-state campaigns, party committees, PACs. A contribution, not a vendor.
POLITICAL = re.compile(r'\bPAC\b|POLITICAL ACTION|\bCAMPAIGN\b|COMMITTEE|\bFOR (GOVERNOR|SENATE|CONGRESS|'
                       r'LOUISIANA|JUDGE|MAYOR|SHERIFF|STATE|PRESIDENT|AMERICA)\b|\bTO ELECT\b|FRIENDS OF|'
                       r'\bNRSC\b|\bNRCC\b|\bDSCC\b|\bDCCC\b|\bRGA\b|\bDGA\b|TEXANS FOR|VICTORY FUND|'
                       r'\bPARTY\b|GOVERNORS ASSOCIATION|ACTION FUND|LEADERSHIP FUND|DELEGATION|'
                       r'NATIONAL (REPUBLICAN|DEMOCRATIC)|\bCAUCUS\b')
# Errands, not hires: kept out of the "hired" list (the dollars still count).
ERRAND = re.compile(r'\b(BANK|BANCORP|INTERNAL REVENUE|IRS|TREASURY|REVENUE|ETHICS|SECRETARY OF STATE|HOTEL|'
                    r'INN|HILTON|MARRIOTT|CASINO|RESORT|USPS|POSTMASTER|POSTAL|RESTAURANT|STEAK|CATER\w*|'
                    r'CLUB|AMERICAN EXPRESS|CREDIT|PAYPAL|STRIPE|ACTBLUE|WINRED|ANEDOT|VERIZON|AT&T|'
                    r'OFFICE DEPOT|AMAZON|HOST COMMITTEE|SUPER BOWL|CONFERENCE|ASSOCIATION|FOUNDATION)\b')
BUSINESS = re.compile(r'\b(LLC|INC|CORP|CO|GROUP|MEDIA|CONSULT\w*|STRATEG\w*|PRINT\w*|PRESS|SIGNS?|'
                      r'COMMUNICATIONS?|DIGITAL|RESEARCH|POLL\w*|ASSOCIATES|PARTNERS|PRODUCTIONS?|'
                      r'MARKETING|ADVERTISING|CREATIVE|AGENCY|FIRM|LAW|SERVICES?|SOLUTIONS|PAC|BANK|'
                      r'COMPANY|NETWORK|PUBLIC|AFFAIRS|DATA|MAIL|DESIGN|FUND|FOUNDATION|CPA|STUDIOS?)\b')


def load(path, default=None):
    if not os.path.exists(path):
        return default
    op = gzip.open if path.endswith('.gz') else open
    with op(path, 'rt', encoding='utf-8') as f:
        return json.load(f)


def looks_like_person(name):
    """A payee who is a private individual, not a firm: never listed by name."""
    n = norm(name)
    return bool(re.fullmatch(r'[A-Z]+( [A-Z]\.?)?( [A-Z]+){1,2}( (JR|SR|II|III|IV))?', n)) and not BUSINESS.search(n)


def select(fin):
    out = []
    for fn, e in fin.index.items():
        kind = fin.kind.get(fn)
        if kind not in ('PAC', 'OP9', 'PCC', 'PFD', 'OP0'):
            continue
        cy = e.get('cycles') or {}
        sp = {c: (cy.get(k) or {}).get('spent') or 0 for c, k in CYCLES.items()}
        if sp[2019] >= 300_000 or sp[2023] >= 300_000 or sp[2027] >= 100_000:
            out.append(fn)
    return out


def build():
    cache = find_cache()
    fin = Finance(cache)
    chosen = set(select(fin))
    tv, ra = load(D('data', 'committees_tv.json'), {}), load(D('data', 'committees_radio.json'), {})
    ag = load(D('data', 'agencies.json'), {})
    agencies = {norm(a['name']) for a in ag.get('agencies', [])}
    # Candidates and committees a group's money can go to: every state filer.
    idx = fin.idx_all

    spent = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))   # fn -> cycle -> bucket -> $
    backed = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # fn -> cycle -> filer -> $
    hired = defaultdict(lambda: defaultdict(Counter))                      # fn -> cycle -> payee -> $
    names, parties, latest = defaultdict(Counter), defaultdict(Counter), {}
    match_cache = {}
    for path in cache_files(cache):
        y = file_year(path)
        if y < FIRST_YEAR:
            continue
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                fn = (r.get('filerNumber') or '').strip()
                if fn not in chosen:
                    continue
                amt = float(r.get('amount') or 0)
                if amt <= 0:
                    continue
                cy = cycle_of(y)
                if r.get('candidate'):
                    names[fn][r['candidate']] += 1
                if r.get('party'):
                    parties[fn][r['party']] += 1
                latest[fn] = max(latest.get(fn, ''), r.get('date') or '')
                raw = (r.get('contributor') or '').strip()
                n = norm(raw)
                if not n:
                    spent[fn][cy]['other'] += amt
                    continue
                if n not in match_cache:
                    hit = match_filer([raw.title()], idx)
                    match_cache[n] = hit
                to = match_cache[n]
                if to and to != fn:
                    spent[fn][cy]['backed'] += amt
                    backed[fn][cy][to] += amt
                elif POLITICAL.search(n):
                    spent[fn][cy]['backed'] += amt
                elif CALL.match(n) or MEDIA_WORDS.search(n) or n in agencies:
                    spent[fn][cy]['media'] += amt
                    hired[fn][cy][raw.upper()] += amt
                else:
                    spent[fn][cy]['other'] += amt
                    if not looks_like_person(raw) and not ERRAND.search(n):
                        hired[fn][cy][raw.upper()] += amt

    def cand_party(f):
        for src in (tv, ra):
            if f in src and src[f].get('party'):
                return src[f]['party']
        return None

    groups = []
    for fn in chosen:
        e = fin.index[fn]
        cy = e.get('cycles') or {}
        name = names[fn].most_common(1)[0][0] if names[fn] else e['name']
        filed = parties[fn].most_common(1)[0][0] if parties[fn] else None
        party = party_of(filed, fn) or 'OTH'
        cycles = {}
        for c, k in CYCLES.items():
            tot = (cy.get(k) or {}).get('spent') or 0
            raised = (cy.get(k) or {}).get('raised') or 0
            if tot <= 0 and raised <= 0:
                continue
            b = spent[fn].get(c, {})
            cycles[c] = {'spent': round(tot), 'raised': round(raised),
                         'split': {k2: round(v) for k2, v in b.items()}}
        active = [c for c in cycles if cycles[c]['spent'] > 0]
        if not active:
            continue
        # The cycle a profile opens on: its biggest of the last two.
        # (or, when those are small beside its peak, the peak)
        peak = max(active, key=lambda c: cycles[c]['spent'])
        last = max((c for c in active if c >= 2023), key=lambda c: cycles[c]['spent'], default=peak)
        if cycles[last]['spent'] < 0.25 * cycles[peak]['spent']:
            last = peak
        # What kind of player: an air war (mostly airtime), a giver (mostly
        # contributions), or a party or caucus committee, judged on its
        # biggest recent cycle's split.
        sp = cycles[max(active, key=lambda c: (c >= 2019, cycles[c]['spent']))]['split']
        tot = sum(sp.values()) or 1
        kind = ('party' if PARTYISH.search(e['name']) else
                'air' if sp.get('media', 0) / tot >= 0.4 else
                'giver' if sp.get('backed', 0) / tot >= 0.5 else 'ops')
        per = {}
        for c in CYCLES:
            if c not in cycles:
                continue
            per[c] = {'backed': [[fin.index[t]['name'], cand_party(t) or 'OTH', round(a), t]
                                 for t, a in sorted(backed[fn].get(c, {}).items(), key=lambda x: -x[1])[:8]],
                      'hired': [[h.title(), round(a)] for h, a in hired[fn].get(c, Counter()).most_common(6)]}
        air = {}
        for key, src in (('tv', tv), ('ra', ra)):
            yrs = (src.get(fn) or {}).get('years') or {}
            for yy, v in yrs.items():
                c = cycle_of(int(yy))
                if c in CYCLES:
                    air.setdefault(c, {}).setdefault(key, 0)
                    air[c][key] += v
        groups.append({
            'f': fn, 'n': name, 'p': party if party in ('DEM', 'REP', 'IND') else 'OTH',
            'kind': kind, 'cycles': cycles, 'last': last, 'latest': latest.get(fn, ''),
            'air': {c: {k: round(v) for k, v in a.items()} for c, a in air.items()},
            'per': per,
        })
    groups.sort(key=lambda g: -max(g['cycles'].get(c, {}).get('spent', 0) for c in (2019, 2023, 2027)))
    return {'groups': groups, 'cycles': sorted(CYCLES)}


def main():
    spend = load(D('data', 'station_spend.json'))
    data = build()
    blob = 'const DATA = ' + json.dumps(data, separators=(',', ':'), ensure_ascii=False) + ';'
    for name in publish(D('players.template.html'), blob, spend, 'players', D('players.html'),
                        D('players.artifact.html'), DESCRIPTION, URL,
                        title='Louisiana Airwaves — Outside groups'):
        print(f'  {os.path.basename(name)}  {os.path.getsize(name):,} bytes')
    print(f"  {len(data['groups'])} groups")


if __name__ == '__main__':
    main()
