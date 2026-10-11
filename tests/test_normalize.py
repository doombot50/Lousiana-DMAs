"""
Regression tests for fcc/normalize.py: each case is a real filing that was
once misread. Run with `python3 -m unittest discover -s tests`.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'fcc'))
from normalize import (aliases, buyer_from_filename, buyer_key, classify, clean_name,  # noqa: E402
                       filer_index, match_filer, out_of_state, parse_path, tidy_caps)

P = 'Political Files/2026/'


class ParsePath(unittest.TestCase):
    def test_level_office_buyer(self):
        self.assertEqual(parse_path(P + 'Federal/US Senate/Bill Cassidy'),
                         ('Federal', 'US Senate', 'Bill Cassidy'))

    def test_document_folders_are_not_buyers(self):
        # WWL-TV's Orders/, WAFB's PB19/, KTBS's and KPXJ's one-folder-per-document.
        for tail, buyer in [('Federal/US Senate/Cassidy-R for US Senate/Orders', 'Cassidy-R for US Senate'),
                            ('Federal/US House/Blake Miquez/PB19', 'Blake Miquez'),
                            ('Federal/US House/Mike Johson/Order - 20349 REV 3', 'Mike Johson'),
                            ('Non-Candidate Issue Ads/Protect the North Dakota Constitution - CW/PB - 63687v1',
                             'Protect the North Dakota Constitution - CW')]:
            self.assertEqual(parse_path(P + tail)[2], buyer, tail)

    def test_sub_channel_folder_is_not_a_buyer(self):
        self.assertEqual(parse_path(P + 'Non-Candidate Issue Ads/Texas PAC/NLFY - CW')[2], 'Texas PAC')

    def test_office_level_has_no_buyer(self):
        self.assertEqual(parse_path(P + 'Federal/US Senate'), ('Federal', 'US Senate', None))

    def test_housekeeping_folders_are_not_a_level(self):
        self.assertEqual(parse_path(P + 'Terms and Disclosures'), (None, None, None))


class OutOfState(unittest.TestCase):
    def test_other_states_races(self):
        for tail in ['Federal/US Senate/Texas/Ken Paxton Victory Fund',
                     'State/TX Governor/Texans for Greg Abbott',
                     'Non-Candidate Issue Ads/Lone Star Liberty PAC']:
            self.assertEqual(out_of_state(P + tail), 'Texas', tail)

    def test_louisiana_names_with_a_state_in_them(self):
        for tail in ['Non-Candidate Issue Ads/Georgia-Pacific',
                     'Local/Washington Parish Sheriff/Jason Smith']:
            self.assertIsNone(out_of_state(P + tail), tail)


class BuyerKey(unittest.TestCase):
    def test_spellings_that_must_merge(self):
        for a, b in [('Julie Letlow', 'Julia Letlow'), ('JULIE LETLOW', 'Julia Letlow'),
                     ('Hillar Moore- District Attorney', 'Hillar Moore'),
                     ('Mike Johson', 'Mike Johnson'), ('Sherman Q Mack', 'Sherman Mack'),
                     ('John E Atkins', 'John Atkins'),
                     ('Ken Paxton Victory Fund-Ken Paxton US Sentate-Texas', 'Ken Paxton'),
                     ('Texans for Greg Abbott', 'Greg Abbott')]:
            self.assertEqual(buyer_key(a), buyer_key(b), a)

    def test_party_and_office_shorthand(self):
        self.assertEqual(buyer_key('Cassidy-R for US Senate'), 'cassidy')


class Aliases(unittest.TestCase):
    def test_different_candidates_stay_apart(self):
        # Two 2026 Shreveport mayoral candidates.
        a = aliases({'State & local': {'john young', 'john paul young'}})
        self.assertEqual(a[('State & local', 'john young')], 'john young')
        self.assertEqual(a[('State & local', 'john paul young')], 'john paul young')

    def test_bare_surname_joins_the_one_full_name(self):
        a = aliases({'Federal': {'cassidy', 'bill cassidy'}})
        self.assertEqual(a[('Federal', 'cassidy')], 'bill cassidy')

    def test_ambiguous_surname_stays_alone(self):
        a = aliases({'Federal': {'johnson', 'mike johnson', 'dusty johnson'}})
        self.assertEqual(a[('Federal', 'johnson')], 'johnson')

    def test_issue_group_merges_into_its_prefix(self):
        a = aliases({'Issue': {'accountability project', 'accountability project del cielo media'}})
        self.assertEqual(a[('Issue', 'accountability project del cielo media')], 'accountability project')


class DisplayNames(unittest.TestCase):
    def test_office_written_onto_the_name(self):
        for raw, shown in [('Don Landry - District Attorney', 'Don Landry'),
                           ('Gabe Firment for Congress', 'Gabe Firment'),
                           ('Emilia Pardo LA City Court Judge D', 'Emilia Pardo'),
                           ('Pol- James Klock', 'James Klock'),
                           ('The Kristain Earles Campaign', 'Kristain Earles'),
                           ('Ron Richard Richard for Lake Charles City Court Judge', 'Ron Richard')]:
            self.assertEqual(clean_name(raw), shown, raw)

    def test_capitals(self):
        self.assertEqual(tidy_caps('CAMILLE BURAS'), 'Camille Buras')
        self.assertEqual(tidy_caps('ORLEANS PARISH DA'), 'Orleans Parish DA')
        self.assertEqual(tidy_caps('Julia Letlow'), 'Julia Letlow')


class FromFilename(unittest.TestCase):
    # KPLC and KVHP make no buyer folders; the buyer is in the file name.
    def test_reads_the_buyer(self):
        self.assertEqual(buyer_from_filename('Mike Johnson 10.12.26 thru 10.18.26'), 'Mike Johnson')
        self.assertEqual(buyer_from_filename('BILL CASSIDY FOR US SENATE KVHP 4378339 INVOICE', ('KVHP',)),
                         'BILL CASSIDY FOR US SENATE')
        self.assertEqual(buyer_from_filename('Pol-Louisiana Freedom Fund_10.09.2026_Contract'),
                         'Louisiana Freedom Fund')

    def test_nothing_left_is_none(self):
        self.assertIsNone(buyer_from_filename('NAB 10-7'))


class Classify(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(classify('NAB PB-18 signed', ''), 'request')
        self.assertEqual(classify('KVHP invoice', ''), 'invoice')
        self.assertEqual(classify('Order 10-12 to 10-18', ''), 'order')
        self.assertEqual(classify('WWL McMahon 3348118', ''), 'order')
        self.assertEqual(classify('Political Disclosure Notice', ''), 'other')


class MatchFiler(unittest.TestCase):
    idx = filer_index({'1': {'n': 'Donald D. Landry'}, '2': {'n': 'M. Thomas ("Tom") Arceneaux'},
                       '3': {'n': 'Louisiana First PAC'}, '4': {'n': 'Mike Echols'},
                       '5': {'n': 'Michael Echols'}, '6': {'n': 'JUSTICE PAC'}})

    def test_nicknames_and_legal_names(self):
        self.assertEqual(match_filer(['Don Landry'], self.idx), '1')
        self.assertEqual(match_filer(['Tom Arceneaux'], self.idx), '2')

    def test_two_filers_one_name_is_no_match(self):
        self.assertIsNone(match_filer(['Mike Echols'], self.idx))

    def test_groups_need_their_whole_name(self):
        self.assertEqual(match_filer(['Justice PAC'], self.idx, person=False), '6')
        self.assertIsNone(match_filer(['Louisiana First Victory Fund'], self.idx, person=False))

    def test_unknown_is_none(self):
        self.assertIsNone(match_filer(['Will Keaty'], self.idx))


if __name__ == '__main__':
    unittest.main()
