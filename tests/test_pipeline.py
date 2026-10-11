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
from datetime import datetime, timezone

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
        self.assertEqual([x['name'] for x in self.F['all']], ['Don Landry'])

    def test_headline_counts_exclude_other_states(self):
        self.assertEqual(self.F['docs'], 6)


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
        self.assertEqual(cm['1314']['party'], 'REP')               # PARTY_CORRECTION

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
    def test_rules(self):
        self.assertEqual(party_of('Gumbo PAC', 'OTH'), 'DEM')            # OTH, public alignment
        self.assertEqual(party_of('Gumbo PAC', 'REP'), 'REP')            # a stated party stands...
        self.assertEqual(party_of('Blair Edwards', 'DEM', '1314'), 'REP')  # ...unless corrected
        self.assertEqual(party_of('Someone', None), None)


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
            {'scraped': '2026-10-11T00:00:00Z', 'stations': [{'call': 'KTBS', 'stale': True}]}, self.now)
        self.assertEqual(len(found), 4)


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
