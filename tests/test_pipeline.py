"""
Tests for the builders around the normalizer: the political-file rollup on a
small fixture, the TV and radio spend matching on synthetic filing rows, the
party rules, the scraper's year window and the freshness check.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'fcc'))
import build_radio_spend  # noqa: E402
import build_station_spend  # noqa: E402
import check_freshness  # noqa: E402
import summary  # noqa: E402
from filings import party_of  # noqa: E402
from scrape_political_files import default_years  # noqa: E402


def dump(obj, path):
    with open(path, 'w') as f:
        json.dump(obj, f)


def load(path):
    with open(path) as f:
        return json.load(f)


def doc(path, name='doc.pdf', up='2026-10-09T12:00:00'):
    return {'path': 'Political Files/2026/' + path, 'name': name, 'uploaded': up, 'folder_id': 'x'}


class Summary(unittest.TestCase):
    """fcc_summary on a few stations' worth of political file."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = os.path.join(cls.tmp.name, 'data')
        os.makedirs(d)
        stations = {
            # KTBS files Texas's Senate race with no state named; KSLA names it.
            'KTBS': [doc('Federal/US Senate/Ken Paxton/Order - 20357')],
            'KSLA': [doc('Federal/US Senate/Texas/Ken Paxton Victory Fund')],
            # KTVE files a Senate candidate under State; KALB under Federal.
            'KTVE': [doc('State/Julia Letlow')],
            'KALB': [doc('Federal/US Senate/Julia Letlow'), doc('Federal/US Senate/Julia Letlow', 'b.pdf')],
            'KMSS': [doc('Local/Shreveport Mayor/John Young'), doc('Local/Shreveport Mayor/John Paul Young')],
            'KATC': [doc('Local/District Attorney/Don Landry - District Attorney')],
        }
        dump({'scraped': '2026-10-11T00:00:00Z', 'no_online_file': [],
              'stations': [{'call': c, 'fcc_call': c, 'scraped_at': '2026-10-11T00:00:00Z',
                            'year_folders': {}, 'folders': {}, 'files': f}
                           for c, f in stations.items()]},
             os.path.join(d, 'fcc_political.json'))
        dump([{'call': c} for c in stations], os.path.join(d, 'stations.json'))
        dump({'4525': {'n': 'Donald D. Landry', 'p': 'REP'}}, os.path.join(d, 'filers.json'))
        real = summary.D
        summary.D = lambda *p: os.path.join(cls.tmp.name, *p)
        try:
            cls.F = summary.fcc_summary({'KTBS': 'SHV', 'KSLA': 'SHV', 'KMSS': 'SHV', 'KTVE': 'MON',
                                         'KALB': 'ALX', 'KATC': 'LAF'}, full=True)
        finally:
            summary.D = real
        cls.by = {b['name']: b for b in cls.F['buyers']}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_out_of_state_at_one_station_is_out_of_state_everywhere(self):
        b = self.by['Ken Paxton']
        self.assertEqual((b['b'], b['state'], b['docs']), ('Out of state', 'Texas', 2))
        self.assertEqual(self.F['away']['docs'], 2)

    def test_a_federal_candidate_filed_under_state_is_federal(self):
        b = self.by['Julia Letlow']
        self.assertEqual((b['b'], b['docs'], len(b['st'])), ('Federal', 3, 2))

    def test_different_candidates_stay_apart(self):
        self.assertIn('John Young', self.by)
        self.assertIn('John Paul Young', self.by)

    def test_state_candidate_links_to_the_filer(self):
        b = self.by['Don Landry']
        self.assertEqual((b['f'], b['office']), ('4525', 'District Attorney'))
        self.assertEqual([x['name'] for x in self.F['all'] if x['f']], ['Don Landry'])

    def test_headline_counts_exclude_other_states(self):
        self.assertEqual(self.F['docs'], 6)


class SummaryMedia(unittest.TestCase):
    """Cable systems' files join TV's under the same buyer, labeled and tagged."""

    def test_cable_joins_tv(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, 'data')
            os.makedirs(d)
            st = lambda call, files, **k: dict({'call': call, 'scraped_at': '2026-10-11T00:00:00Z',
                                                'year_folders': {}, 'folders': {}, 'files': files}, **k)
            dump({'scraped': '2026-10-11T00:00:00Z', 'stations': [
                st('WBRZ', [doc('Local/District Attorney/Hillar Moore', 'Hillar Moore 10-5 to 10-18')])]},
                os.path.join(d, 'fcc_political.json'))
            dump({'scraped': '2026-10-11T00:00:00Z', 'stations': [
                st('002460', [doc('State/Hillar Moore', 'Hillar Moore REV 2', '2026-10-10T09:00:00')],
                   profile='cable-profile/002460')]}, os.path.join(d, 'fcc_cable.json'))
            dump({'scraped': '2026-10-11T00:00:00Z', 'stations': [
                st('DIRECTV', [doc('Local/Louisiana/Hillar Moore IIIEast Baton Rouge Parish District Attorney',
                                   'HILLAR MOORE FOR LA_confirm1312860')], profile='dbs-profile/directv')]},
                os.path.join(d, 'fcc_dbs.json'))
            dump({'002460': {'name': 'Cox Baton Rouge', 'market': 'BR'}}, os.path.join(d, 'cable_systems.json'))
            dump([], os.path.join(d, 'radio_stations.json'))
            dump([{'call': 'WBRZ'}], os.path.join(d, 'stations.json'))
            dump({}, os.path.join(d, 'filers.json'))
            real = summary.D
            summary.D = lambda *p: os.path.join(tmp, *p)
            try:
                F = summary.fcc_summary({'WBRZ': 'BR'}, full=True, media=('tv', 'cable', 'dbs'))
                radio_only = summary.fcc_summary({'WBRZ': 'BR'}, full=True, media=('radio',))
                tv_only = summary.fcc_summary({'WBRZ': 'BR'}, full=True)
            finally:
                summary.D = real
        b = next(x for x in F['all'] if x['name'] == 'Hillar Moore')
        # DirecTV's Louisiana folder and glued-on office don't split the buyer.
        self.assertEqual([(s['c'], s['m'], s['k']) for s in b['st']],
                         [('WBRZ', 'tv', 'BR'), ('Cox Baton Rouge', 'cable', 'BR'), ('DirecTV', 'dbs', None)])
        self.assertEqual((b['docs'], b['revs'], b['onAir'][1], sum(b['wk'])), (3, 1, '2026-10-18', 3))
        self.assertEqual(F['media'], {'tv': 1, 'cable': 1, 'dbs': 1})
        self.assertIsNone(radio_only)        # no radio file yet
        self.assertEqual(tv_only['all'][0]['docs'], 1)


class OutsideGroups(unittest.TestCase):
    """Issue groups tied to a race by what their documents say."""

    def test_cues(self):
        from build_races_page import outside_groups
        row = lambda n, b, docnames: {'name': n, 'b': b, 'docnames': docnames, 'docs': 2, 'recent': 1,
                                      'latest': '2026-10-09', 'st': [], 'stRecent': [], 'fresh': [],
                                      'wk': [0] * 10, 'revs': 0, 'aired': 0}
        F = {'all': [row('Club for Growth Action', 'Issue', ['N LA CFGA-LA CD6 NAB CBTS092226']),
                     row('Accountability Project', 'Issue', ['ACCOUNTABILITY PROJECT AD ID CREEP SCALISE 30']),
                     row('Friends of Justice', 'Issue', ['Friends of Justice NAB page 1'])]}
        e = {'posted': True, 'races': [
            {'id': 'cd1', 'o': 'U. S. Representative -- 1st Congressional District',
             'c': [{'n': 'Steve Scalise', 'pf': {'docs': 8}}]},
            {'id': 'cd6', 'o': 'U. S. Representative -- 6th Congressional District', 'c': [{'n': 'Blake Miguez'}]},
            {'id': 'sb', 'o': 'Natchitoches Parish Member of School Board -- District 3', 'c': [{'n': 'Kim Page'}]}]}
        outside_groups(F, e)
        got = {r['id']: [(g['n'], g['cue']) for g in r.get('out', [])] for r in e['races']}
        self.assertEqual(got, {'cd1': [('Accountability Project', 'names Scalise in its ad titles')],
                               'cd6': [('Club for Growth Action', 'filed for LA CD6')],
                               'sb': []})   # "page 1" is a word; Kim Page isn't buying airtime


class SpendMatching(unittest.TestCase):
    """The TV and radio builders on synthetic filing rows."""

    def run_builder(self, mod, rows, out):
        args = mod.parse_args(['--out', out])
        add, finish = mod.builder(args, ['x/expenditures_yr2026.json.gz'])
        for r in rows:
            add(dict({'date': '2026-03-01', 'filerNumber': '10', 'candidate': 'A Buyer', 'party': 'REP'}, **r), 2026)
        finish(len(rows), '2026-03-01')
        return load(out)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_tv(self):
        out = self.run_builder(build_station_spend, [
            {'contributor': 'KADN-TV CHANNEL 15', 'amount': 100},
            {'contributor': 'KARD-TV KTVE-TV', 'amount': 200},     # combined buy, split
            {'contributor': 'WWL-AM RADIO', 'amount': 50},         # radio sister, excluded
            {'contributor': 'WWL', 'amount': 30},                  # bare call: TV, disclosed
            {'contributor': 'Total Wine', 'amount': 999},          # not a station
            {'contributor': 'KADN', 'amount': 7, 'filerNumber': '1314', 'party': 'DEM'},
        ], os.path.join(self.tmp.name, 'station_spend.json'))
        spend = {s['call']: s['spend'] for s in out['stations']}
        self.assertEqual((spend['KADN'], spend['KARD'], spend['KTVE'], spend['WWL-TV']), (107, 100, 100, 30))
        self.assertEqual(out['total_spend'], 337)
        self.assertEqual(out['caveats']['radio_excluded'], {'WWL-TV': 50})
        self.assertEqual(out['caveats']['ambiguous_bare_call'], {'WWL-TV': 30})
        self.assertEqual(out['caveats']['combined_buys']['amount'], 200)
        cm = load(os.path.join(self.tmp.name, 'committees_tv.json'))
        self.assertEqual(cm['1314']['party'], 'REP')               # data/party_corrections.json

    def test_radio(self):
        out = self.run_builder(build_radio_spend, [
            {'contributor': 'KBON', 'amount': 40},                 # allowlisted, short name
            {'contributor': 'KBON-FM', 'amount': 10},
            {'contributor': 'KIRK TALBOT FOR SHERIFF', 'amount': 500},   # a person, not a station
            {'contributor': 'WWL', 'amount': 30},                  # bare TV sister: the TV page's
            {'contributor': 'WWL-AM', 'amount': 20},               # marked radio: counted here
        ], os.path.join(self.tmp.name, 'radio_spend.json'))
        spend = {s['call']: s['spend'] for s in out['stations']}
        self.assertEqual(spend, {'KBON': 50, 'WWL': 20})
        self.assertEqual(out['caveats']['tv_sister_radio_rows'], {'WWL': 20})
        self.assertEqual(out['caveats']['name_collisions_rejected']['amount'], 500)
        self.assertEqual(out['total_spend'], 70)


class PartyRules(unittest.TestCase):
    """The filer-keyed corrections shared with la-campaign-finance."""

    FIXES = {'3354': {'party': 'DEM', 'when': 'oth'}, '1314': {'party': 'REP', 'when': 'always'}}

    def test_rules(self):
        self.assertEqual(party_of('OTH', '3354', self.FIXES), 'DEM')     # OTH, public alignment
        self.assertEqual(party_of(None, '3354', self.FIXES), 'DEM')
        self.assertEqual(party_of('REP', '3354', self.FIXES), 'REP')     # a stated party stands...
        self.assertEqual(party_of('DEM', ' 1314', self.FIXES), 'REP')    # ...unless corrected outright
        self.assertEqual(party_of('DEM', '99', self.FIXES), 'DEM')
        self.assertEqual(party_of(None, None, self.FIXES), None)

    def test_shared_file_loads(self):
        # The synced copy carries the corrections this repo used to list itself.
        from filings import PARTY_CORRECTIONS
        for fn, p in {'1314': 'REP', '3354': 'DEM', '6034': 'REP', '632': 'DEM', '621': 'DEM', '160': 'REP'}.items():
            self.assertEqual(PARTY_CORRECTIONS[fn]['party'], p)

    def test_sync_keeps_the_copy_when_the_release_lacks_it(self):
        import fetch_cache
        dest = os.path.join(tempfile.mkdtemp(), 'party_corrections.json')
        dump({'filers': {'1': {'party': 'REP', 'when': 'oth'}}}, dest)
        real = fetch_cache.fetch
        try:
            fetch_cache.fetch = lambda url, path: False                 # 404
            fetch_cache.sync_party_corrections(dest)
            self.assertEqual(load(dest)['filers']['1']['party'], 'REP')

            def bad(url, path):
                with open(path, 'w') as f:
                    f.write('not json')
                return True
            fetch_cache.fetch = bad
            fetch_cache.sync_party_corrections(dest)
            self.assertEqual(load(dest)['filers']['1']['party'], 'REP')
            self.assertFalse(os.path.exists(dest + '.new'))
        finally:
            fetch_cache.fetch = real


class ScraperYears(unittest.TestCase):
    def test_odd_years_keep_the_even_year_before(self):
        self.assertEqual(default_years(2026), [2026, 2027])
        self.assertEqual(default_years(2027), [2026, 2027, 2028])


class Freshness(unittest.TestCase):
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)

    def test_fresh(self):
        self.assertEqual(check_freshness.problems(
            '2026-10-19T15:00:00Z', {'generated': '2026-10-20'},
            {'scraped': '2026-10-20T00:00:00Z', 'stations': []}, self.now), [])

    def test_stale_and_unreadable(self):
        found = check_freshness.problems(
            '', {'generated': '2026-10-10'},
            {'scraped': '2026-10-11T00:00:00Z', 'stations': [{'call': 'KTBS', 'stale': True}]}, self.now,
            {'fetched': '2026-10-01T11:00:00Z'}, {'fetched': '2026-10-02T11:00:00Z'})
        self.assertEqual(len(found), 6)
        self.assertIn('FEC', found[-1])


if __name__ == '__main__':
    unittest.main()


class Prose(unittest.TestCase):
    """The phrases the pages' copy is built from (prose.py)."""

    def test_share_words(self):
        from prose import share_words
        self.assertEqual(share_words(0.33), 'a third')
        self.assertEqual(share_words(0.30), 'nearly a third')
        self.assertEqual(share_words(0.28), 'more than a quarter')
        self.assertEqual(share_words(0.55), 'more than half')

    def test_ahead_of(self):
        from prose import ahead_of
        self.assertEqual(ahead_of(33, 17.7), 'nearly double')
        self.assertEqual(ahead_of(28.9, 27.2), 'just ahead of')
        self.assertEqual(ahead_of(40, 20), 'double')

    def test_words_and_money(self):
        from prose import money, money_words, words
        self.assertEqual((words(13), words(30), words(67), words(1322)), ('thirteen', 'thirty', 'sixty-seven', '1,322'))
        self.assertEqual((money(11348197), money(1520591), money(947767), money(245.5)),
                         ('$11.3M', '$1.52M', '$948K', '$246'))
        self.assertEqual(money_words(121e6), '$121 million')

    def test_unfilled_markers_stop_the_build(self):
        from page_shell import fill_tokens
        spend = {'years_covered': [2000, 2026], 'data_through': '2026-10-05'}
        self.assertIn('2000–2026', fill_tokens('__SPAN__ {{a}}', spend, 'tv', {'a': 1}))
        with self.assertRaises(SystemExit):
            fill_tokens('{{missing}}', spend, 'tv', {})


class FilerMediaExport(unittest.TestCase):
    """data/filer_media.json, the handoff to the campaign-finance dashboard."""

    def test_shape_and_one_line_per_filer(self):
        from build_committees_page import media_export
        rows = [
            {'f': '1314', 'n': 'Blair Edwards', 'tv': 300, 'ra': 0, 'nts': 2, 'nrs': 0,
             'y': {'2026': [300, 0]}, 'ts': [['WVUE', 200, 'nola'], ['WAFB', 100, 'br']], 'rs': [],
             'pf': {'docs': 9, 'recent': 2, 'latest': '2026-10-07',
                    'st': [{'c': 'WVUE', 'r': True}, {'c': 'WAFB', 'r': False}]}},
            {'f': '10', 'n': 'Paul Bonin', 'tv': 0, 'ra': 40, 'nts': 0, 'nrs': 1,
             'y': {'2008': [0, 40]}, 'ts': [], 'rs': [['WWL', 40]]},
        ]
        text = media_export(rows, {'scraped': '2026-10-11', 'since': '2026-09-28', 'days': 14},
                            {'generated': '2026-10-11', 'data_through': '2026-10-05'})
        d = json.loads(text)
        self.assertEqual(d['data_through'], '2026-10-05')
        self.assertEqual(d['filers']['1314']['pf'],
                         {'docs': 9, 'recent': 2, 'latest': '2026-10-07', 'st': 2, 'live': 1})
        self.assertEqual(d['filers']['1314']['top'], ['WVUE', 'WAFB'])
        self.assertEqual(d['filers']['10']['top'], ['WWL'])          # radio when no TV
        self.assertNotIn('pf', d['filers']['10'])
        # The date stamp sits on a line of its own, so the nightly commit
        # step's -I'"generated":' can ignore a stamp-only change.
        self.assertIn('\n"generated": "2026-10-11",\n', text)


class Ballot(unittest.TestCase):
    """fetch_ballot.races on the portal's shapes."""

    def test_parish_races_get_their_parish_and_measures_are_dropped(self):
        import fetch_ballot
        cands = {'Races': {'Race': [
            {'ID': '1', 'SpecificTitle': 'Member of School Board -- District 7', 'NumberToElect': '1',
             'Choice': [{'ID': 'a', 'Desc': 'Hannah Amoroso (IND)'}, {'ID': 'b', 'Desc': 'Chris "CJ" Spalatin (DEM)'}]},
            {'ID': '2', 'SpecificTitle': 'Mayor -- City of Baton Rouge', 'Choice': {'ID': 'c', 'Desc': 'Someone (REP)'}},
            {'ID': '3', 'SpecificTitle': 'Proposition -- Parishwide', 'Choice': [{'ID': 'y', 'Desc': 'Yes'}, {'ID': 'n', 'Desc': 'No'}]},
            {'ID': '4', 'SpecificTitle': 'DPEC Member -- District 1', 'Choice': {'ID': 'd', 'Desc': 'X Y (DEM)'}},
        ]}}
        votes = {'Races': {'Race': {'ID': '1', 'Choice': [{'ID': 'a', 'VoteTotal': '120', 'Outcome': 'Elected'}]}}}
        rs = fetch_ballot.races(cands, votes, 'East Baton Rouge')
        self.assertEqual([r['office'] for r in rs], ['East Baton Rouge Parish Member of School Board -- District 7',
                                                     'Mayor -- City of Baton Rouge'])
        self.assertEqual(rs[0]['candidates'][0], {'name': 'Hannah Amoroso', 'party': 'IND', 'votes': 120, 'outcome': 'Elected'})
        self.assertEqual(rs[0]['candidates'][1]['name'], 'Chris CJ Spalatin')

    def test_parishes_are_numbered_alphabetically(self):
        import fetch_ballot
        self.assertEqual((len(fetch_ballot.PARISHES), fetch_ballot.PARISHES[16]), (64, 'East Baton Rouge'))


class Races(unittest.TestCase):
    def test_tiers_follow_the_money_wins_page(self):
        from build_races_page import tier
        for office, t in [('U. S. Representative -- 6th Congressional District', 'Federal'),
                          ('Governor', 'Statewide'), ('State Senator -- 9th Senatorial District', 'Legislative'),
                          ('District Judge -- 19th Judicial District Court, Div. A', 'Judicial'),
                          ('Justice -- Supreme Court, 1st Supreme Court District', 'Judicial'),
                          ('District Attorney -- 19th Judicial District Court', 'Local'),
                          ('East Baton Rouge Parish Member of School Board -- District 7', 'Local'),
                          ('Justice of the Peace -- Justice of the Peace Ward 1', 'Local')]:
            self.assertEqual(tier(office), t, office)

    def test_namesakes_the_history_keeps_apart(self):
        from build_races_page import Finance
        fin = Finance(None)
        fin.history = {'EDWARD JAMES': [{'office': 'Alderman -- Town of Maringouin', 'date': '11/02/2010'}],
                       'EDWARD TED JAMES': [{'office': 'State Representative -- 101st Representative District',
                                             'date': '11/19/2011'}],
                       'KIMBERLY BAINGUEL': [{'office': 'School Board', 'date': '11/08/2022'}],
                       'KIMBERLY MARIE BAINGUEL': [{'office': 'School Board', 'date': '11/03/2026'}]}
        self.assertTrue(fin.different_people('Edward James, Jr.', 'Edward (Ted) James'))
        self.assertFalse(fin.different_people('Kimberly Marie Bainguel', 'Kimberly Bainguel'))
        self.assertFalse(fin.different_people('Megan Garretson', 'Megan Garretson'))

    def test_federal_seats_from_race_titles(self):
        from build_races_page import fec_seat
        self.assertEqual(fec_seat('U. S. Senator'), ('S', '00'))
        self.assertEqual(fec_seat('U. S. Representative -- 4th Congressional District'), ('H', '04'))
        self.assertIsNone(fec_seat('State Senator -- 9th Senatorial District'))

    def test_federal_candidates_match_the_fec_campaign_for_their_seat(self):
        from build_races_page import Fec
        c = lambda i, n, o, d: {'id': i, 'name': n, 'office': o, 'district': d, 'r': 10, 's': 5,
                                'coh': 3, 'loans': 0, 'through': '2026-09-30'}
        fec = Fec({'cycle': 2026, 'candidates': [
            c('S6LA00001', 'LETLOW, JULIA', 'S', '00'),
            c('H0LA05001', 'LETLOW, JULIA', 'H', '05'),        # her old House campaign
            c('H8LA01001', 'SCALISE, STEVE', 'H', '01'),
            c('H6LA02001', 'CARTER, TROY A. SR.', 'H', '02'),
            c('H6LA03001', 'HIGGINS, GLEN CLAY', 'H', '03'),
            c('H6LA03002', 'WALKER, CALEB', 'H', '03'),
            c('H6LA04001', 'JOHNSON, JAMES MICHAEL', 'H', '04'),
            c('H6LA06001', 'DAVIS, LARRY III', 'H', '06'),
            c('H6LA06002', 'DAVIS, LAWRENCE', 'H', '06'),
            c('H6LA05001', 'ECHOLS, MICHAEL', 'H', '05')]})
        sen, d = 'U. S. Senator', 'U. S. Representative -- {} Congressional District'.format
        got = lambda n, o: (fec.match(n, o) or {}).get('id')
        self.assertEqual(got('Julia Letlow', sen), 'S6LA00001')            # the Senate seat's, not the House's
        self.assertEqual(got('Steve Scalise', d('1st')), 'H8LA01001')
        self.assertEqual(got('Troy A. Carter, Sr.', d('2nd')), 'H6LA02001')
        self.assertEqual(got('Clay Higgins', d('3rd')), 'H6LA03001')        # by surname, a given name shared
        self.assertEqual(got('Caleb With a C Walker', d('3rd')), 'H6LA03002')
        self.assertEqual(got('Mike Johnson', d('4th')), 'H6LA04001')
        self.assertIsNone(got('Jamie Davis', sen))                          # no Senate Davis
        self.assertIsNone(got('Larry Davis III', d('6th')))                 # two Davises for the seat
        self.assertIsNone(got('Mike Echols', d('4th')))                     # another seat's campaign
        self.assertIsNone(got('Gordon Heslop', d('4th')))
        self.assertEqual(fec.money(fec.match('Steve Scalise', d('1st'))),
                         {'r': 10, 's': 5, 'fec': ['H8LA01001', 2026], 'coh': [3, '2026-09-30']})

    def test_fec_bulk_rows(self):
        import fetch_fec
        row = lambda i, n, st, dist, rec, disb, coh, end: '|'.join(
            [i, n, 'I', '1', 'REP', rec, '0', disb, '0', '0', coh, '100', '200', '50', '0', '0', '7',
             '900', st, dist, '', '', '', '', '', '0', '0', end, '0', '0'])
        text = '\n'.join([row('H8LA01087', 'SCALISE, STEVE', 'LA', '01', '1000.40', '500', '250', '09/30/2026'),
                          row('S6LA00001', 'LETLOW,  JULIA', 'LA', '00', '20', '10', '5', ''),
                          row('H6TX01001', 'SOMEONE, ELSE', 'TX', '01', '1', '1', '1', '09/30/2026'),
                          row('P00006213', 'PRESIDENT, A', '', '00', '1', '1', '1', '09/30/2026')])
        got = fetch_fec.parse(text, fetch_fec.COLUMNS)
        self.assertEqual([c['id'] for c in got], ['S6LA00001', 'H8LA01087'])   # Senate first, Texas out
        self.assertEqual(got[1], {'id': 'H8LA01087', 'name': 'SCALISE, STEVE', 'office': 'H', 'district': '01',
                                  'party': 'REP', 'r': 1000, 's': 500, 'coh': 250, 'debts': 7, 'loans': 250,
                                  'indiv': 900, 'self': 300, 'through': '2026-09-30'})
        self.assertEqual((got[0]['name'], got[0]['through']), ('LETLOW, JULIA', None))
        with self.assertRaises(ValueError):
            fetch_fec.parse('C00123|short', fetch_fec.COLUMNS)
        with self.assertRaises(ValueError):                      # a column shifted
            fetch_fec.parse(row('H8LA01087', 'SCALISE, STEVE', 'LA', '01', 'REP', '500', '250', '09/30/2026'),
                            fetch_fec.COLUMNS)
        self.assertEqual([fetch_fec.cycle_for(date(y, 6, 1)) for y in (2026, 2027)], [2026, 2028])

    def test_fcc_rotation_tightens_before_an_election(self):
        from scrape_political_files import stations_tonight
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'ballot.json')
            dump({'elections': [{'date': '2026-11-03'}, {'date': '2026-12-12'}]}, path)
            got = [stations_tonight(8, d, path) for d in ('2026-09-01', '2026-10-12', '2026-10-28', '2026-11-04')]
            self.assertEqual(got, [8, 14, 28, 8])
            self.assertEqual(stations_tonight(8, '2026-10-28', os.path.join(tmp, 'none.json')), 8)
