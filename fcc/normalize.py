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
    r'^(orders?|invoices?|contracts?|nab( forms?)?|pb-?\d{1,2}|agreements?|requests?|'
    r'disclosures?|logs?|as ?run|affidavits?|makegoods?|make goods|revisions?|'
    r'cancell?ations?|political (orders?|invoices?)|\d{4}|notices?|'
    # one folder per document, as KPXJ files them: "Order - 20228 REV 1", "PB - 19990"
    r'(orders?|pb|nab|invoices?|contracts?)\s*[-#]?\s*\d+\b.*|'
    # a sub-channel folder under a buyer: "NLFY - CW"
    r'[kw][a-z]{2,3}\s*-\s*(cw|my\w*|ion|me\w*|antenna|bounce)'
    r')$', re.I)

# Shreveport's market reaches East Texas and Monroe-El Dorado's southern
# Arkansas, and network sub-channels carry national issue buys, so a
# Louisiana station's file holds other states' races. They are named by the
# state somewhere in the path ("TX Governor/Texans for Greg Abbott",
# "Dan Patrick-Lieutenant Governor-Texas", "Californians For Voter ID - CW").
# Washington is left out: Washington Parish is in Louisiana.
STATES = ('Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware '
          'Florida Georgia Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky Maine '
          'Maryland Massachusetts Michigan Minnesota Mississippi Missouri Montana '
          'Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah '
          'Vermont Virginia Wisconsin Wyoming').split() + [
          'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina',
          'North Dakota', 'South Carolina', 'South Dakota', 'Rhode Island', 'West Virginia',
          'Washington State']
DEMONYMS = {'texan': 'Texas', 'arkansan': 'Arkansas', 'mississippian': 'Mississippi',
            'alabamian': 'Alabama', 'oklahoman': 'Oklahoma', 'floridian': 'Florida',
            'californian': 'California', 'tennessean': 'Tennessee', 'georgian': 'Georgia',
            'lone star': 'Texas'}
STATE_WORD = re.compile(
    r'\b(?:(' + '|'.join(re.escape(x) for x in STATES) + r')s?|'
    r'(' + '|'.join(DEMONYMS) + r')s?)\b', re.I)
# Neighbours' postal codes, matched only as capitals: "TX Governor", "MS Senate".
STATE_CODE = re.compile(r'\b(TX|AR|MS)\b')
CODE = {'TX': 'Texas', 'AR': 'Arkansas', 'MS': 'Mississippi'}


# Names that contain a state but aren't another state's race.
NOT_A_STATE = re.compile(r'georgia[- ]pacific', re.I)


def out_of_state(path):
    """The other state a political-file path names below its level folder, or None."""
    below = NOT_A_STATE.sub('', '/'.join(path.split('/')[3:]))
    m = STATE_WORD.search(below)
    if m:
        if m.group(2):
            return DEMONYMS[m.group(2).lower()]
        return m.group(1).title().replace('Washington State', 'Washington')
    m = STATE_CODE.search(below)
    return CODE[m.group(1)] if m else None
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


def buyer_folder(path):
    """The path of the buyer's own folder: `path` without trailing
    document-type folders ("…/Bill Cassidy/Orders" -> "…/Bill Cassidy")."""
    parts = [p for p in path.split('/')]
    while len(parts) > 3 and DOC_FOLDERS.match(parts[-1].strip()):
        parts.pop()
    return '/'.join(parts)


def fcc_url(slug, path, folder_id):
    """The FCC site's own link to a folder: the path below "Political Files",
    each folder name slugged, then the folder's id, e.g.
    /tv-profile/wdsu/political-files/2026/federal/us-senate/bill-cassidy/<id>.
    The id alone decides the page (a wrong slug still resolves, checked
    against the live site), so the slug is cosmetic and never breaks a link."""
    segs = [re.sub(r'[^a-z0-9]+', '-', p.lower()).strip('-') for p in path.split('/')[1:]]
    return f"https://publicfiles.fcc.gov/tv-profile/{slug}/political-files/{'/'.join(segs)}/{folder_id}"


def parse_path(path):
    """('Federal', 'US Senate', 'Bill Cassidy') from a political-file path."""
    parts = [p.strip() for p in path.split('/') if p.strip()]
    # Political Files / <year> / <level> / ...
    if len(parts) < 3:
        return None, None, None
    # Only the FCC's four levels hold buys; stations also keep housekeeping
    # folders here ("Terms and Disclosures") that name no race or buyer.
    level = LEVELS.get(parts[2].lower())
    if not level:
        return None, None, None
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


# Station misspellings of a buyer, folded by hand: a spelling slip like this
# makes a bare surname ambiguous ("letlow" -> julia or julie?), so the
# conservative merge rule below would otherwise keep them apart. Each entry is
# an editorial call, listed so it can be audited.
ALIASES = {
    'julie letlow': 'julia letlow',
    # Public Service Commission, District 5: KNOE files him with his middle
    # initial, KTAL and KSLA without.
    'john e atkins': 'john atkins',
}


OFFICE_WORDS = (r'court|judge|justice|senate|senator|house|congress|council|board|attorney|da|'
                r'sheriff|mayor|assessor|clerk|commission\w*|commissioner|district|dist|'
                r'governor|parish|representative|rep|comptroller|judicial')
PLACE_WORDS = r'louisiana|la|united states|us|u\.s\.|texas|tx|arkansas|mississippi'
# An office (or the state) written onto the name after a hyphen, repeated:
# "Mike Johnson- US House - Louisiana", "…Edwards-LA Supreme Court".
OFFICE_SUFFIX = re.compile(
    r'\s*-\s*(?:[^-]*\b(?:' + OFFICE_WORDS + r')\b[^-]*|\s*(?:' + PLACE_WORDS + r')\s*)$', re.I)
# ...or after "for": "Julia Letlow for US Senate", "Mike Johnson for Louisiana",
# "Committee to elect David Way for District Judge".
FOR_OFFICE = re.compile(
    r'\s+for\s+(?:.*\b(?:' + OFFICE_WORDS + r')\b.*|(?:' + PLACE_WORDS + r'))$', re.I)
# ...or just appended, after a full name: "Don Landry DA 15 Judicial District of LA".
OFFICE_TAIL = re.compile(
    r'^(\S+\s+\S+(?:\s+\S+)??)\s+(?:district judge|district attorney|judge|da|sheriff|mayor)\b.*$', re.I)
# "Texans for Greg Abbott", "Citizens for…": the supporters, not the buyer's name.
SUPPORTERS = re.compile(r'^(texans|arkansans|louisianans|louisianians|citizens|people|friends)\s+for\s+', re.I)
CHANNEL = re.compile(r'\s*-\s*(cw|my\w*|ion)\s*$', re.I)


def buyer_key(buyer):
    """Lower-case, punctuation-free, filler-free form of a buyer's name.
    Station shorthand like "Cassidy-R for US Senate" also loses its party
    suffix and office ("-R for US Senate" -> "cassidy")."""
    k = re.sub(r'-\s*[RDI]\b.*$', '', buyer, flags=re.I) if re.search(r'-\s*[RDI]\b', buyer) else buyer
    # ...and an office written onto the name after a hyphen
    # ("…Blair Downing Edwards-LA Supreme Court", "Hillar Moore- District Attorney").
    k = CHANNEL.sub('', k)
    k = SUPPORTERS.sub('', k)
    prev = None
    while prev != k:
        prev, k = k, OFFICE_SUFFIX.sub('', k)
    k = FOR_OFFICE.sub('', k)
    k = OFFICE_TAIL.sub(r'\1', k)
    k = FILLER.sub(' ', k.lower())
    k = re.sub(r'[^a-z0-9 ]', ' ', k)
    k = re.sub(r'\s+', ' ', k).strip()
    return ALIASES.get(k, k)


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
