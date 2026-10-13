#!/usr/bin/env python3
"""
build_races_page.py — every race on Louisiana's coming ballots, with its money
================================================================================
One card per race on each coming election's ballot (data/ballot.json, from
the Secretary of State), one row per candidate, joining what the other pages
and the campaign-finance dashboard know about them:

  * raised and spent this four-year cycle, from the state finance reports
    (la-campaign-finance's per-filer totals);
  * certified cash on hand from the candidate's latest annual report;
  * for federal candidates, raised, spent and cash on hand from the FEC's
    bulk summary of House and Senate campaigns (fetch_fec.py, data/fec.json);
  * what they've paid TV and radio stations this cycle (committees_tv.json,
    committees_radio.json);
  * what the FCC political files of the TV stations, cable systems and radio
    stations show them booking: documents by week, flights booked ahead (from
    the documents' names), and what was posted in the last few days;
  * how often the money leader has won this kind of race since 2000 (the
    "does money win?" page).

Before an election's ballot is posted (2027's, until qualifying closes in
summer 2027) its card list comes from the offices last contested four years
earlier, each with its incumbent's money so far this cycle, plus the
committees raising money this cycle that aren't tied to a race yet.

    python3 build_races_page.py

Candidates are matched to state filers by name, only when exactly one filer
matches. Federal candidates report to the FEC, not the state; they are
matched to the FEC's campaigns for the same seat (see Fec), and carry no
station payments, since federal campaigns pay media buyers rather than
stations. Inputs from la-campaign-finance
are read from the filings cache (fetch_cache.py); without them the page
still builds, without the finance columns. Writes races.html (standalone)
and races.artifact.html (body fragment), and data/filer_races.json (filer ->
the coming race it's on a ballot for), which the committee profiles link
from. Stdlib only.
"""
import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)
sys.path.insert(0, HERE)
sys.path.insert(0, D('fcc'))
from filings import find_cache  # noqa: E402
from markets import BY_NAME, BY_TOPO, MARKETS  # noqa: E402
from normalize import buyer_key, filer_index, match_filer, person_keys  # noqa: E402
from page_shell import SITE, publish  # noqa: E402
from prose import words  # noqa: E402
from summary import fcc_summary  # noqa: E402

URL = SITE + 'races.html'
DESCRIPTION = ("Every race on Louisiana's coming ballots — candidates, money raised, cash on hand, "
               'TV and radio bought, and the ad orders stations posted this week.')
CYCLE = '2024-2027'
RECENT = 2011   # "last ran for": older races are too likely a namesake's
# Not a person: committees whose names say so, for the "not in a race yet" list.
ORG = re.compile(r'\b(pac|fund|committee|association|assn|council|party|federation|alliance|coalition|'
                 r'inc|llc|forward|citizens|people|project|action|league|union|network|caucus|victory|'
                 r'conservative|progressive|democrats?|republicans?|leadership|majority|future|louisiana)\b', re.I)


def load(path, default=None):
    try:
        if path.endswith('.gz'):
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                return json.load(f)
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        if default is None:
            raise
        print(f'  {os.path.basename(path)}: not available; going without it')
        return default


def sos_name(name):
    """A name as la-campaign-finance keys the Secretary of State's candidacy
    history: capitals, no titles or suffixes, letters only."""
    n = re.sub(r'\b(DR|MR|MRS|MS|JR|SR|II|III|IV|ESQ|PHD|MD)\.?\b', '', name.upper())
    return ' '.join(re.sub(r'[^A-Z\s]', ' ', n).split())


def tier(office):
    """The "does money win?" page's office tiers (la-campaign-finance
    build_money_wins.tier_of over build_election_results.office_rank)."""
    o = office.upper()
    if re.search(r'\bU\.?\s?S\.?\s|CONGRESS', o):
        return 'Federal'
    if (('GOVERNOR' in o) or any(x in o for x in ('ATTORNEY GENERAL', 'SECRETARY OF STATE', 'TREASURER',
                                                   'INSURANCE COMMISSIONER', 'AGRICULTURE', 'COMMISSIONER OF'))) \
            and 'PARISH' not in o and 'CITY' not in o:
        return 'Statewide'
    if 'STATE SENATOR' in o or 'STATE REPRESENTATIVE' in o:
        return 'Legislative'
    if any(x in o for x in ('MAYOR', 'SHERIFF', 'DISTRICT ATTORNEY', 'PARISH PRESIDENT', 'ASSESSOR',
                            'CLERK OF COURT', 'CORONER')):
        return 'Local'
    if 'JUSTICE' in o and 'PEACE' not in o or 'JUDGE' in o:
        return 'Judicial'
    return 'Local'


def advantage_bucket(ratio):
    return '<2x' if ratio < 2 else '2-5x' if ratio < 5 else '5-10x' if ratio < 10 else '>10x'


class Finance:
    """What la-campaign-finance knows about a state filer."""

    def __init__(self, cache):
        c = lambda n: os.path.join(cache, n) if cache else '/nonexistent/' + n
        self.index = load(c('la_filer_index.json.gz'), {})
        lookup = load(c('la_filer_lookup.json'), {})
        coh = load(c('ethics_coh_cache.json'), {})
        self.wins = load(c('la_money_wins.json'), {})
        self.history = load(c('la_candidacies_raw.json.gz'), {})
        # Match against filers active this cycle first, then any.
        active = {f: {'n': e['name']} for f, e in self.index.items() if e.get('last_cycle') == CYCLE}
        self.idx_active = filer_index(active)
        self.idx_all = filer_index({f: {'n': e['name']} for f, e in self.index.items()})
        # Certified cash on hand is keyed by the name the Ethics Board files
        # under; the lookup ties names to filer numbers.
        # The history's names by first + last name, for spellings that add a
        # middle or maiden name ("Blair Downing Edwards").
        self.by_key = defaultdict(set)
        for n in self.history:
            for k in person_keys(n.title()):
                self.by_key[k].add(n)
        self.coh, self.kind = {}, {}
        for name, fn in lookup.items():
            # The Ethics Board's own id says what kind of filer it is:
            # CAN... a candidate, PAC... a committee.
            if (coh.get(name) or {}).get('filer_id'):
                self.kind[fn] = coh[name]['filer_id'][:3]
            reps = [r for r in (coh.get(name) or {}).get('reports', []) if r.get('ending_coh') is not None]
            if reps:
                r = max(reps, key=lambda r: (r.get('report_year') or 0, r.get('report_id') or 0))
                prev = self.coh.get(fn)
                if not prev or r['report_year'] > prev[1]:
                    self.coh[fn] = [round(r['ending_coh']), r['report_year']]

    def match(self, name):
        fn = match_filer([name], self.idx_active) or match_filer([name], self.idx_all)
        return fn if fn and not self.different_people(name, self.index[fn]['name']) else None

    def offices(self, name):
        return {' '.join(x['office'].split()) for x in self.history.get(sos_name(name), [])
                if not x.get('party_office')}

    def different_people(self, a, b):
        """Two names the matcher joined that the Secretary of State's history
        keeps apart: each has run for office under its own spelling, and never
        for the same one ("Edward James", Maringouin alderman, is not
        "Edward Ted James", state representative)."""
        if sos_name(a) == sos_name(b):
            return False
        oa, ob = self.offices(a), self.offices(b)
        return bool(oa and ob and not oa & ob)

    def last_run(self, name):
        """[office, year, outcome] of the most recent race this name ran in."""
        xs = [x for x in self.history.get(sos_name(name), [])
              if not x.get('party_office') and int(x['date'][-4:]) >= RECENT]
        if not xs:
            return None
        x = max(xs, key=lambda x: (x['date'][-4:], x['date'][:5]))
        return [' '.join(x['office'].split()), int(x['date'][-4:]), x['outcome']]

    def ran_since(self, name, year):
        """Whether any spelling of this name has been on a ballot since `year`."""
        names = {sos_name(name)} | {n for k in person_keys(name) for n in self.by_key.get(k, ())}
        return any(int(x['date'][-4:]) >= year and not x.get('party_office')
                   for n in names for x in self.history.get(n, []))

    def money(self, fn):
        e = self.index.get(fn) or {}
        cy = (e.get('cycles') or {}).get(CYCLE) or {}
        out = {}
        if cy:
            out['r'], out['s'] = round(cy.get('raised') or 0), round(cy.get('spent') or 0)
            if cy.get('borrowed'):
                out['b'] = round(cy['borrowed'])
            # Raised in the last 60 days of monthly totals, for momentum.
            mo = e.get('monthly') or {}
            last = sorted(mo)[-2:] if mo else []
            out['m'] = [[k, round(mo[k].get('in') or 0), round(mo[k].get('out') or 0)] for k in last]
        if fn in self.coh:
            out['coh'] = self.coh[fn]
        return out


def fec_seat(office):
    """('S', '00') or ('H', '04') for a federal race title; None otherwise."""
    if re.search(r'U\.?\s?S\.?\s+Senat', office, re.I):
        return 'S', '00'
    m = re.search(r'(\d+)(?:st|nd|rd|th)\s+Congressional District', office, re.I)
    return ('H', m.group(1).zfill(2)) if m else None


def fec_person(name):
    """'CARTER, TROY A. SR.' as 'Troy A. Carter', the order ballots use."""
    last, _, given = name.partition(',')
    given = re.sub(r'\b(MR|MRS|MS|DR|HON|JR|SR|II|III|IV)\b\.?', ' ', given.upper())
    return ' '.join(f'{given} {last}'.split()).title()


class Fec:
    """The FEC's House and Senate campaigns, by seat, for matching federal
    candidates. A ballot name matches a campaign for the same seat on its
    full name or first + last name, else on a surname only one campaign for
    the seat has, so long as the given names share an initial: "Clay
    Higgins" is "HIGGINS, GLEN CLAY" and "Jamie Davis" can be "DAVIS,
    JAMES", but a "Davis" doesn't make Jamie Davis a Larry Davis, and two
    Davises for one seat match neither."""

    def __init__(self, data):
        self.cycle = (data or {}).get('cycle')
        self.seats = defaultdict(list)
        for c in (data or {}).get('candidates', []):
            self.seats[(c['office'], c['district'])].append(c)

    @staticmethod
    def words(name):
        return [x for x in buyer_key(name, alias=False).split() if x not in ('jr', 'sr', 'ii', 'iii', 'iv')]

    def match(self, name, office):
        pool = self.seats.get(fec_seat(office) or (), [])
        keys = person_keys(name)
        hits = [c for c in pool if keys & person_keys(fec_person(c['name']))]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return None
        w = self.words(name)
        if len(w) < 2:
            return None
        same = [c for c in pool if self.words(fec_person(c['name']))[-1:] == w[-1:]]
        if len(same) != 1:
            return None
        initials = lambda ws: {x[0] for x in ws}
        given = initials(self.words(fec_person(same[0]['name']))[:-1])
        return same[0] if initials(w[:-1]) & given else None

    def money(self, c):
        out = {'r': c['r'], 's': c['s'], 'fec': [c['id'], self.cycle]}
        if c.get('through'):
            out['coh'] = [c['coh'], c['through']]
        if c.get('loans'):
            out['b'] = c['loans']
        return out


def airtime(fn, tv, ra):
    """This cycle's TV and radio payments from the state filings."""
    yrs = lambda c: sum(v for y, v in (c.get('years') or {}).items() if '2024' <= y <= '2027')
    t, r = tv.get(fn) or {}, ra.get(fn) or {}
    return round(yrs(t)), round(yrs(r))


def fcc_index(F):
    """Political-file buyers by filer and by person key, for matching
    candidates. A key two buyers share matches neither."""
    by_f, by_k = {}, defaultdict(list)
    for x in (F or {}).get('all', []):
        if x['b'] == 'Issue':
            continue
        if x['f']:
            by_f[x['f']] = x
        for k in person_keys(x['name']):
            by_k[k].append(x)
    return by_f, by_k


def fcc_row(x):
    return {'bn': x['name'], 'docs': x['docs'], 'recent': x['recent'], 'latest': x['latest'],
            'st': [[s['c'], s['u'], s['c'] in x['stRecent'], s['k'], s['m']] for s in x['st']],
            'fresh': len(x['fresh']), 'wk': x['wk'], 'revs': x['revs'], 'aired': x['aired'],
            **({'onAir': x['onAir']} if 'onAir' in x else {})}


def candidate(c, fed, fin, tv, ra, pf, used, fec=None, office=''):
    """One candidate's row: who they are and their money and airtime."""
    row = {'n': c['name'], 'p': c['party'] or 'OTH'}
    if c.get('votes') or c.get('outcome'):
        row['v'], row['w'] = c.get('votes') or 0, c.get('outcome') or ''
    if fed and fec and (x := fec.match(c['name'], office)):
        row.update(fec.money(x))
    fn = None if fed else fin.match(c['name'])
    if fn:
        row['f'] = fn
        row.update(fin.money(fn))
        row['tv'], row['ra'] = airtime(fn, tv, ra)
    by_f, by_k = pf
    x = by_f.get(fn) if fn else None
    if not x:
        # The buyer filed under this exact name, else the one buyer any of the
        # name's forms points to ("John Paul Young" is not "John Young").
        same = lambda b: (b['b'] == 'Federal') == fed
        exact = [b for b in by_k.get(buyer_key(c['name']), []) if same(b) and buyer_key(b['name']) == buyer_key(c['name'])]
        hits = {id(b): b for k in person_keys(c['name']) for b in by_k.get(k, []) if same(b)}
        x = exact[0] if len(exact) == 1 else next(iter(hits.values())) if len(hits) == 1 else None
    if x and id(x) not in used:
        used.add(id(x))
        row['pf'] = fcc_row(x)
    return row


def race_markets(race, rows):
    """TV markets a race is in: its parish's, or for a multi-parish race the
    markets of the stations its candidates book."""
    if race.get('parish'):
        return [BY_TOPO[PARISH_DMA[race['parish']]]]
    ks = {s[3] for r in rows if 'pf' in r for s in r['pf']['st'] if s[3]}
    return sorted(ks, key=list(MARKETS).index)


PARISH_DMA = json.load(open(D('data', 'parish_dma.json'), encoding='utf-8'))


def advantage(rows, wins):
    """The spending leader's edge over the runner-up, and how often a leader
    with that edge has won since 2000."""
    spent = sorted((r.get('s') or 0 for r in rows), reverse=True)
    if len(spent) < 2 or spent[1] <= 0:
        return None
    b = advantage_bucket(spent[0] / spent[1])
    hist = next((x for x in wins.get('by_advantage', []) if x['bucket'] == b), None)
    return {'x': round(spent[0] / spent[1], 1), 'b': b, **({'rate': hist['rate'], 'n': hist['n']} if hist else {})}


def ballot_races(election, fin, tv, ra, pf, used, fec=None):
    out = []
    for r in election['races']:
        t = tier(r['office'])
        rows = [candidate(c, t == 'Federal', fin, tv, ra, pf, used, fec, r['office']) for c in r['candidates']]
        out.append({'id': r['id'], 'o': r['office'], 'pa': r.get('parish'), 't': t,
                    'k': race_markets(r, rows), 'el': r.get('elect', 1), 'c': rows,
                    **({'adv': a} if (a := advantage(rows, fin.wins)) else {})})
    return out


def scaffold(day, fin, tv, ra, pf, used, taken):
    """Before qualifying: the offices last contested four years before `day`,
    each with its winner then, and the committees raising money this cycle
    that aren't tied to any race yet."""
    lo, hi = date(day.year - 4, 9, 1), date(day.year - 4, 12, 31)
    winners = defaultdict(list)
    for norm, cs in fin.history.items():
        for x in cs:
            m, d, y = x['date'].split('/')
            when = date(int(y), int(m), int(d))
            if lo <= when <= hi and x['outcome'] == 'Elected' and not x.get('party_office'):
                winners[' '.join(x['office'].split())].append((norm, x))
    races = []
    for office, ws in sorted(winners.items()):
        t = tier(office)
        if t == 'Federal':
            continue
        rows = []
        for norm, x in ws:
            row = candidate({'name': norm.title(), 'party': x['party']}, False, fin, tv, ra, pf, used)
            row['inc'] = True
            if row.get('f'):
                taken.add(row['f'])
            rows.append(row)
        parish = next((p for p in PARISH_DMA if office.startswith(p + ' Parish') or office.startswith(p + ' ')), None)
        races.append({'id': 'inc:' + office, 'o': office, 'pa': parish, 't': t,
                      'k': race_markets({'parish': parish}, rows), 'el': len(rows), 'c': rows})
    # Raising this cycle, not in any race above, on a posted ballot, or on a
    # ballot since the last cycle's: likely entrants. People only; PACs and
    # party committees are left out.
    loose = []
    for fn, e in fin.index.items():
        cy = (e.get('cycles') or {}).get(CYCLE) or {}
        person = fin.kind.get(fn) == 'CAN' or (fn not in fin.kind and not ORG.search(e['name']))
        if fn in taken or not cy.get('raised') or not person or fin.ran_since(e['name'], day.year - 3):
            continue
        loose.append((cy['raised'], fn))
    field = []
    for _, fn in sorted(loose, reverse=True)[:60]:
        row = {'n': fin.index[fn]['name'], 'p': 'OTH', 'f': fn, **fin.money(fn)}
        if (last := fin.last_run(row['n'])):
            row['last'] = last
        row['tv'], row['ra'] = airtime(fn, tv, ra)
        x = pf[0].get(fn)
        if x and id(x) not in used:
            used.add(id(x))
            row['pf'] = fcc_row(x)
        field.append(row)
    return races, field


ORDINAL = {1: '1st', 2: '2nd', 3: '3rd'}
EXPLICIT = [(re.compile(r'\bLA[\s_-]*CD[\s_-]*0?(\d)\b', re.I),
             lambda m: f"U. S. Representative -- {ORDINAL.get(int(m.group(1)), m.group(1) + 'th')} Congressional District"),
            (re.compile(r'\b(?:LA[\s_-]*)?U\.?\s?S\.?\s*Sen(?:ate)?\b', re.I), lambda m: 'U. S. Senator')]


def outside_groups(F, election):
    """Issue groups' airtime tied to the races it's about, read from their
    document names: a district written in ("LA CD6", DirecTV's habit), or the
    surname of a candidate in the race who is buying airtime too ("Creep
    Scalise", "Liberal Letlow": stations name the creative). A surname counts
    only when one such candidate on the ballot has it, so a plain word
    ("Page") or a namesake can't tie a group to the wrong race."""
    if not F or not election.get('posted'):
        return
    by_office = {}
    for r in election['races']:
        by_office.setdefault(r['o'], r)
    sur = defaultdict(set)
    for r in election['races']:
        for c in r['c']:
            if c.get('pf') or c.get('tv') or c.get('ra'):
                w = [x for x in re.sub(r"[^A-Za-z' ]", ' ', c['n']).split()
                     if x.lower() not in ('jr', 'sr', 'ii', 'iii', 'iv')]
                if w and len(w[-1]) > 3:
                    sur[w[-1].lower()].add((r['id'], c['n']))
    sur = {s: next(iter(v)) for s, v in sur.items() if len(v) == 1}
    races = {r['id']: r for r in election['races']}
    for x in F.get('all', []):
        if x['b'] != 'Issue' or not x.get('docnames'):
            continue
        cues = {}
        for name in x['docnames']:
            for pat, office in EXPLICIT:
                m = pat.search(name)
                if m and office(m) in by_office:
                    cues.setdefault(by_office[office(m)]['id'], f'filed for {m.group(0).strip()}')
            for w in set(re.findall(r"[a-z']+", name.lower())):
                if w in sur:
                    rid, cand = sur[w]
                    cues.setdefault(rid, f'names {cand.split()[-1]} in its ad titles')
        for rid, cue in cues.items():
            name = x['name'].title() if x['name'].islower() else x['name']
            races[rid].setdefault('out', []).append(dict(fcc_row(x), n=name, cue=cue))
    for r in election['races']:
        if 'out' in r:
            r['out'].sort(key=lambda g: (-g['recent'], -g['docs'], g['n']))


def feed(F, elections):
    """Political-file documents posted in the last few days, newest first,
    each tied to the race its buyer is running in, where there is one."""
    where = {c['pf']['bn']: [e['d'], r['id']] for e in elections for r in e['races']
             for c in r['c'] if 'pf' in c}
    out = []
    for x in (F or {}).get('all', []):
        for up, call, kind in x['fresh']:
            out.append({'d': up, 'c': call, 'kind': kind, 'n': x['name'], 'b': x['b'],
                        **({'r': where[x['name']]} if x['name'] in where else {})})
    out.sort(key=lambda r: (r['d'], r['n'], r['c']), reverse=True)
    return out


def build(today=None):
    today = today or date.today()
    spend = load(D('data', 'station_spend.json'))
    ballot = load(D('data', 'ballot.json'), {'elections': []})
    market = {s['call']: BY_NAME[s['dma']] for s in load(D('data', 'stations.json'))}
    F = fcc_summary(market, full=True, media=('tv', 'cable', 'radio', 'dbs'))
    fin = Finance(find_cache())
    fec = Fec(load(D('data', 'fec.json'), {}))
    tv, ra = load(D('data', 'committees_tv.json')), load(D('data', 'committees_radio.json'))
    pf = fcc_index(F)
    party = {}
    for src in (tv, ra):
        for fn, c in src.items():
            party.setdefault(fn, c.get('party'))

    used, taken, elections = set(), set(), []
    for e in ballot['elections']:
        day = date.fromisoformat(e['date'])
        if e.get('posted'):
            races = ballot_races(e, fin, tv, ra, pf, used, fec)
            for r in races:
                taken |= {c['f'] for c in r['c'] if c.get('f')}
            elections.append({'d': e['date'], 'posted': True, 'races': races})
        else:
            elections.append({'d': e['date'], 'posted': False, 'races': []})
    # The first coming election with no ballot yet and a regular cycle four
    # years back gets the offices-up-for-election scaffold: in 2026-27, the
    # October 2027 statewide, legislative and parish elections.
    for e in elections:
        day = date.fromisoformat(e['d'])
        if not e['posted'] and day > today and day.month == 10 and day.year % 4 == 3:
            e['races'], e['field'] = scaffold(day, fin, tv, ra, pf, used, taken)
            e['scaffold'] = True
            break
    for e in elections:
        for r in e['races']:
            for c in r['c'] + e.get('field', []):
                if c.get('p') == 'OTH' and c.get('f') and party.get(c['f']):
                    c['p'] = party[c['f']]
    for e in elections:
        outside_groups(F, e)
    wins = fin.wins
    data = {
        'elections': elections,
        'feed': feed(F, elections),
        'fcc': {'scraped': F['scraped'], 'freshSince': F['freshSince'], 'days': F['days'],
                'media': F['media'], 'weeks': F['weeks']} if F else None,
        'wins': {'tier': {x['tier']: [x['rate'], x['n']] for x in wins.get('by_tier', [])},
                 'all': [wins['overall']['rate'], wins['overall']['n_races']] if wins.get('overall') else None,
                 'span': wins.get('span')} if wins else None,
        'fetched': ballot.get('fetched'),
        'fecThrough': max((c['through'] or '' for c in sum(fec.seats.values(), [])), default='') or None,
        'today': today.isoformat(),
    }
    return data, spend


def facts(data):
    posted = [e for e in data['elections'] if e['posted'] and e['d'] >= data['today']]
    nxt = posted[0] if posted else None
    cycle = CYCLE.replace('-', '–')
    if not nxt:
        return {'lede': 'No ballot is posted for a coming election yet.', 'cycle': cycle}
    rs = nxt['races']
    nc = sum(len(r['c']) for r in rs)
    money = sum(1 for r in rs for c in r['c'] if c.get('r'))
    ads = sum(1 for r in rs for c in r['c'] if c.get('pf') or c.get('tv') or c.get('ra'))
    when = date.fromisoformat(nxt['d']).strftime('%B %-d')
    return {'lede': f'<b>{len(rs):,} contested races</b> and <b>{nc:,} candidates</b> are on the {when} ballot. '
                    f'{money:,} of the candidates have reported raising money this cycle, and {words(ads)} '
                    f'have bought or booked TV or radio time.', 'cycle': cycle}


def filer_races(data):
    """filer -> [election date, race id, office] for every matched candidate
    on a posted ballot that hasn't happened yet."""
    out = {}
    for e in data['elections']:
        if e['posted'] and e['d'] >= data['today']:
            for r in e['races']:
                for c in r['c']:
                    if c.get('f'):
                        out.setdefault(c['f'], [e['d'], r['id'], r['o']])
    return out


def main():
    data, spend = build()
    with open(D('data', 'filer_races.json'), 'w', encoding='utf-8') as f:
        f.write('{\n' + ',\n'.join(f'{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}'
                                    for k, v in sorted(filer_races(data).items())) + '\n}\n')
    # Names come from outside sources; '</' can't be allowed to close the script.
    blob = 'const DATA = ' + json.dumps(data, separators=(',', ':'), ensure_ascii=False).replace('</', '<\\/') + ';'
    for name in publish(D('races.template.html'), blob, spend, 'races', D('races.html'),
                        D('races.artifact.html'), DESCRIPTION, URL,
                        title='Louisiana Airwaves — Races', icon='&#128499;', facts=facts(data)):
        print(f'  {os.path.basename(name)}  {os.path.getsize(name):,} bytes')


if __name__ == '__main__':
    main()
