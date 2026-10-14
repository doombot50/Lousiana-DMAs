"""
Regression tests for fcc/documents.py: each case is a real political-file
document's text (tests/documents/), as pdftotext -layout or, for a scan,
tesseract read it on GitHub's runners. Run with
`python3 -m unittest discover -s tests`.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'fcc'))
from documents import agency_key, amount, parse, same_agency  # noqa: E402


def doc(name):
    with open(os.path.join(ROOT, 'tests', 'documents', name), encoding='utf-8') as f:
        return parse(f.read())


class Amounts(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(amount('$1,234.50'), 1234.5)
        self.assertEqual(amount('($499.50)'), -499.5)
        self.assertEqual(amount('$50,00'), 50.0)        # OCR's decimal comma
        self.assertEqual(amount('$1,000.00'), 1000.0)


class WideOrbitOrders(unittest.TestCase):
    def test_bill_plan_totals_and_agency(self):
        d = doc('wo_order_kalb.txt')       # KALB, Save Our Louisiana issue buy
        self.assertEqual((d['kind'], d['gross'], d['net']), ('order', 2900.0, 2465.0))
        self.assertEqual(d['agency'], 'Kingfish Communications LLC')
        self.assertEqual(d['advertiser'], 'SaveOurLouisiana.Org')
        self.assertEqual(d['order_no'], '4348571')

    def test_scanned_order(self):
        d = doc('ocr_order_wntz.txt')      # WNTZ, Firment for Congress, OCR'd
        self.assertEqual((d['gross'], d['net']), (1695.0, 1440.75))
        self.assertEqual(d['agency'], 'Flexpoint Campaigns')
        self.assertEqual(d['order_no'], '5433697')
        self.assertEqual(d['flight'], ['10/21/26', '10/27/26'])


class WideOrbitContracts(unittest.TestCase):
    def test_agency_is_the_party_under_and(self):
        d = doc('wo_contract_wdsu.txt')    # WDSU, Bill Cassidy
        self.assertEqual((d['kind'], d['gross'], d['net']), ('order', 2150.0, 1827.5))
        self.assertEqual(d['agency'], 'SRCP Media Inc')
        self.assertEqual(d['advertiser'], 'Cassidy/R/Senate')
        self.assertEqual(d['order_no'], '4399459')

    def test_nexstar_contract(self):
        d = doc('wo_contract_kard.txt')    # KARD, Mike Echols
        self.assertEqual((d['gross'], d['net']), (3330.0, 2830.5))
        self.assertEqual(d['agency'], 'MAV LLC')

    def test_scanned_contracts(self):
        d = doc('ocr_contract_kpxj.txt')   # KPXJ, Mike Johnson, OCR'd
        self.assertEqual((d['gross'], d['net']), (1690.0, 1436.5))
        self.assertEqual(d['agency'], 'Media Ad Ventures, Inc')
        d = doc('ocr_contract_ktbs.txt')   # KTBS, Julia Letlow, OCR'd
        self.assertEqual((d['gross'], d['net']), (28325.0, 24076.25))
        self.assertEqual(d['agency'], 'Brabender Cox')

    def test_klax_contract(self):
        d = doc('klax_contract.txt')       # KLAX, Louisiana Growth and Future Fund
        self.assertEqual((d['gross'], d['net']), (5560.0, 4726.0))
        self.assertEqual(d['agency'], 'Armada Strategies')
        self.assertEqual(d['advertiser'], 'Louisiana Growth and Future Fund')
        self.assertEqual(d['order_no'], '50737')


class Invoices(unittest.TestCase):
    def test_gray_invoice(self):
        d = doc('wo_invoice_kplc.txt')     # KPLC, Mike Johnson
        self.assertEqual((d['kind'], d['gross'], d['net']), ('invoice', 65400.0, 55590.0))
        self.assertEqual(d['agency'], 'Media Ad Ventures (MAV)')
        # The station's order number, which ties the invoice to its order.
        self.assertEqual((d['order_no'], d['invoice_no']), ('4581104', '4581104-1'))

    def test_bill_to_agency(self):
        self.assertEqual(doc('wo_invoice_kadn.txt')['agency'], 'Brabender Cox')
        # Nexstar's layout puts the next column on the label's line.
        self.assertEqual(doc('nexstar_invoice_kmss.txt')['agency'], 'FlexPoint Media')

    def test_reissue_is_marked(self):
        d = doc('wo_invoice_reissue_kalb.txt')
        self.assertTrue(d['reissue'])
        self.assertEqual(d['agency'], 'Kingfish Communications LLC')


class RequestForms(unittest.TestCase):
    def test_issue_form(self):
        d = doc('nab_issue_ksla.txt')
        self.assertEqual((d['kind'], d['gross']), ('request', None))
        self.assertEqual(d['agency'], 'Del Cielo Media LLC')

    def test_candidate_form_answer_on_next_line(self):
        d = doc('nab_candidate_ksla.txt')  # "N/A ESM"
        self.assertEqual(d['agency'], 'ESM')
        self.assertEqual(d['advertiser'], 'Alan Seabaugh Campaign')


class NoGuessing(unittest.TestCase):
    def test_unit_only_network_order_has_no_amount(self):
        d = doc('ocr_order_kplc.txt')      # Gray's CW network buy: units, no dollars
        self.assertIsNone(d['gross'])
        self.assertEqual(d['agency'], 'Flexpoint Media')


class AgencyNames(unittest.TestCase):
    def test_spellings_join(self):
        for a, b in [('Media Ad Ventures (MAV)', 'MAV LLC'), ('Media Ad Ventures, Inc', 'MEDIA AD VENTURES'),
                     ('Flexpoint Campaigns', 'FLEXPOINT MEDIA INC.'), ('AxMedia', 'AX MEDIA LLC'),
                     ('Arsement Media', 'ARSEMENT MEDIA GROUP. LLC'),
                     ('Louisiana Radio Network', 'KINGFISH COMMUNICATIONS D/B/A LOUISIANA RADIO NETWORK')]:
            self.assertTrue(same_agency(agency_key(a), agency_key(b)), (a, b))

    def test_short_keys_need_an_exact_match(self):
        self.assertFalse(same_agency(agency_key('ESM'), agency_key('ESM Productions')))
        self.assertTrue(same_agency(agency_key('Angie Sanders'), agency_key('Angie Sanders Ad Group, LLC')))


if __name__ == '__main__':
    unittest.main()
