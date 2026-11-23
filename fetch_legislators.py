#!/usr/bin/env python3
"""
fetch_legislators.py — who holds every Louisiana House and Senate seat now,
and whether they can run for it again in 2027
================================================================================
The races page's 2027 tab lists the offices up and their incumbents before
qualifying. Its source for incumbents, the Secretary of State's results,
carries only contested races: a legislator elected without opposition never
appears there, and in 2023 that was 47 of 105 House seats and 20 of 39 Senate
seats. The Legislature's own rosters list every member, and both chambers
publish term limits: a member who has served more than two and a half terms in
three consecutive terms can't run for the same chamber again (La. Const. art.
III, sec. 4(E)).

  * House: H_Reps_FullInfo (name, district, party) and H_Reps_Term<YEAR>.aspx,
    the members eligible to serve through the term ending in YEAR. Those on
    the 2028 list are in their final term and can't run for the House in 2027.
  * Senate: Senators_FullInfo and Senators_ByTermLimits.aspx ("Final Term
    2024-2028" means the same).

Writes data/legislators.json. Run nightly with the other fetchers; the
Legislature's sites aren't reachable from every network.

    python3 fetch_legislators.py
"""
import html
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'data', 'legislators.json')
HOUSE = 'https://house.louisiana.gov/H_Reps/'
SENATE = 'https://senate.la.gov/'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; louisiana-airwaves data fetch)'}
PARTY = {'Republican': 'REP', 'Democrat': 'DEM', 'Independent': 'IND'}


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def lines(page):
    """The page as its visible text, one non-empty line per element."""
    page = re.sub(r'<script.*?</script>|<style.*?</style>', '', page, flags=re.S | re.I)
    text = html.unescape(re.sub(r'<[^>]+>', '\n', page))
    return [' '.join(x.split()) for x in text.split('\n') if x.strip()]


def full_name(last_first):
    """'Bamburg, Jr., Dennis' -> 'Dennis Bamburg, Jr.'; 'Amedée, Beryl' -> 'Beryl Amedée'."""
    parts = [p.strip() for p in last_first.split(',')]
    if len(parts) == 3:
        return f'{parts[2]} {parts[0]}, {parts[1]}'
    if len(parts) == 2:
        return f'{parts[1]} {parts[0]}'
    return last_first


NAME = re.compile(r"^[A-Z][A-Za-zÀ-ÿ'\-. ]+, [A-Za-zÀ-ÿ'\"\-. ,]+$")


def roster(ls):
    """Members from a FullInfo page: a 'Last, First' line, then 'District', the
    number, and the party within the next few lines."""
    out = []
    for i, l in enumerate(ls):
        if (m := re.fullmatch(r'Vacant - District (\d+)', l)):
            out.append({'d': int(m.group(1)), 'name': None, 'party': None, 'vacant': True})
            continue
        if not NAME.match(l) or i + 4 >= len(ls):
            continue
        win = ls[i + 1:i + 5]
        if 'District' not in win:
            continue
        j = win.index('District')
        if j + 2 >= len(win) or not win[j + 1].isdigit() or win[j + 2] not in PARTY:
            continue
        out.append({'d': int(win[j + 1]), 'name': full_name(l), 'party': PARTY[win[j + 2]]})
    return out


def house_terms():
    """name -> last year of the final term the member may serve, from the
    House's term-limit lists ('eligible to serve through the 2024 - 2028 term')."""
    final = {}
    for end in (2028, 2032, 2036, 2040):
        try:
            ls = lines(get(f'{HOUSE}H_Reps_Term{end}.aspx'))
        except Exception:
            continue
        if not any('Eligible to serve' in l for l in ls):
            continue
        for i, l in enumerate(ls):
            if NAME.match(l) and i + 3 < len(ls) and ls[i + 1].isdigit() and ls[i + 2] in PARTY \
                    and re.fullmatch(r'\d{4}', ls[i + 3]):
                final[(int(ls[i + 1]), l)] = {'final': end, 'elected': int(ls[i + 3])}
    return final


def senate_terms():
    final = {}
    ls = lines(get(f'{SENATE}Senators_ByTermLimits.aspx'))
    for i, l in enumerate(ls):
        if NAME.match(l) and i + 4 < len(ls) and ls[i + 1] == 'Year Elected:' and ls[i + 3] == 'Final Term':
            m = re.fullmatch(r'(\d{4})\s*-\s*(\d{4})', ls[i + 4])
            if m and ls[i + 2].isdigit():
                final[l] = {'final': int(m.group(2)), 'elected': int(ls[i + 2])}
    return final


def main():
    house = roster(lines(get(f'{HOUSE}H_Reps_FullInfo')))
    senate = roster(lines(get(f'{SENATE}Senators_FullInfo')))
    if len(house) < 95 or len(senate) < 35:
        sys.exit(f'Rosters look incomplete ({len(house)} House, {len(senate)} Senate): not writing.')
    ht, st = house_terms(), senate_terms()
    # FullInfo names and the term lists' names are both "Last, First" from the
    # same site; match on the raw form, then district + surname for drift.
    for m in house:
        if m.get('vacant'):
            continue
        raw = next((k for k in ht if k[0] == m['d']), None)
        if raw:
            m.update(ht[raw])
    raw_by_full = {full_name(k): v for k, v in st.items()}
    for m in senate:
        if m.get('vacant'):
            continue
        v = raw_by_full.get(m['name']) or next(
            (v for k, v in st.items() if k.split(',')[0] == m['name'].split()[-1].rstrip(',')), None)
        if v:
            m.update(v)
    for m in house + senate:
        # can't run again for this chamber in the October 2027 election
        m['tl'] = m.get('final') == 2028 and not m.get('vacant')
    doc = {
        'fetched': time.strftime('%Y-%m-%d'),
        'source': 'house.louisiana.gov (H_Reps_FullInfo, H_Reps_Term*.aspx); '
                  'senate.la.gov (Senators_FullInfo, Senators_ByTermLimits.aspx)',
        'house': sorted(house, key=lambda m: m['d']),
        'senate': sorted(senate, key=lambda m: m['d']),
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    for ch in ('house', 'senate'):
        ms = doc[ch]
        print(f"{ch}: {len(ms)} members, {sum(m['tl'] for m in ms)} term-limited in 2027, "
              f"{sum(bool(m.get('vacant')) for m in ms)} vacant, "
              f"{sum('final' not in m and not m.get('vacant') for m in ms)} without a term-limit entry")


if __name__ == '__main__':
    main()
