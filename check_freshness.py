#!/usr/bin/env python3
"""
check_freshness.py — has any source behind the pages stopped updating?
================================================================================
The nightly rebuild is built to keep going when a source falters: the FCC
step may fail without failing the run, and a state-filings cache that
stopped refreshing still downloads fine, just old. Both leave the site up
and quietly stale. This checks each source's age and reports what is behind:

    python3 check_freshness.py --upstream 2026-10-11T09:14:02Z --report report.md

  * the la-campaign-finance `data-cache` release, refreshed nightly from the
    Ethics Administration: `--upstream` is its newest asset's update time
    (the workflow reads it from the GitHub API); empty means it couldn't be
    read, which is reported too;
  * this repo's own build (`generated` in data/station_spend.json), in case
    the rebuild itself stopped;
  * the FCC political files (`scraped` in data/fcc_political.json), and any
    station not refreshed in a week.

Exits 1 when something is stale, writing the Markdown report the workflow
puts in a GitHub issue; exits 0 when all is fresh. Stdlib only.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
D = lambda *p: os.path.join(HERE, *p)

# Each source refreshes daily; three days is two missed nights plus slack.
MAX_AGE = timedelta(days=3)


def parse(ts):
    """An ISO date or timestamp as an aware UTC datetime, or None."""
    if not ts:
        return None
    ts = ts.strip().replace('Z', '+00:00')
    try:
        t = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def problems(upstream, spend, fcc, now):
    """What is stale, as Markdown bullet lines; empty when everything is fresh."""
    out = []

    def age(label, ts, fix):
        t = parse(ts)
        if t is None:
            out.append(f'- **{label}**: no timestamp could be read. {fix}')
        elif now - t > MAX_AGE:
            out.append(f'- **{label}**: last updated {t:%Y-%m-%d %H:%M} UTC, '
                       f'{(now - t).days} days ago. {fix}')

    age('State filings (la-campaign-finance `data-cache` release)', upstream,
        'Its nightly refresh from the Ethics Administration has stopped, so the '
        'TV, radio and committee pages are showing old filings. Check that '
        "repository's Actions tab.")
    age('This site\'s build (`data/station_spend.json`)', spend.get('generated'),
        'The nightly rebuild here has not completed. Check the "Nightly rebuild" '
        'runs in the Actions tab.')
    if fcc is None:
        out.append('- **FCC political files**: `data/fcc_political.json` is missing.')
    else:
        age('FCC political files (`data/fcc_political.json`)', fcc.get('scraped'),
            'The "Refresh FCC political files" step has been failing; it never fails '
            'the run, so look at that step\'s log in recent nightly runs'
            + (f' (last recorded block: {fcc["blocked"]})' if fcc.get('blocked') else '') + '.')
        stale = [s['call'] for s in fcc.get('stations', []) if s.get('stale')]
        if stale:
            out.append(f'- **FCC stations not refreshed in a week**: {", ".join(stale)}. '
                       'The nightly rotation is not reaching them; the page marks them stale.')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--upstream', default='',
                    help="newest update time of the data-cache release's assets (ISO 8601)")
    ap.add_argument('--report', help='write the Markdown report here')
    args = ap.parse_args()

    spend = json.load(open(D('data', 'station_spend.json'), encoding='utf-8'))
    try:
        fcc = json.load(open(D('data', 'fcc_political.json'), encoding='utf-8'))
    except FileNotFoundError:
        fcc = None
    now = datetime.now(timezone.utc)
    found = problems(args.upstream, spend, fcc, now)

    if found:
        text = ('The nightly rebuild found data that has stopped updating, so '
                'airwaves.charliestephens.xyz may be showing stale figures:\n\n'
                + '\n'.join(found)
                + f'\n\nChecked {now:%Y-%m-%d %H:%M} UTC. This issue updates each night while '
                'the problem lasts and closes itself once every source is fresh again.\n')
    else:
        text = f'Every source was fresh as of {now:%Y-%m-%d %H:%M} UTC.\n'
    print(text)
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            f.write(text)
    sys.exit(1 if found else 0)


if __name__ == '__main__':
    main()
