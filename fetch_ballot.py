#!/usr/bin/env python3
"""
fetch_ballot.py — the races and candidates on Louisiana's coming ballots
================================================================================
Reads the Secretary of State's election-results portal, which lists every
race on a ballot once qualifying closes and fills in the votes on election
night, for each election from a few weeks ago onward. Writes
data/ballot.json:

    {"fetched": "...", "elections": [{"date": "2026-11-03", "races": [
        {"id": "...", "office": "East Baton Rouge Parish Member of School Board -- District 7",
         "parish": "East Baton Rouge" | null, "elect": 1,
         "candidates": [{"name": "...", "party": "REP", "votes": 0, "outcome": ""}]}]}]}

    python3 fetch_ballot.py

voterportal.sos.la.gov is not reachable from every network; the nightly
workflow runs this on GitHub's runners. The race titles follow
la-campaign-finance's build_election_results.py: a single-parish race whose
title omits its parish ("Sheriff") gets the parish written in, so the 64
parishes' sheriffs stay 64 races. Stdlib only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, 'data', *p)
SOS = 'https://voterportal.sos.la.gov/ElectionResults/ElectionResults/Data?blob='

# Elections already scheduled by law, tried even when the portal's date list
# doesn't carry them yet.
SCHEDULED = ['2026-11-03', '2026-12-12', '2027-10-09', '2027-11-20']
# Keep an election this long after its date, for results and the runoff ahead.
KEEP_AFTER = timedelta(days=45)

# Numbered alphabetically, 01-64; the portal's per-parish files key off it.
PARISHES = [
    'Acadia', 'Allen', 'Ascension', 'Assumption', 'Avoyelles', 'Beauregard', 'Bienville',
    'Bossier', 'Caddo', 'Calcasieu', 'Caldwell', 'Cameron', 'Catahoula', 'Claiborne',
    'Concordia', 'De Soto', 'East Baton Rouge', 'East Carroll', 'East Feliciana',
    'Evangeline', 'Franklin', 'Grant', 'Iberia', 'Iberville', 'Jackson', 'Jefferson',
    'Jefferson Davis', 'Lafayette', 'Lafourche', 'La Salle', 'Lincoln', 'Livingston',
    'Madison', 'Morehouse', 'Natchitoches', 'Orleans', 'Ouachita', 'Plaquemines',
    'Pointe Coupee', 'Rapides', 'Red River', 'Richland', 'Sabine', 'St. Bernard',
    'St. Charles', 'St. Helena', 'St. James', 'St. John the Baptist', 'St. Landry',
    'St. Martin', 'St. Mary', 'St. Tammany', 'Tangipahoa', 'Tensas', 'Terrebonne', 'Union',
    'Vermilion', 'Vernon', 'Washington', 'Webster', 'West Baton Rouge', 'West Carroll',
    'West Feliciana', 'Winn',
]
PARTY = {'DEM': 'DEM', 'REP': 'REP', 'D': 'DEM', 'R': 'REP', 'LBT': 'LBT', 'GRN': 'GRN',
         'IND': 'IND', 'NOPTY': 'IND', 'OTHER': 'OTH'}


def fetch(blob, timeout=30):
    req = urllib.request.Request(SOS + blob, headers={'User-Agent': 'louisiana-airwaves/1.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode('utf-8', 'replace').strip()
            return json.loads(body) if body.startswith('{') else None
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            err = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            err = e
        time.sleep(1 + attempt * 2)
    print(f'  giving up on {blob}: {err}')
    return None


def as_list(x):
    return [] if x is None else x if isinstance(x, list) else [x]


def party_office(office):
    o = office.upper()
    return bool(re.search(r'\b(DSCC|RSCC|DPEC|RPEC)\b', o) or 'COMMITTEE' in o)


def local_office(office):
    """A parish or municipal office whose title doesn't name its parish."""
    o = office.upper()
    if any(k in o for k in ('BESE', 'PUBLIC SERVICE', 'ELEMENTARY', 'CONGRESS', 'U. S.',
                            'STATE SENATOR', 'STATE REPRESENTATIVE', 'JUSTICE --', 'COURT OF APPEAL',
                            'JUDICIAL DISTRICT', 'DISTRICT COURT', 'DISTRICT ATTORNEY', 'GOVERNOR',
                            'SECRETARY OF STATE', 'ATTORNEY GENERAL', 'TREASURER', 'COMMISSIONER OF')):
        return False
    return not any(k in o for k in ('CITY OF', 'TOWN OF', 'VILLAGE OF', 'PARISH OF'))


def qualify(office, parish):
    if office.upper().startswith('PARISH '):
        return f'{parish} {office}'
    return f'{parish} Parish {office}'


def parse_choice(desc):
    """'John "Johnny" Doe (REP)' -> ('John Johnny Doe', 'REP'); a proposition's
    choices (Yes/No) have no party and come back with None."""
    m = re.match(r'^(.*)\s+\(([A-Za-z]+)\)$', desc.strip())
    if not m:
        return desc.strip(), None
    return ' '.join(re.sub(r'"([^"]+)"', r'\1', m.group(1)).split()), PARTY.get(m.group(2).upper(), 'OTH')


def races(cands, votes, parish=None):
    """The races in one RacesCandidates file, with votes when there are any."""
    tally = {}
    for vr in as_list(((votes or {}).get('Races') or {}).get('Race')):
        for vc in as_list(vr.get('Choice')):
            tally[(vr.get('ID'), vc.get('ID'))] = (int(vc.get('VoteTotal') or 0), vc.get('Outcome') or '')
    out = []
    for r in as_list(((cands or {}).get('Races') or {}).get('Race')):
        office = ' '.join((r.get('SpecificTitle') or r.get('GeneralTitle') or '').split())
        if not office or party_office(office):
            continue
        if parish and local_office(office):
            office = qualify(office, parish)
        people, measure = [], False
        for ch in as_list(r.get('Choice')):
            name, party = parse_choice(ch.get('Desc') or '')
            if party is None:
                measure = True
            v, outcome = tally.get((r.get('ID'), ch.get('ID')), (0, ''))
            people.append({'name': name, 'party': party, 'votes': v, 'outcome': outcome})
        if measure:     # propositions and amendments: not candidates
            continue
        out.append({'id': f"{parish or 'mp'}:{r.get('ID')}", 'office': office, 'parish': parish,
                    'elect': int(r.get('NumberToElect') or 1), 'candidates': people})
    return out


def election(day):
    """Every race on one election's ballot, or None if the portal has nothing."""
    blob = day.strftime('%Y%m%d')
    found = []
    mp = fetch(f'{blob}/RacesCandidates_Multiparish.htm')
    if mp is not None:
        found += races(mp, fetch(f'{blob}/Votes_Multiparish.htm'))
    pe = fetch(f'{blob}/ParishesInElection.htm')
    pids = [str(p.get('ParishValue')).zfill(2) for p in
            as_list(((pe or {}).get('ParishesInElection') or {}).get('Parish'))]
    for pid in pids:
        parish = PARISHES[int(pid) - 1] if pid.isdigit() and 0 < int(pid) <= 64 else None
        found += races(fetch(f'{blob}/RacesCandidates/ByParish_{pid}.htm'),
                       fetch(f'{blob}/VotesParish/Votes_{pid}.htm'), parish)
        time.sleep(0.1)
    if mp is None and not pids:
        return None
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=D('ballot.json'))
    ap.add_argument('--today', help='YYYY-MM-DD (default: today, UTC)')
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()

    listed = fetch('ElectionDates.htm')
    if listed is None:
        sys.exit('The Secretary of State portal did not answer.')
    days = {datetime.strptime(d['ElectionDate'], '%m/%d/%Y').date()
            for d in as_list((listed.get('Dates') or {}).get('Date'))}
    print(f'Portal lists {len(days)} elections; latest {sorted(days)[-3:]}')
    days |= {date.fromisoformat(d) for d in SCHEDULED}
    want = sorted(d for d in days if d >= today - KEEP_AFTER)

    try:
        with open(args.out, encoding='utf-8') as f:
            old = {e['date']: e for e in json.load(f).get('elections', [])}
    except (OSError, ValueError):
        old = {}
    out = []
    for day in want:
        found = election(day)
        if found is None:
            print(f'  {day}: no ballot posted yet')
            if day.isoformat() in old:          # keep what we had rather than drop it
                out.append(old[day.isoformat()])
            elif day > today:
                out.append({'date': day.isoformat(), 'posted': False, 'races': []})
            continue
        print(f'  {day}: {len(found)} races, {sum(len(r["candidates"]) for r in found)} candidates')
        out.append({'date': day.isoformat(), 'posted': True, 'races': found})

    doc = {'fetched': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'source': 'Louisiana Secretary of State, voterportal.sos.la.gov election results',
           'elections': out}
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=0, ensure_ascii=False)
    print(f'Wrote {os.path.relpath(args.out, HERE)}')


if __name__ == '__main__':
    main()
