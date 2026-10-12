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
    # (KPXJ's sub-channel ones carry a version: "PB - 63687v1")
    r'(orders?|pb|nab|invoices?|contracts?)\s*[-#]?\s*\d+.*|'
    # a sub-channel folder under a buyer: "NLFY - CW", "KPXJ - ION"
    r'[a-z]{3,4}\s*-\s*(cw|my\w*|ion|me\w*|antenna|bounce)'
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


# Flight dates written into a document's name: "10-5 to 10-18",
# "4-27 thru 5-1-26", "5.22-5.26", "10.12.26 thru 10.18.26".
_D = r'(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2}|\d{4}))?'
FLIGHT = re.compile(r'(?<![\d#])' + _D + r'\s*(?:-|–|thru|through|to)\s*' + _D + r'(?!\d)', re.I)
REVISED = re.compile(r'\brev(?:ised|ision)?\b|\brev\s*\d|\br\d{1,2}[./]\d{1,2}', re.I)


def flight(name, year):
    """(start, end) ISO dates of the flight a document's name gives, in the
    political-file folder's `year` unless the name says otherwise; None
    when it gives none, or gives one that can't be a flight (backwards, or
    longer than ~four months)."""
    from datetime import date
    m = FLIGHT.search(name or '')
    if not m:
        return None
    m1, d1, y1, m2, d2, y2 = m.groups()
    yr = lambda y: int(y) + 2000 if y and len(y) == 2 else int(y) if y else None
    y2 = yr(y2) or yr(y1) or int(year)
    y1 = yr(y1) or (y2 - 1 if int(m1) > int(m2) else y2)
    try:
        a, b = date(y1, int(m1), int(d1)), date(y2, int(m2), int(d2))
    except ValueError:
        return None
    if not 0 <= (b - a).days <= 120:
        return None
    return a.isoformat(), b.isoformat()


def revised(name):
    """Whether a document's name marks it a revision of an earlier one."""
    return bool(REVISED.search(name or ''))


def buyer_folder(path):
    """The path of the buyer's own folder: `path` without trailing
    document-type folders ("…/Bill Cassidy/Orders" -> "…/Bill Cassidy")."""
    parts = [p for p in path.split('/')]
    while len(parts) > 3 and DOC_FOLDERS.match(parts[-1].strip()):
        parts.pop()
    return '/'.join(parts)


def fcc_url(profile, path, folder_id):
    """The FCC site's own link to a folder: the profile ("tv-profile/wdsu",
    "cable-profile/002460"), the path below "Political Files", each folder
    name slugged, then the folder's id, e.g.
    /tv-profile/wdsu/political-files/2026/federal/us-senate/bill-cassidy/<id>.
    The id alone decides the page (a wrong slug still resolves, checked
    against the live site), so the slug is cosmetic and never breaks a link."""
    segs = [re.sub(r'[^a-z0-9]+', '-', p.lower()).strip('-') for p in path.split('/')[1:]]
    return f"https://publicfiles.fcc.gov/{profile}/political-files/{'/'.join(segs)}/{folder_id}"


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
                    r'friends of|people for|victory fund)\b')


# Station misspellings of a buyer, folded by hand: a spelling slip like this
# makes a bare surname ambiguous ("letlow" -> julia or julie?), so the
# conservative merge rule below would otherwise keep them apart. Each entry is
# an editorial call, listed so it can be audited.
ALIASES = {
    'julie letlow': 'julia letlow',
    # Public Service Commission, District 5: KNOE files him with his middle
    # initial, KTAL and KSLA without.
    'john e atkins': 'john atkins',
    # Spelling slips in Lake Charles file names (KPLC, KVHP).
    'accountablility project': 'accountability project',
    'loisiana freedom fund': 'louisiana freedom fund',
    'john flemming': 'john fleming',
    # The new stations of October 2026 (KTBS, WVLA, WAFB, WNTZ, KADN).
    'mike johson': 'mike johnson',
    'blake miquez': 'blake miguez',
    'rick edmunds': 'rick edmonds',
    'kristain earles': 'kristian earles',
    # The same congressional candidates under their short and full names.
    'mike echols': 'michael echols',
    'michael gabriel firment': 'gabe firment',
    'mike marsiglia': 'michael marsiglia',
}


OFFICE_WORDS = (r'court|judge|justice|senate|senator|house|congress|council|board|attorney|da|'
                r'sheriff|mayor|assessor|clerk|commission\w*|commissioner|district|dist|sentate|'
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
# ...or just appended, after a full name: "Don Landry DA 15 Judicial District of LA",
# "Emilia Pardo LA City Court Judge D".
OFFICE_TAIL = re.compile(
    r'^(\S+\s+\S+(?:\s+\S+)??)\s+(?:(?:la|louisiana|us|tx)\s+)?'
    r'(?:district judge|district attorney|city court|judge|da|ag|sheriff|mayor|congress)\b.*$', re.I)
# "Texans for Greg Abbott", "Citizens for…": the supporters, not the buyer's name.
SUPPORTERS = re.compile(r'^(texans|arkansans|louisianans|louisianians|citizens|people|friends)\s+for\s+', re.I)
CHANNEL = re.compile(r'\s*-\s*(cw|my\w*|ion)\s*$', re.I)


# Some stations (KPLC and KVHP in Lake Charles) make no buyer folders: the
# documents sit in the office folder and only the file name says who bought
# ("Mike Johnson 10.12.26 thru 10.18.26", "BILL CASSIDY FOR US SENATE KVHP
# 4378339 INVOICE"). For those, the buyer is read from the name.
DOC_LEAD = re.compile(r'^(?:(?:nab|update|revised|contract|order|invoice|new creative|political)'
                      r'\b[\s\-\u2013:.]*)+', re.I)
DOC_TAIL = re.compile(r"\b(?:nab|invoice|order|contract|revised|network buy|est|spot|rec'?v?d|update|"
                      r"new creative|creative|fpm|pb\s*-?\d+|flight|notice|no charge|\d+\s*sec)\b.*$", re.I)
FIRST_DATE = re.compile(r'\s\d|\d{1,2}[./-]\d|#')


def buyer_from_filename(name, calls=()):
    """A buyer's name read from a document name, or None if nothing sensible
    is left once the dates, order numbers and document words are removed.
    `calls` are station call signs to strip ("KVHP", its sister "MVHP")."""
    t = re.sub(r'_+', ' ', name).strip()
    t = re.sub(r'^pol(?:itical)?\s*-\s*', '', t, flags=re.I)       # KLFY: "Pol-Louisiana Freedom Fund_…"
    t = DOC_LEAD.sub('', t)
    t = FIRST_DATE.split(t, 1)[0]
    for c in calls:
        t = re.sub(r'\b' + re.escape(c) + r'\b', ' ', t, flags=re.I)
    t = DOC_TAIL.sub('', t)
    t = re.sub(r'[\s\-\u2013,.:]+$', '', re.sub(r'\s+', ' ', t)).strip()
    return t if len(re.sub(r'[^A-Za-z]', '', t)) >= 3 else None


def clean_name(buyer, issue=False):
    """A buyer's name without the office, party or channel a station wrote
    onto it, case kept: "Don Landry - District Attorney" -> "Don Landry",
    "Cassidy-R for US Senate" -> "Cassidy", "Gabe Firment for Congress" ->
    "Gabe Firment". An issue group keeps its name whole ("Citizens for
    Louisiana" names the group, not a race) but loses a sub-channel tag."""
    if issue:
        return re.sub(r'\s+campaign$', '', CHANNEL.sub('', buyer), flags=re.I).strip() or buyer
    k = re.sub(r'-\s*[RDI]\b.*$', '', buyer, flags=re.I) if re.search(r'-\s*[RDI]\b', buyer) else buyer
    k = CHANNEL.sub('', k)
    k = re.sub(r'^pol(?:itical)?\s*-\s*', '', k, flags=re.I)     # KLFY: "Pol- James Klock"
    prev = None
    while prev != k:
        prev, k = k, OFFICE_SUFFIX.sub('', k)
    k = FOR_OFFICE.sub('', k)
    k = OFFICE_TAIL.sub(r'\1', k)
    k = re.sub(r'\s+campaign$', '', re.sub(r'^the\s+', '', k.strip(), flags=re.I), flags=re.I)
    k = re.sub(r'\b(\w+)\s+\1\b', r'\1', k, flags=re.I)     # KPLC: "Ron Richard Richard"
    return k.strip() or buyer


def buyer_key(buyer, alias=True):
    """Lower-case, punctuation-free, filler-free form of a buyer's name, so
    the same buyer filed differently at two stations groups together. A
    middle initial is dropped ("Sherman Q Mack" -> "sherman mack");
    `alias=False` skips the hand-made ALIASES."""
    k = SUPPORTERS.sub('', clean_name(buyer))
    k = FILLER.sub(' ', k.lower())
    k = re.sub(r'[^a-z0-9 ]', ' ', k)
    k = re.sub(r'\s+', ' ', k).strip()
    w = k.split()
    if len(w) == 3 and len(w[1]) == 1:
        k = f'{w[0]} {w[2]}'
    return ALIASES.get(k, k) if alias else k


KEEP_CAPS = {'US', 'LA', 'PAC', 'DA', 'JP', 'II', 'III', 'TX', 'AR', 'MS', 'LLC'}


def tidy_caps(name):
    """Title-case a name a station typed in capitals ("CAMILLE BURAS")."""
    if not name or not name.isupper():
        return name
    return re.sub(r"[A-Z][A-Z'.]*", lambda m: m.group(0) if m.group(0) in KEEP_CAPS
                  else m.group(0).capitalize(), name)


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


# ── matching a political-file buyer to its state filer ───────────────────────
# Stations write the name a campaign goes by ("Don Landry", "Tom Arceneaux");
# the Ethics filings carry the legal one ("Donald D. Landry",
# 'M. Thomas ("Tom") Arceneaux'). Both reduce to a first name, spelled out,
# and a surname.
NICKNAMES = {
    'al': 'albert', 'andy': 'andrew', 'ben': 'benjamin', 'bill': 'william',
    'billy': 'william', 'bob': 'robert', 'bobby': 'robert', 'chris': 'christopher',
    'dan': 'daniel', 'danny': 'daniel', 'dave': 'david', 'don': 'donald',
    'ed': 'edward', 'greg': 'gregory', 'jeff': 'jeffrey', 'jim': 'james',
    'jimmy': 'james', 'joe': 'joseph', 'ken': 'kenneth', 'larry': 'lawrence',
    'matt': 'matthew', 'mike': 'michael', 'pat': 'patrick', 'rick': 'richard',
    'rob': 'robert', 'ron': 'ronald', 'sal': 'salvatore', 'sam': 'samuel',
    'steve': 'stephen', 'tim': 'timothy', 'tom': 'thomas', 'tony': 'anthony',
    'will': 'william', 'liz': 'elizabeth', 'beth': 'elizabeth', 'betty': 'elizabeth',
    'kathy': 'katherine', 'jen': 'jennifer', 'nick': 'nicholas', 'charlie': 'charles',
    'chuck': 'charles', 'johnny': 'john', 'tommy': 'thomas',
}
SUFFIX = re.compile(r',?\s+(jr|sr|ii|iii|iv)\.?$', re.I)


def person_keys(name):
    """Keys a person's name can be matched on: the full buyer key, and
    first + last name with the first name spelled out. A parenthesized
    nickname ('M. Thomas ("Tom") Arceneaux') yields keys for both."""
    forms = {name}
    m = re.match(r'^(.*?)\s*\(\s*["“]?([^)"”]+)["”]?\s*\)\s*(.*)$', name)
    if m:
        before, nick, after = m.groups()
        forms |= {f'{before} {after}', f'{nick} {after}'}
    keys = set()
    for f in forms:
        k = buyer_key(SUFFIX.sub('', f.strip()))
        if not k:
            continue
        keys.add(k)
        w = [x for x in k.split() if len(x) > 1]       # initials out
        if len(w) >= 2:
            keys.add(f'{NICKNAMES.get(w[0], w[0])} {w[-1]}')
    return keys


def group_key(name):
    """A PAC's or issue group's name for matching: the whole name, losing only
    corporate words, so "Louisiana First Victory Fund" never matches
    "Louisiana First PAC"."""
    k = re.sub(r'[^a-z0-9 ]', ' ', CHANNEL.sub('', name).lower())
    return 'org:' + ' '.join(w for w in k.split() if w not in ('inc', 'llc', 'the', 'pac'))


def filer_index(filers):
    """key -> set of filer numbers, over {filer: {'n': name, ...}}."""
    idx = {}
    for fn, rec in filers.items():
        for k in person_keys(rec['n']) | {group_key(rec['n'])}:
            idx.setdefault(k, set()).add(fn)
    return idx


def match_filer(names, idx, person=True):
    """The one filer every spelling in `names` that matches at all points
    to, or None. A key shared by two filers (two Mike Echolses) is no match.
    Issue groups (`person=False`) match on their full name only."""
    found = set()
    for n in names:
        keys = person_keys(n) if person else {group_key(n)}
        for k in keys:
            hit = idx.get(k, set())
            if len(hit) == 1:
                found |= hit
            elif len(hit) > 1:
                return None
    return found.pop() if len(found) == 1 else None
