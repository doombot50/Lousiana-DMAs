#!/usr/bin/env python3
"""
fetch_fec.py — what Louisiana's federal candidates have raised and spent
================================================================================
Federal candidates report to the FEC, not the state, so the state finance
reports behind the races page never see them. The FEC publishes a summary
row per House and Senate campaign in its bulk "current campaigns" file
(webl<yy>.zip, refreshed daily, no API key), and this keeps Louisiana's
rows. Writes data/fec.json:

    {"fetched": "...", "source": "...", "cycle": 2026, "candidates": [
        {"id": "H8LA01087", "name": "SCALISE, STEVE", "office": "H", "district": "01",
         "party": "REP", "r": 0, "s": 0, "coh": 0, "debts": 0, "loans": 0,
         "indiv": 0, "self": 0, "through": "2026-09-30"}]}

    python3 fetch_fec.py               # the cycle of the next federal election
    python3 fetch_fec.py --cycle 2028

Raised and spent are the campaign's totals for the two-year cycle (receipts
and disbursements, transfers included), cash on hand is at the end of the
latest report, and `through` is that report's last day. The file has no
header row, so every row is checked against the published layout (an id
where the id goes, amounts and a date where they go); one that doesn't fit
stops the run with the old file kept, rather than putting receipts under
spending. fec.gov is not reachable from every network; the nightly workflow
runs this on GitHub's runners. Stdlib only.
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'data', 'fec.json')
BULK = 'https://www.fec.gov/files/bulk-downloads/{cycle}/webl{yy}.zip'
# The file's published layout ("Current campaigns for House and Senate").
COLUMNS = ['CAND_ID', 'CAND_NAME', 'CAND_ICI', 'PTY_CD', 'CAND_PTY_AFFILIATION', 'TTL_RECEIPTS',
           'TRANS_FROM_AUTH', 'TTL_DISB', 'TRANS_TO_AUTH', 'COH_BOP', 'COH_COP', 'CAND_CONTRIB',
           'CAND_LOANS', 'OTHER_LOANS', 'CAND_LOAN_REPAY', 'OTHER_LOAN_REPAY', 'DEBTS_OWED_BY',
           'TTL_INDIV_CONTRIB', 'CAND_OFFICE_ST', 'CAND_OFFICE_DISTRICT', 'SPEC_ELECTION',
           'PRIM_ELECTION', 'RUN_ELECTION', 'GEN_ELECTION', 'GEN_ELECTION_PRECENT',
           'OTHER_POL_CMTE_CONTRIB', 'POL_PTY_CONTRIB', 'CVG_END_DT', 'INDIV_REFUNDS', 'CMTE_REFUNDS']
PARTY = {'REP': 'REP', 'DEM': 'DEM', 'LIB': 'LBT', 'GRE': 'GRN', 'IND': 'IND', 'NNE': 'IND', 'NPA': 'IND'}
STATE = 'LA'


def cycle_for(today):
    """The two-year cycle of the next federal election: 2026 through 2026,
    then 2028."""
    return today.year + today.year % 2


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'louisiana-airwaves/1.0'})
    err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            err = e
        except (urllib.error.URLError, TimeoutError) as e:
            err = e
        time.sleep(2 + attempt * 4)
    raise err


def amount(v):
    """A dollar field as a whole number; ValueError when it isn't one."""
    return round(float(v.strip() or 0))


def iso(mdy):
    """MM/DD/YYYY as YYYY-MM-DD; None when blank."""
    mdy = (mdy or '').strip()
    if not mdy:
        return None
    return datetime.strptime(mdy, '%m/%d/%Y').date().isoformat()


def parse(text, cols, state=STATE):
    """The rows of a webl file for one state's House and Senate campaigns.
    Raises ValueError on a row that doesn't fit the layout."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        f = line.split('|')
        if len(f) < len(cols):
            raise ValueError(f'line {n}: {len(f)} fields, expected {len(cols)}')
        x = dict(zip(cols, f))
        if not re.fullmatch(r'[HSP][0-9A-Z]{8}', x['CAND_ID']):
            raise ValueError(f'line {n}: {x["CAND_ID"]!r} is not a candidate id')
        try:
            for k in ('TTL_RECEIPTS', 'TTL_DISB', 'COH_COP'):
                amount(x[k])
            iso(x['CVG_END_DT'])
        except ValueError:
            raise ValueError(f'line {n}: amounts or date not where the layout puts them') from None
        office = x['CAND_ID'][0]
        if office == 'P' or x['CAND_OFFICE_ST'] != state:
            continue
        loans = amount(x['CAND_LOANS']) + amount(x['OTHER_LOANS'])
        out.append({
            'id': x['CAND_ID'], 'name': ' '.join(x['CAND_NAME'].split()), 'office': office,
            'district': '00' if office == 'S' else x['CAND_OFFICE_DISTRICT'].zfill(2),
            'party': PARTY.get(x['CAND_PTY_AFFILIATION'], 'OTH'),
            'r': amount(x['TTL_RECEIPTS']), 's': amount(x['TTL_DISB']), 'coh': amount(x['COH_COP']),
            'debts': amount(x['DEBTS_OWED_BY']), 'loans': loans,
            'indiv': amount(x['TTL_INDIV_CONTRIB']),
            'self': amount(x['CAND_CONTRIB']) + amount(x['CAND_LOANS']),
            'through': iso(x['CVG_END_DT']),
        })
    out.sort(key=lambda c: (c['office'] != 'S', c['district'], c['name']))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cycle', type=int, default=cycle_for(date.today()))
    args = ap.parse_args()
    url = BULK.format(cycle=args.cycle, yy=str(args.cycle)[-2:])
    print(f'Fetching {url}')
    try:
        blob = get(url, 120)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith('.txt'))
            text = z.read(name).decode('latin-1')
        rows = parse(text, COLUMNS)
    except (urllib.error.URLError, TimeoutError, zipfile.BadZipFile, StopIteration, ValueError) as e:
        print(f'  failed: {e}; keeping {os.path.relpath(OUT, HERE)} as it was')
        sys.exit(1)
    if not rows:
        print(f'  no {STATE} campaigns in the file; keeping {os.path.relpath(OUT, HERE)} as it was')
        sys.exit(1)
    data = {'fetched': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'source': url, 'cycle': args.cycle, 'candidates': rows}
    # One candidate a line, the stamp on its own, so the nightly commit step
    # can ignore a stamp-only change.
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('{\n' + ',\n'.join(f'{json.dumps(k)}: {json.dumps(v)}' for k, v in data.items()
                                   if k != 'candidates')
                + ',\n"candidates": [\n' + ',\n'.join(json.dumps(c) for c in rows) + '\n]\n}\n')
    print(f'  {len(rows)} {STATE} campaigns, reports through '
          f'{max(c["through"] or "" for c in rows) or "?"}')


if __name__ == '__main__':
    main()
