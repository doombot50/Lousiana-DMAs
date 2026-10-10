"""
normalize.py — turn a station's political-file folder path into level / office / buyer
================================================================================
Every station files its political documents under "Political Files/<year>/",
then a level folder the FCC prescribes (Federal, State, Local, Non-Candidate
Issue Ads), but below that each sales office improvises:

    Political Files/2026/Federal/US Senate/Bill Cassidy                      WDSU
    Political Files/2026/Federal/US Senate/Cassidy-R for US Senate/Orders   WWL-TV
    Political Files/2026/Local/Louisiana State Supreme Court District 1/Blair Downing Edwards
    Political Files/2026/Non-Candidate Issue Ads/Accountability Project Inc  Del Cielo Media

So: drop trailing document-type folders (Orders, Invoices, NAB forms…); the
last folder left is the buyer, anything between level and buyer is the
office. A path that stops at an office ("…/Federal/US Senate") has no buyer
folder and is reported as such rather than guessed at.
"""
import re

LEVELS = {
    'federal': 'Federal', 'state': 'State', 'local': 'Local',
    'non-candidate issue ads': 'Issue', 'non candidate issue ads': 'Issue',
    'issue ads': 'Issue', 'non-candidate': 'Issue',
}
# Folders that sort documents by kind rather than naming who bought.
DOC_FOLDERS = re.compile(
    r'^(orders?|invoices?|contracts?|nab( forms?)?|pb-?18|agreements?|requests?|'
    r'disclosures?|logs?|as ?run|affidavits?|makegoods?|make goods|revisions?|'
    r'cancell?ations?|political (orders?|invoices?)|\d{4})$', re.I)
# Offices are named by the race, not the buyer, so a leaf that reads like one
# means the station filed at the office level.
OFFICE_HINT = re.compile(
    r'^(us |u\.s\. )?(senate|house|congress)|^(president|governor|lt\.? governor|'
    r'attorney general|secretary of state|mayor|sheriff|district attorney|'
    r'city council|parish council|school board|board of elem)', re.I)


def classify(name, path):
    """What kind of document this is, from its name and folder."""
    t = f'{path} {name}'.lower()
    if re.search(r'\bnab\b|pb-?18|agreement form', t):
        return 'request'          # NAB PB-18: the buyer's request for time
    if re.search(r'invoice|\binv\b|billing|affidavit', t):
        return 'invoice'          # time that aired, billed
    # Flight dates ("10-12 to 10-18") or a sales-system order number
    # ("WWL McMahon 3348118") both mark an order for time.
    if re.search(r'order|contract|\bbuy\b|schedule|\d{1,2}-\d{1,2} ?(to|-) ?\d{1,2}-\d{1,2}'
                 r'|#?\b\d{6,8}\b', t):
        return 'order'
    return 'other'


def parse_path(path):
    """('Federal', 'US Senate', 'Bill Cassidy') from a political-file path."""
    parts = [p.strip() for p in path.split('/') if p.strip()]
    # Political Files / <year> / <level> / ...
    if len(parts) < 3:
        return None, None, None
    level = LEVELS.get(parts[2].lower(), parts[2])
    rest = parts[3:]
    while rest and DOC_FOLDERS.match(rest[-1]):
        rest.pop()
    if not rest:
        return level, None, None
    if len(rest) == 1 and OFFICE_HINT.search(rest[0]):
        return level, rest[0], None
    buyer = rest[-1]
    office = ' / '.join(rest[:-1]) or None
    return level, office, buyer


FILLER = re.compile(r'\b(inc|llc|pac|the|committee to elect|campaign|for|of|to|elect|'
                    r'friends of|people for)\b')


def buyer_key(buyer):
    """Lower-case, punctuation-free, filler-free form of a buyer's name.
    Station shorthand like "Cassidy-R for US Senate" also loses its party
    suffix and office ("-R for US Senate" -> "cassidy")."""
    k = re.sub(r'-\s*[RDI]\b.*$', '', buyer, flags=re.I) if re.search(r'-\s*[RDI]\b', buyer) else buyer
    k = FILLER.sub(' ', k.lower())
    k = re.sub(r'[^a-z0-9 ]', ' ', k)
    return re.sub(r'\s+', ' ', k).strip()


def bucket(level):
    """Stations disagree on State vs Local for the same race (one files the
    Supreme Court race under State, another under Local), so the two are
    grouped together; Federal and issue ads stay apart."""
    return {'Federal': 'Federal', 'Issue': 'Issue'}.get(level, 'State & local')


def aliases(keys_by_bucket):
    """Map each buyer key to the key it merges into, per bucket.

    Deliberately conservative, because a false merge puts one candidate's
    buys under another's name:
      * a multi-word name merges only with an identical name — "john young"
        and "john paul young" are different 2026 candidates;
      * a bare surname (station shorthand, "cassidy") merges with a full name
        only when exactly one full name in the bucket ends in that surname;
      * an issue group merges into a shorter name it starts with
        ("accountability project del cielo media" -> "accountability project").
    """
    out = {}
    for b, keys in keys_by_bucket.items():
        multi = [k for k in keys if len(k.split()) > 1]
        for k in keys:
            target = k
            if b == 'Issue':
                pre = [m for m in keys if m != k and k.startswith(m + ' ')]
                if pre:
                    target = min(pre, key=len)
            elif len(k.split()) == 1:
                full = [m for m in multi if m.split()[-1] == k]
                if len(full) == 1:
                    target = full[0]
            out[(b, k)] = target
    return out
