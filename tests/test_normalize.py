"""
Regression tests for fcc/normalize.py: each case is a real filing that was
once misread. Run with `python3 -m unittest discover -s tests`.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'fcc'))
from normalize import (aliases, buyer_from_filename, buyer_key, classify, clean_name, dbs_buyer,  # noqa: E402
                       filer_index, flight, match_filer, out_of_state, parse_path, revised, tidy_caps)

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

    def test_spectrum_orders_invoices_and_proposals(self):
        # Spectrum files its cable orders and invoices in "Invoices"/"Orders"
        # folders under the office; the buyer was read as "Ord" and "Inv".
        self.assertEqual(buyer_from_filename('Inv_3268199-68067-Bill_Cassidy_for_US_Senate_VNS__526'),
                         'Bill Cassidy for US Senate')
        self.assertEqual(buyer_from_filename('Ord_3293504-68093-Julia_Letlow_for_Senate_2026'),
                         'Julia Letlow for Senate')
        self.assertEqual(buyer_from_filename(
            'P_R_John_Fleming_for_US_Senate_April_17_April_23_SHV_Rev_04-16-26_117361_Proposal'),
            'John Fleming for US Senate')
        self.assertEqual(buyer_from_filename('Fleming_for_Senate_Lake_Charles_MG_Schedule__04-21-26_118134_Proposal'),
                         'Fleming for Senate')

    def test_nothing_left_is_none(self):
        self.assertIsNone(buyer_from_filename('NAB 10-7'))


class Classify(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(classify('NAB PB-18 signed', ''), 'request')
        self.assertEqual(classify('KVHP invoice', ''), 'invoice')
        self.assertEqual(classify('Order 10-12 to 10-18', ''), 'order')
        self.assertEqual(classify('WWL McMahon 3348118', ''), 'order')
        self.assertEqual(classify('Political Disclosure Notice', ''), 'other')
        # Cable affidavits and DirecTV confirmations: spots that ran.
        self.assertEqual(classify('SHERMAN MACK FOR DA_SEP_AFF1293848_SYS 3174', ''), 'aired')
        self.assertEqual(classify('MIKE MARSIGLIA_confirm1319185_sys0222_20261009_150005', ''), 'aired')
        self.assertEqual(classify('Staffing PAC order', ''), 'order')


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


class FromTheName(unittest.TestCase):
    # WDSU, WBRZ, KSLA and KPLC write the flight into the document's name.
    def test_flights(self):
        for name, want in [('Camille Buras 10-5 to 10-18', ('2026-10-05', '2026-10-18')),
                           ('REVISED Fleming  Order Contract 4-27 thru 5-1-26', ('2026-04-27', '2026-05-01')),
                           ('KSLA Texans for Chip Roy 5.22-5.26 Contract#4416049', ('2026-05-22', '2026-05-26')),
                           ('Mike Johnson 10.12.26 thru 10.18.26', ('2026-10-12', '2026-10-18')),
                           ('12-28 to 1-3', ('2025-12-28', '2026-01-03')),
                           ('37408 Club for Growth Action 2026-09-23 2026-11-03 Order D2', ('2026-09-23', '2026-11-03'))]:
            self.assertEqual(flight(name, '2026'), want, name)

    def test_system_number_is_not_a_year(self):
        # Cox (PSIDs 002460, 004321, 005341) and DirecTV file a cable system's
        # number after the flight.
        for name, want in [('Julia Letlow 6.17-6.23-3996 order contract', ('2026-06-17', '2026-06-23')),
                           ('Julia Letlow-5.11-5.15-8644', ('2026-05-11', '2026-05-15')),
                           ('Julia Letlow 6.17-6.23-6979order contract', ('2026-06-17', '2026-06-23')),
                           ('Julia Letlow 3996-6.24-6.27-ordercontract', ('2026-06-24', '2026-06-27'))]:
            self.assertEqual(flight(name, '2026'), want, name)

    def test_not_flights(self):
        # Order numbers, a single date, and KPXJ's timestamp names.
        for name in ['PB - 20357', 'NAB 10-7', '20261009152635051', 'Order - 20349 REV 3',
                     '1185359_Order_Contract_20260612034311543', 'SCALISE FOR CONGRESS_confirm1314092_sys6979_20261006_150006']:
            self.assertIsNone(flight(name, '2026'), name)

    def test_directv_names(self):
        for raw, name in [('Steve Scalise LA CD1', 'Steve Scalise'), ('Julia Letlow LA US Senate', 'Julia Letlow'),
                          ('Hillar Moore IIIEast Baton Rouge Parish District Attorney', 'Hillar Moore III'),
                          ('Louisiana Freedom Fund', 'Louisiana Freedom Fund'),
                          # Its Senate folders end in a bare state code.
                          ('Julia Letlow LA', 'Julia Letlow'), ('Bill Cassidy LA', 'Bill Cassidy'),
                          ('Ellie Schroder LA Board of Elementary and Secondary Education D1', 'Ellie Schroder'),
                          ('John F Young LA Public Service Commissioner D1', 'John F Young')]:
            self.assertEqual(dbs_buyer(raw), name, raw)
        self.assertEqual(buyer_key(dbs_buyer('Hillar Moore IIIEast Baton Rouge Parish District Attorney')),
                         buyer_key('Hillar Moore'))

    def test_revisions(self):
        for name in ['Order - 20349 REV 3', 'Louisiana Freedom Fund Order 1514741 r5.7.26',
                     'Bill Cassidy NAB WVLA #5213225 revised 3.25.26']:
            self.assertTrue(revised(name), name)
        self.assertFalse(revised('Reveille PAC order'))


if __name__ == '__main__':
    unittest.main()
