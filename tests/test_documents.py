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
from summary import booked  # noqa: E402


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


class Radio(unittest.TestCase):
    def test_iheart_confirmation(self):
        d = doc('iheart_wjbo.txt')         # WJBO, Accountability Project, through iHeart's rep firm
        self.assertEqual((d['kind'], d['layout'], d['gross'], d['net']), ('order', 'iheart', 10000.0, 8500.0))
        self.assertEqual((d['advertiser'], d['order_no']), ('Accountability Project Inc', '1100655318'))
        self.assertIsNone(d['agency'])     # Katz Media Group is the rep, not an agency
        self.assertIsNone(doc('iheart_wrno.txt')['agency'])     # "Political Candidate - Direct"
        d = doc('iheart_wjbo_agency.txt')  # Club for Growth
        self.assertEqual((d['gross'], d['agency']), (22500.0, 'Medium Buying, LLC'))

    def test_iheart_labelled(self):
        d = doc('iheart_wynk_labelled.txt')
        self.assertEqual((d['gross'], d['net']), (13050.0, 11092.5))
        self.assertEqual((d['agency'], d['advertiser']), ('Taylor Media Services', 'Sherman Mack for DA'))

    def test_wavstar(self):
        d = doc('wavstar_kqki.txt')        # KQKI, Captain Higgins, bought direct
        self.assertEqual((d['gross'], d['order_no'], d['agency']), (1996.0, 'C00208524', None))

    def test_on_air_schedule(self):
        d = doc('schedule_krvv.txt')       # KRVV, scanned
        self.assertEqual((d['gross'], d['net']), (225.0, 191.25))
        self.assertEqual(d['agency'], 'MOBILE COMMUNICATIONS SERVICES')

    def test_schedule_holding_another_clients_order(self):
        # Alvin Sharp's $600, bought direct, and a DA candidate's $120 in one file.
        d = doc('schedule_kmlb.txt')
        self.assertEqual((d['gross'], d['advertiser'], d['agency']), (600.0, 'ALVIN SHARP', None))


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


class Names(unittest.TestCase):
    def test_billing_words_are_not_names(self):
        # A scanned KTBS contract's billing columns, read into the buyer's place.
        from documents import clean
        for junk in ['Cash', 'EOM/EOC', 'EOM/EOC Calendar', 't vf']:
            self.assertIsNone(clean(junk), junk)

    def test_phone_number_after_a_name(self):
        from documents import clean
        self.assertEqual(clean('Arsement Media Group 501-9900'), 'Arsement Media Group')
        self.assertEqual(clean('Smart Media Group (225) 555-0100'), 'Smart Media Group')

    def test_short_ocr_debris(self):
        from documents import clean
        self.assertEqual(clean('FlexPoint Media t'), 'FlexPoint Media')
        self.assertEqual(clean('Media Ad Ventures, Inc Ht'), 'Media Ad Ventures, Inc')
        self.assertEqual(clean('Electric Symphony Media Ht'), 'Electric Symphony Media')
        self.assertEqual(clean('Smith & Co'), 'Smith & Co')
        self.assertEqual(clean('Citizens for a Better LA'), 'Citizens for a Better LA')

    def test_a_candidate_is_not_an_agency(self):
        from documents import agency_of
        text = 'Contract Agreement Between:\n\nAnd:\n           Roche/D/Judge\n'
        self.assertIsNone(agency_of(text, 'contract', None))
        text = 'Contract Agreement Between:\n\nAnd:\n           Friends of Gaddo (D) if\n'
        self.assertIsNone(agency_of(text, 'contract', None))

    def test_ocr_debris_after_a_name(self):
        from documents import clean
        self.assertEqual(clean('Crossroads Media LLC H£'), 'Crossroads Media LLC')
        self.assertEqual(clean('Media Ad Ventures, Inc ##'), 'Media Ad Ventures, Inc')
        self.assertEqual(clean('AT&T Ad Works'), 'AT&T Ad Works')
        self.assertEqual(clean("Bull's Eye Media"), "Bull's Eye Media")


class AgencyNames(unittest.TestCase):
    def test_spellings_join(self):
        for a, b in [('Media Ad Ventures (MAV)', 'MAV LLC'), ('Media Ad Ventures, Inc', 'MEDIA AD VENTURES'),
                     ('Flexpoint Campaigns', 'FLEXPOINT MEDIA INC.'), ('AxMedia', 'AX MEDIA LLC'),
                     ('Arsement Media', 'ARSEMENT MEDIA GROUP. LLC'),
                     ('Louisiana Radio Network', 'KINGFISH COMMUNICATIONS D/B/A LOUISIANA RADIO NETWORK')]:
            self.assertTrue(same_agency(agency_key(a), agency_key(b)), (a, b))

    def test_consulting_and_consultants(self):
        self.assertEqual(agency_key('Littlefield Consulting'), agency_key('LITTLEFIELD CONSULTANTS, LLC'))

    def test_short_keys_need_an_exact_match(self):
        self.assertFalse(same_agency(agency_key('ESM'), agency_key('ESM Productions')))
        self.assertTrue(same_agency(agency_key('Angie Sanders'), agency_key('Angie Sanders Ad Group, LLC')))


class Speed(unittest.TestCase):
    """Scanned rows of digits that a pattern could split many ways took
    minutes to parse, and stalled the nightly reader past its limit."""
    def test_long_digit_rows_parse_at_once(self):
        import time
        from documents import clean
        text = open(os.path.join(ROOT, 'tests', 'documents', 'ocr_contract_ktbs.txt'), encoding='utf-8').read()
        t = time.time()
        parse(text + '\nTotals ' + '1' * 60 + ' x\n')
        clean('Smart Media ' + '1 2' * 60 + ' x')
        self.assertLess(time.time() - t, 2)


class Retries(unittest.TestCase):
    """A stall or failed download is tried once more, two days on; nothing
    else is ever downloaded twice."""
    def test_once_more_after_two_days(self):
        from read_documents import retry_due
        cutoff = '2026-10-20'
        self.assertTrue(retry_due({'status': 'too_slow', 'read_at': '2026-10-20T16:10:00Z'}, cutoff))
        self.assertTrue(retry_due({'status': 'failed', 'read_at': '2026-10-19T16:10:00Z'}, cutoff))
        self.assertFalse(retry_due({'status': 'too_slow', 'read_at': '2026-10-21T16:10:00Z'}, cutoff))
        self.assertFalse(retry_due({'status': 'too_slow', 'tries': 2, 'read_at': '2026-10-01'}, cutoff))
        for status in ('read', 'scan', 'too_big', 'not_pdf'):
            self.assertFalse(retry_due({'status': status, 'read_at': '2026-10-01'}, cutoff), status)


class Booked(unittest.TestCase):
    """A buyer's dollars: each station order once, invoices only for an
    order not read, a reissued invoice never twice."""
    def row(self, i, up, call='WDSU', m='tv'):
        return {'id': i, 'up': up, 'call': call, 'm': m, 'fname': i}

    def test_revisions_and_invoices(self):
        docs = {
            'o1': {'status': 'read', 'kind': 'order', 'order_no': '100', 'gross': 1000.0, 'agency': 'SRCP Media Inc'},
            'o1r': {'status': 'read', 'kind': 'order', 'order_no': '100', 'gross': 1500.0},     # its revision
            'i1': {'status': 'read', 'kind': 'invoice', 'order_no': '100', 'invoice_no': '100-1', 'gross': 900.0},
            'i2': {'status': 'read', 'kind': 'invoice', 'order_no': '200', 'invoice_no': '200-1', 'gross': 300.0},
            'i2x': {'status': 'read', 'kind': 'invoice', 'order_no': '200', 'invoice_no': '200-1', 'gross': 300.0,
                    'reissue': True},
            'n': {'status': 'read', 'kind': 'request', 'gross': None, 'agency': 'SRCP MEDIA'},
        }
        rs = [self.row('o1', '2026-04-01'), self.row('o1r', '2026-04-09'), self.row('i1', '2026-04-20'),
              self.row('i2', '2026-05-01'), self.row('i2x', '2026-05-02'), self.row('n', '2026-03-30'),
              self.row('unread', '2026-05-03')]
        b = booked(rs, docs)
        self.assertEqual(b['usd'], 1800)          # order 100 at its revision, order 200 by invoice
        self.assertEqual((b['ordered'], b['invoiced']), (1500, 1200))
        self.assertEqual(b['read'], 6)
        self.assertEqual(b['ag'], ['SRCP Media Inc'])

    def test_radio_order_filed_at_two_stations(self):
        docs = {'a': {'status': 'read', 'kind': 'order', 'order_no': '9001395062', 'gross': 13050.0},
                'b': {'status': 'read', 'kind': 'order', 'order_no': '9001395062', 'gross': 13050.0}}
        rs = [self.row('a', '2026-09-29', 'WYNK', 'radio'), self.row('b', '2026-09-29', 'KRVE', 'radio')]
        self.assertEqual(booked(rs, docs)['usd'], 13050)

    def test_nothing_read(self):
        self.assertIsNone(booked([self.row('x', '2026-01-01')], {}))


if __name__ == '__main__':
    unittest.main()
