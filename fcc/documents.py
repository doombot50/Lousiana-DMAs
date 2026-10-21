"""
documents.py — what a political-file document's text says
================================================================================
The stations' orders, contracts and invoices come out of a handful of sales
systems, and each lays its page out its own way. pdftotext -layout keeps the
columns, so each is read by where its labels sit:

  WideOrbit order     "Order / Rev: 4348571" … "Agency  Name: Kingfish Communications LLC"
                      and a bill plan whose "Totals  4  $2,900.00  $2,465.00" row
                      is the order's gross and net (KALB, KADN, KTAL, WNTZ…)
  WideOrbit contract  "Contract Agreement Between:" the station "And:" the buyer,
                      whose name is the first line under "And:"; totals at the end,
                      "Totals  12  $2,150.00  ($322.50)  $1,827.50" (WDSU, KARD, KTBS)
  WideOrbit invoice   "Billing Address:" then who is billed (the agency, or the
                      advertiser when it buys direct); "Gross Total  $65,400.00"
  KLAX's contract     "Agency  Armada Strategies (1880)", "Grand Total:  25  $5,560.00"
  NAB PB-18/PB-19     the request form: "Agency name: Del Cielo Media LLC", or
                      "Agency requesting time (and contact information):" with the
                      answer on the next line; no amounts

Scans are read by OCR (fcc/read_documents.py), which misreads a little
("$50,00", "Agancy"); the patterns allow for the slips seen in real scans.
Every case here is a real document, in tests/documents/.

parse() never guesses: a field it can't find is None.
"""
import re

# ---------------------------------------------------------------- amounts

# "$1,234.50", "1234.50", OCR's "$50,00"; parenthesised is negative.
AMT = r'\(?\$?\s?\d{1,3}(?:,\d{3})*(?:[.,]\d{2})\)?|\(?\$?\s?\d+[.,]\d{2}\)?'


def amount(s):
    """'$1,234.50' -> 1234.5; '($499.50)' -> -499.5; '$50,00' (OCR) -> 50.0."""
    if s is None:
        return None
    s = s.strip()
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()').replace('$', '').replace(' ', '')
    if re.search(r',\d{2}$', s):          # an OCR'd decimal comma
        s = s[:-3] + '.' + s[-2:]
    s = s.replace(',', '')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


# A totals row: "Totals  4  $2,900.00  $2,465.00", "Totals  13  $3,330.00  ($499.50)  $2,830.50".
# The spot count comes first; amounts follow. OCR sometimes slips a rating in.
TOTALS_ROW = re.compile(r'^\s*Totals?\b[ \t:]+((?:[ \t]*(?:\(?\$?[\d,]+(?:\.\d{2})?\)?|[\d.]+))+)[ \t]*$', re.I | re.M)
GROSS_TOTAL = re.compile(r'(?:Gross\s+Total|Total\s+Gross(?:\s+Amount)?|Grand\s+Total)\s*:?\s+(?:\d{1,5}\s+)?(' + AMT + ')', re.I)
NET_TOTAL = re.compile(r'(?:Net\s+Amount\s+Due|Net\s+Total|Total\s+Net(?:\s+Amount)?)\s*:?\s+(' + AMT + ')', re.I)


def totals(text):
    """(gross, net) from the document's totals: the largest gross any totals
    row or labelled total gives, with the net printed beside it."""
    best = None
    for m in TOTALS_ROW.finditer(text):
        vals = re.findall(AMT, m.group(1))
        money = [amount(v) for v in vals if '$' in v or '(' in v]
        money = [v for v in money if v is not None]
        if not money:
            continue
        gross = money[0]
        rest = [v for v in money[1:] if v >= 0]
        net = rest[-1] if rest and rest[-1] <= gross else None
        if best is None or gross > best[0] or (gross == best[0] and best[1] is None):
            best = (gross, net)
    g = [amount(m.group(1)) for m in GROSS_TOTAL.finditer(text)]
    g = [v for v in g if v is not None]
    n = [amount(m.group(1)) for m in NET_TOTAL.finditer(text)]
    n = [v for v in n if v is not None]
    if g and (best is None or max(g) > best[0]):
        best = (max(g), None)
    if best and best[1] is None and n:
        cand = [v for v in n if v <= best[0]]
        best = (best[0], max(cand) if cand else None)
    return best or (None, None)


# ---------------------------------------------------------------- names

def chunk(s):
    """The first column of a layout line: text up to a run of 3+ spaces."""
    return re.split(r'\s{3,}', s.strip())[0].strip() if s and s.strip() else ''


def next_line(text, pos, left=None):
    """The first non-blank text after `pos`: its first column, or with `left`
    the first column that starts before character `left` of its line."""
    for line in text[pos:].split('\n')[1:12]:
        if not line.strip():
            continue
        if left is not None:
            lead = len(line) - len(line.lstrip())
            if lead >= left:
                continue
        return chunk(line)
    return ''


def under(text, label):
    """The value printed beneath a column header: the text on the next line
    starting at the header's column ("Advertiser" on a WideOrbit contract)."""
    m = re.search(r'^(.*?)\b' + label + r'\b', text, re.M)
    if not m:
        return ''
    col = len(m.group(1))
    lines = text[m.end():].split('\n')[1:4]
    for line in lines:
        seg = line[max(0, col - 2):]
        if seg.strip():
            return chunk(seg)
    return ''


JUNK = re.compile(r'^(?:n/?a\b|none\b|tbd\b|same\b|self\b|direct\b)[\s,;:-]*', re.I)
# Not a name: a label or an address line that lands where a name should be.
NOT_NAME = re.compile(r'^(?:attention|attn|p\.?\s?o\.?\s+box|\d|address|contact|phone|email|'
                      r'billing|agency\b|advertiser\b|name\b|station|us$|comm|'
                      # a WideOrbit contract's billing columns, which OCR can run
                      # into the buyer's line ("Cash", "EOM/EOC Calendar")
                      r'cash\b|trade\b|eom\b|eoc\b|broadcast\b|calendar\b|property\b|'
                      r'account executive|sales office|special handling|demographic)', re.I)
# A candidate written the way stations file one ("Roche/D/Judge", "Friends
# of Gaddo (D)"): the advertiser itself, buying direct, not an agency.
PARTY_MARK = re.compile(r'/\s*[DRIL]\s*/|\(\s*[DRIL]\s*\)')
# Short words a name may end in; any other trailing token of one or two
# letters is OCR debris ("FlexPoint Media t", "Media Ad Ventures, Inc Ht").
SHORT_OK = {'LA', 'TV', 'US', 'II', 'IV', 'CO', 'JR', 'SR', 'PR', 'AD', 'MS', 'TX'}


def clean(name):
    """Tidy a name read off a document: drop sales-system codes ("(1880)"),
    OCR debris ("##"), N/A, and edge punctuation."""
    if not name:
        return None
    s = re.sub(r'\(\d{2,6}\)', '', name)
    s = re.sub(r'[#|_~*‘’"“”]+', ' ', s)
    s = JUNK.sub('', s.strip())
    s = re.sub(r'\s+', ' ', s).strip(' .,:;-/')
    # OCR debris trailing a name: a short token with a symbol or a
    # non-ASCII character ("Crossroads Media LLC H£").
    s = re.sub(r'(?:\s+(?=\S{0,3}(?:\s|$))\S*[^A-Za-z0-9\s.,&\'-]\S*)+$', '', s).strip(' .,:;-/')
    # A phone number or code run onto the name ("Arsement Media Group 501-9900").
    s = re.sub(r'(?:\s+\(?\d[\d\s().-]{3,}\d)+$', '', s).strip(' .,:;-/')
    while True:
        m = re.search(r'\s+([A-Za-z]{1,2})$', s)
        if not m or m.group(1).upper() in SHORT_OK:
            break
        s = s[:m.start()].rstrip(' .,:;-/')
    if len(s) < 3 or NOT_NAME.match(s) or not re.search(r'[A-Za-z]{2}', s):
        return None
    return s[:80]


def same_party(a, b):
    """Whether two names are one buyer, loosely: a bill-to that is the
    advertiser itself means the advertiser bought direct, with no agency."""
    k = lambda s: re.sub(r'[^a-z]', '', re.sub(r'^(?:pol|iss)\s*/', '', (s or '').lower()))[:12]
    return bool(a and b) and (k(a) in k(b) or k(b) in k(a))


# ---------------------------------------------------------------- one document

def layout(text):
    head = text[:4000]
    if re.search(r'agreement\s+form|PB-?1[6-9]\b|request(?:s|ing)?\s+station\s+time', head, re.I):
        return 'nab'
    if re.search(r'\bINVOICE\b', head) and re.search(r'Invoice\s*#', head):
        return 'invoice'
    if re.search(r'Contract\s+Agreement\s+Betw', head, re.I):
        return 'contract'
    if re.search(r'Order\s*/\s*Rev', head, re.I):
        return 'order'
    if re.search(r'Contract\s*#', head, re.I):
        return 'contract'
    if re.search(r'\bORDER\b|\bCONTRACT\b|Insertion\s+Order', head):
        return 'order'
    return 'other'


KIND = {'nab': 'request', 'invoice': 'invoice', 'contract': 'order', 'order': 'order', 'other': 'other'}


def search(pattern, text, flags=re.I | re.M):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _agency_of(text, lay, advertiser):
    if lay == 'order':
        a = search(r'^\s*Agency\s+Name:\s*(.+?)(?:\s{3,}|$)', text)
        if a:
            return clean(a)
    if lay == 'contract':
        m = re.search(r'^[ \t]*And:', text, re.M)
        if m:
            return clean(next_line(text, m.start(), left=60))
        a = search(r'(?:^|\s{2,})Agency\s{2,}(.+?)(?:\s{3,}|$)', text)
        if a:
            return clean(a)
    if lay == 'invoice':
        m = re.search(r'Billing\s+Address:', text)
        if m:
            # A name on the label's own line sits right after it; text far to
            # the right is the next column ("Sales Region").
            same = search(r'Billing\s+Address:[ \t]{0,3}(\S.+?)(?:\s{3,}|$)', text)
            who = clean(same if same and not re.match(r'P\.?\s?O|\d', same) else next_line(text, m.start(), left=60))
            return None if not who or same_party(who, advertiser) else who
    if lay == 'nab':
        for pat in (r'Agency\s+name:[ \t]*(.*)$', r'Station\s+time\s+requested\s+by:[ \t]*(.*)$'):
            m = re.search(pat, text, re.I | re.M)
            if m and clean(chunk(m.group(1))):
                return clean(chunk(m.group(1)))
        m = re.search(r'Agency\s+requesting\s+time[^\n]*', text, re.I)
        if m:
            return clean(next_line(text, m.start()))
    # Anything else (OCR'd orders from other systems): a labelled "Agency:".
    a = search(r'(?:^|\s{2,})Agency(?:\s+Name)?\s*:\s*(.+?)(?:\s{3,}|$)', text)
    return clean(a) if a else None


def agency_of(text, lay, advertiser):
    """The agency that placed the buy, or None: none named, or the name in
    the agency's place is the advertiser itself (a candidate as stations
    file one, "Roche/D/Judge"), which means it bought direct."""
    a = _agency_of(text, lay, advertiser)
    if not a or PARTY_MARK.search(a) or same_party(a, advertiser):
        return None
    return a


def advertiser_of(text, lay):
    if lay == 'order':
        return clean(search(r'^\s*Advertiser\s+Name:\s*(.+?)(?:\s{3,}|\s+Order Brand|$)', text))
    if lay == 'contract':
        # KLAX prints the value beside the label; WideOrbit beneath it.
        a = search(r'(?:^|\s{2,})Advertiser,?\s{2,}(.+?)(?:\s{3,}|$)', text)
        if not a or re.match(r'Original|Contract|Grand', a):
            a = under(text, 'Advertiser')
        if a and not re.match(r'Original|Contract|Grand', a):
            return clean(a)
    if lay == 'nab':
        m = re.search(r'Authorized\s+committee:[ \t]*(.*)$', text, re.I | re.M)
        if m:
            return clean(chunk(m.group(1)) or next_line(text, m.start()))
        m = re.search(r'Name\s+of\s+advertiser/sponsor', text, re.I)
        if m:
            return clean(search(r'^\s*Name:[ \t]*(.+?)(?:\s{3,}|$)', text[m.end():]))
    return clean(search(r'(?:^|\s{2,})Advertiser\s{2,}(.+?)(?:\s{3,}|$)', text))


def order_no_of(text, lay):
    if lay == 'order':
        return search(r'Order\s*/\s*Rev:?\s*(\d{4,10})', text)
    if lay == 'contract':
        m = re.search(r'Contract\s*/\s*Revision', text)
        if m:
            return search(r'(\d{5,10})\s*/', text[m.end():m.end() + 600])
        return search(r'Contract\s*#\s*(\d{4,10})', text)
    if lay == 'invoice':
        return search(r'Order\s*#\s+(\d{4,10}[A-Z]?)\b', text)
    return None


def parse(text):
    """What a document's text says: its kind (order, invoice, request,
    other), gross and net amounts, agency, advertiser, the station's order
    number and the invoice number. Fields it can't find are None."""
    lay = layout(text)
    adv = advertiser_of(text, lay)
    gross, net = totals(text) if lay != 'nab' else (None, None)
    fl = re.search(r'(?:Flight\s+Dates|Contract\s+Dates|Order\s+Flight)[: \t]*(?:\n\s*)?(\d\d/\d\d/\d\d)\s*-\s*(\d\d/\d\d/\d\d)', text, re.I)
    return {
        'kind': KIND[lay], 'layout': lay,
        'gross': gross, 'net': net,
        'agency': agency_of(text, lay, adv),
        'advertiser': adv,
        'order_no': order_no_of(text, lay),
        'invoice_no': search(r'Invoice\s*#\s+(\d{4,10}[A-Z]?-?\d{0,2})\b', text) if lay == 'invoice' else None,
        'flight': [fl.group(1), fl.group(2)] if fl else None,
        'reissue': bool(re.search(r'INVOICE\s+REISSUE|DUPLICATE\s+Invoice', text)) if lay == 'invoice' else None,
    }


# ---------------------------------------------------------------- agencies

# One agency, however a station or a committee's treasurer spells it. The
# key drops corporate suffixes, parentheticals and spacing ("Media Ad
# Ventures (MAV)", "MEDIA AD VENTURES, INC" -> MEDIAADVENTURES); ALIASES
# joins what the key can't: an acronym, a renamed or sister company. Each
# entry is a pairing seen in real documents.
SUFFIXES = re.compile(r'\b(?:L\s?L\s?C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PLLC|THE|GROUP|'
                      r'D\s?B\s?A\b.*)\b', re.I)
AGENCY_ALIASES = {
    'MAV': 'MEDIAADVENTURES',                 # KARD/KTVE bill "MAV LLC"; KPLC "Media Ad Ventures (MAV)"
    'FLEXPOINTCAMPAIGNS': 'FLEXPOINTMEDIA',   # Nexstar's orders vs. its invoices and the state filings
    'LOUISIANARADIONETWORK': 'KINGFISHCOMMUNICATIONS',  # filed "KINGFISH COMMUNICATIONS D/B/A LOUISIANA RADIO NETWORK"
}


def agency_key(name):
    """A spelling-proof key for an agency name; '' for none."""
    if not name:
        return ''
    s = re.sub(r'\([^)]*\)', ' ', name.upper())
    s = re.sub(r'[^A-Z0-9& ]', ' ', s.replace('&', ' AND '))
    s = SUFFIXES.sub(' ', s)
    s = re.sub(r'\bCONSULT(?:ING|ANTS?)\b', 'CONSULT', s)   # "Littlefield Consulting" / "Consultants"
    k = re.sub(r'[^A-Z0-9]', '', s)
    return AGENCY_ALIASES.get(k, k)


def same_agency(a, b):
    """Two keys for one agency: equal, or one a word-run prefix of the other
    at least ten letters long ("ANGIESANDERS" for "ANGIESANDERSAD")."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 10 and long_.startswith(short)
