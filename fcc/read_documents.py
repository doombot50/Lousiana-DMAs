#!/usr/bin/env python3
"""
read_documents.py — the dollars and agencies inside the political-file documents
================================================================================
scrape_political_files.py lists the documents in each station's political
file; this reads them. A station's order or invoice for political time
usually prints the gross amount, the agency that placed it and the
advertiser, so reading them turns "Bill Cassidy: 14 documents at WDSU" into
"Bill Cassidy: $412,000 ordered at WDSU through Smart Media Group", and gives
the federal races, which never appear in the state's filings, real numbers.

    python3 fcc/read_documents.py                      # tonight's TV batch
    python3 fcc/read_documents.py --media radio --budget 20
    python3 fcc/read_documents.py --sample 40          # print what a sample reads as

Each document is downloaded once, ever: what it read as is kept in
data/fcc_documents.json by its FCC file id, so a night spends its request
budget only on documents it hasn't read. The CDN that blocked the folder
scraper's first full run is just as touchy about downloads, so a night reads
few (--budget, default 40, more close to an election), newest orders first:

  1. orders, the latest revision of each order number at a station (an
     order's revisions restate the whole order, so only the last counts);
  2. documents the name doesn't type, which are mostly orders;
  3. one NAB request form per buyer at a station, for the agency;
  4. invoices, which say what aired rather than what was bought.

Text comes from poppler's `pdftotext -layout` (apt: poppler-utils). A scan
with no text layer is recorded as such and not retried. What a document
reads as (parse()) is regression-tested on real documents' text in
tests/test_documents.py; a document whose amount can't be found is kept with
`gross: null`, never guessed.

Must run where publicfiles.fcc.gov is reachable (GitHub Actions).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
D = lambda *p: os.path.join(ROOT, 'data', *p)

PARSER = 1            # bump when parse() changes, to re-parse kept text-less results
MAX_BYTES = 8 << 20   # a 40-page scan isn't worth the request budget twice over


# ---------------------------------------------------------------- reading text

MONEY = r'\$?\s*(\(?-?[\d,]+\.\d{2}\)?|\(?-?\d{1,3}(?:,\d{3})+\)?)'


def amount(s):
    """'$1,234.50' -> 1234.5; '(500.00)' -> -500.0; None when not a number."""
    s = s.replace('$', '').replace(',', '').strip()
    neg = s.startswith('(') and s.endswith(')')
    try:
        v = float(s.strip('()'))
    except ValueError:
        return None
    return -v if neg else v


# Totals, most specific first: a line naming the gross total of the whole
# order or invoice. Line-item columns ("Gross" at the head of a column) are
# not totals, which is why each wants "total" or a terminal position.
GROSS = [
    re.compile(r'(?:order|contract|grand|invoice|schedule)?\s*total\s+gross(?:\s+amount)?\s*:?\s*' + MONEY, re.I),
    re.compile(r'gross\s+(?:order\s+|contract\s+|invoice\s+)?(?:total|amount)\s*:?\s*' + MONEY, re.I),
    re.compile(r'total\s+(?:order\s+|contract\s+)?(?:amount|cost|dollars)\s*:?\s*' + MONEY, re.I),
    re.compile(r'(?:order|contract|grand|schedule)\s+total\s*:?\s*' + MONEY, re.I),
]
NET = [
    re.compile(r'total\s+net(?:\s+amount)?\s*:?\s*' + MONEY, re.I),
    re.compile(r'net\s+(?:order\s+|contract\s+|invoice\s+)?(?:total|amount)(?:\s+due)?\s*:?\s*' + MONEY, re.I),
    re.compile(r'(?:amount|balance|total)\s+due\s*:?\s*' + MONEY, re.I),
]
COMMISSION = re.compile(r'(?:agency\s+)?commission\s*(?:\(?\s*\d{1,2}(?:\.\d+)?\s*%\s*\)?)?\s*:?\s*' + MONEY, re.I)

# A labelled field: "Agency: Smart Media Group" up to a run of spaces (the
# next column in -layout text) or the end of the line.
def field(label):
    return re.compile(r'(?:^|\s{2,}|\|)\s*' + label + r'\s*[:#]?\s+([^\n]+?)(?=\s{3,}|\s*$)', re.I | re.M)


AGENCY = [field(r'(?:buying\s+|media\s+|ad(?:vertising)?\s+)?agency(?:\s+name)?'),
          field(r'(?:billing|bill\s+to)\s+(?:agency|name)')]
ADVERTISER = [field(r'advertiser(?:\s+name)?'), field(r'client'), field(r'candidate(?:\s+name)?')]
ORDER_NO = re.compile(r'(?:order|contract|invoice|estimate)\s*(?:no\.?|number|#|id)\s*:?\s*([A-Z]?\d{4,10}(?:-\d{1,2})?)', re.I)
DATE = r'(\d{1,2}/\d{1,2}/\d{2,4})'
FLIGHT = re.compile(r'(?:flight|schedule|air|contract)\s*(?:dates?)?\s*:?\s*' + DATE + r'\s*(?:-|–|to|thru|through)\s*' + DATE, re.I)
SPOTS = re.compile(r'total\s+(?:spots|units)\s*:?\s*([\d,]+)', re.I)

# What isn't an agency: labels and boilerplate that land in the field.
NOT_NAME = re.compile(r'^(?:n/?a|none|direct|same|self|tbd|-+|\W+|address|contact|phone|'
                      r'commission|code|id|no\.?|number|name|ref\w*)\b', re.I)


def first(patterns, text, conv=lambda x: x):
    for p in patterns:
        for m in p.finditer(text):
            v = conv(m.group(1))
            if v not in (None, ''):
                return v
    return None


def last(patterns, text, conv):
    """The last match of the first pattern that matches: a total sits at the
    end of the document, after any subtotals."""
    for p in patterns:
        vals = [v for v in (conv(m.group(1)) for m in p.finditer(text)) if v is not None]
        if vals:
            return vals[-1]
    return None


def name_field(patterns, text):
    for p in patterns:
        for m in p.finditer(text):
            v = re.sub(r'\s+', ' ', m.group(1)).strip(' :,-')
            if v and not NOT_NAME.match(v) and re.search(r'[A-Za-z]{2}', v) and len(v) <= 80:
                return v
    return None


def kind_of(text):
    t = text[:3000].lower()
    if re.search(r'agreement form for (?:political|non-candidate|candidate)|pb-?1[6-9]\b|nab form', t):
        return 'request'
    if re.search(r'\binvoice\b', t):
        return 'invoice'
    if re.search(r'\b(?:order|contract|schedule|proposal)\b', t):
        return 'order'
    return 'other'


def parse(text):
    """What a document's text says: its kind, gross and net amounts, agency,
    advertiser, order number and flight. Fields it can't find are None."""
    k = kind_of(text)
    gross = last(GROSS, text, amount)
    net = last(NET, text, amount)
    comm = last([COMMISSION], text, amount)
    # Net and commission give the gross when only they are printed.
    if gross is None and net is not None and comm is not None:
        gross = round(net + comm, 2)
    fl = FLIGHT.search(text)
    sp = SPOTS.search(text)
    return {
        'kind': k,
        'gross': gross, 'net': net,
        'agency': name_field(AGENCY, text),
        'advertiser': name_field(ADVERTISER, text),
        'order_no': first([ORDER_NO], text),
        'flight': [fl.group(1), fl.group(2)] if fl else None,
        'spots': int(sp.group(1).replace(',', '')) if sp else None,
    }


OCR_PAGES = 2         # a scan is read from its first and last pages this many each


def pdf_text(data, ocr=True):
    """(text, how): the text layer of a PDF laid out in columns ('text'), or
    for a scan with none, tesseract's reading of its first and last pages
    ('ocr'); ('', 'scan') when neither gives anything."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, 'doc.pdf')
        with open(pdf, 'wb') as f:
            f.write(data)
        r = subprocess.run(['pdftotext', '-layout', '-q', pdf, '-'], capture_output=True, timeout=60)
        text = r.stdout.decode('utf-8', 'replace')
        if len(re.sub(r'\s', '', text)) >= 40:
            return text, 'text'
        if not ocr:
            return '', 'scan'
        info = subprocess.run(['pdfinfo', pdf], capture_output=True, timeout=30).stdout.decode('utf-8', 'replace')
        m = re.search(r'^Pages:\s+(\d+)', info, re.M)
        n = int(m.group(1)) if m else 1
        pages = sorted(set(range(1, min(n, OCR_PAGES) + 1)) | set(range(max(1, n - OCR_PAGES + 1), n + 1)))
        out = []
        for pg in pages:
            subprocess.run(['pdftoppm', '-r', '200', '-gray', '-png', '-f', str(pg), '-l', str(pg),
                            pdf, os.path.join(tmp, f'p{pg}')], capture_output=True, timeout=120)
            for png in sorted(x for x in os.listdir(tmp) if x.startswith(f'p{pg}') and x.endswith('.png')):
                t = subprocess.run(['tesseract', os.path.join(tmp, png), '-', '--psm', '6',
                                    '-c', 'preserve_interword_spaces=1'], capture_output=True, timeout=180)
                out.append(t.stdout.decode('utf-8', 'replace'))
        text = '\n\f'.join(out)
        return (text, 'ocr') if len(re.sub(r'\s', '', text)) >= 40 else ('', 'scan')


# ---------------------------------------------------------------- choosing

ORDER_IN_NAME = re.compile(r'(?<!\d)(\d{6,8})(?:-(\d{1,2}))?(?!\d)')
REV = re.compile(r'\brev(?:ision|ised)?\s*#?\s*(\d{1,2})\b', re.I)


def doc_id(f):
    return f.get('file_manager_id') or f.get('file_id')


def candidates(data, media, done):
    """Every unread document in a political-file listing, in reading order."""
    from normalize import buyer_folder, classify
    out = []
    for st in data['stations']:
        newest_rev = {}
        for f in st['files']:
            if (f.get('ext') or '').lower() != 'pdf' or not doc_id(f) or not f.get('folder_id'):
                continue
            kind = classify(f['name'] or '', f['path'])
            m = ORDER_IN_NAME.search(f['name'] or '')
            # An order's revisions share its number; only the newest is read.
            if kind == 'order' and m:
                key = (st['call'], m.group(1))
                rv = REV.search(f['name'] or '')
                rank = (int(rv.group(1)) if rv else 0, f['uploaded'] or '')
                if key not in newest_rev or rank > newest_rev[key][0]:
                    newest_rev[key] = (rank, f)
            out.append((kind, st['call'], f))
    keep = {id(v[1]) for v in newest_rev.values()}
    read_requests = set()
    rows = []
    for kind, call, f in out:
        if doc_id(f) in done:
            if kind == 'request':
                read_requests.add((call, buyer_folder(f['path'])))
            continue
        m = ORDER_IN_NAME.search(f['name'] or '')
        if kind == 'order' and m and id(f) not in keep:
            continue
        rank = {'order': 0, 'other': 1, 'request': 2, 'invoice': 3, 'aired': 4}[kind]
        rows.append((rank, call, f, kind))
    # By kind, newest first within each.
    rows.sort(key=lambda r: r[2]['uploaded'] or '', reverse=True)
    rows.sort(key=lambda r: r[0])
    picked, seen_req = [], set(read_requests)
    for rank, call, f, kind in rows:
        if kind == 'request':
            k = (call, buyer_folder(f['path']))
            if k in seen_req:
                continue
            seen_req.add(k)
        picked.append((call, f, kind))
    return picked


def download_url(f):
    return f"https://publicfiles.fcc.gov/api/manager/download/{f['folder_id']}/{f['file_manager_id']}.pdf"


# ---------------------------------------------------------------- run

FILES = {'tv': 'fcc_political.json', 'cable': 'fcc_cable.json', 'radio': 'fcc_radio.json', 'dbs': 'fcc_dbs.json'}


def read_one(get, f):
    data = get(download_url(f), raw=True)
    if data is None:
        return {'status': 'missing'}
    if not data.startswith(b'%PDF'):
        return {'status': 'not_pdf', 'bytes': len(data)}
    if len(data) > MAX_BYTES:
        return {'status': 'too_big', 'bytes': len(data)}
    text, how = pdf_text(data)
    if not text:
        return {'status': 'scan'}
    return dict(parse(text), status='read', via=how), text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--media', choices=sorted(FILES), default='tv')
    ap.add_argument('--budget', type=int, help='documents to download this run (default 40, more near an election)')
    ap.add_argument('--sample', type=int,
                    help='read this many documents spread across stations and kinds, print their text '
                         'and what it parsed to, and write nothing')
    ap.add_argument('--names', nargs='*', help='with --sample: read only documents whose name or path '
                    'contains one of these')
    ap.add_argument('--offset', type=int, default=0, help='with --sample: skip this many of the sample first')
    ap.add_argument('--out', default=D('fcc_documents.json'))
    args = ap.parse_args()

    import scrape_political_files as sp
    listing = json.load(open(D(FILES[args.media]), encoding='utf-8'))
    try:
        store = json.load(open(args.out, encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        store = {'documents': {}}
    docs = store.setdefault('documents', {})
    queue = candidates(listing, args.media, set() if args.sample else set(docs))

    if args.sample:
        # One of each kind per station, round-robin, so the sample covers
        # every sales system rather than the busiest station's.
        by = {}
        for call, f, kind in queue:
            by.setdefault((call, kind), (call, f, kind))
        # Every station's order first, then the other kinds in turn.
        seq = {}
        for r in sorted(by.values(), key=lambda r: r[0]):
            seq.setdefault(r[2], []).append(r)
        rest = [seq[k][i] for i in range(max(map(len, seq.values())))
                for k in ('request', 'invoice', 'other') if i < len(seq.get(k, []))]
        picks = (seq.get('order', []) + rest)[args.offset:args.offset + args.sample]
        if args.names:
            # Each named document (its newest listing), whatever its kind.
            picks = []
            for want in args.names:
                hit = next(((c, f, k) for c, f, k in queue
                            if want.lower() in f"{f['path']}/{f['name']}".lower()), None)
                if hit:
                    picks.append(hit)
        for call, f, kind in picks:
            print('=' * 100)
            print(f"{call} | {kind} | {f['path']} | {f['name']} | {f['uploaded']}")
            print(download_url(f))
            try:
                res = read_one(sp.get, f)
            except sp.Blocked:
                print('BLOCKED; stopping')
                break
            except RuntimeError as e:
                print('ERROR', e)
                continue
            if isinstance(res, tuple):
                res, text = res
                print(json.dumps(res))
                print('-' * 100)
                print(text if len(text) <= 14000 else text[:7000] + '\n[…]\n' + text[-7000:])
            else:
                print(json.dumps(res))
        print(f'{sp.SENT[0]} requests')
        return

    budget = args.budget
    if budget is None:
        budget = sp.stations_tonight(40, time.strftime('%Y-%m-%d', time.gmtime()), close=(80, 120))
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    counts = {}
    blocked = None
    for call, f, kind in queue[:budget]:
        try:
            res = read_one(sp.get, f)
        except sp.Blocked as e:
            blocked = str(e)
            print(f'  blocked at {call} ({e}); keeping what was read')
            break
        except (RuntimeError, subprocess.SubprocessError) as e:
            print(f'  {call} {f["name"]}: {e}')
            continue
        if isinstance(res, tuple):
            res = res[0]
        res.update({'media': args.media, 'call': call, 'path': f['path'], 'name': f['name'],
                    'uploaded': f['uploaded'], 'name_kind': kind, 'read_at': now, 'parser': PARSER})
        docs[doc_id(f)] = res
        counts[res['status']] = counts.get(res['status'], 0) + 1
    store.update({'source': 'FCC political-file documents (publicfiles.fcc.gov), read with pdftotext',
                  'updated': now, 'blocked': blocked})
    store['documents'] = dict(sorted(docs.items()))
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(store, fh, indent=1, ensure_ascii=False)
    left = len(queue) - sum(counts.values())
    print(f'{args.media}: read {sum(counts.values())} documents {counts}; {left:,} still unread; '
          f'{sp.SENT[0]} requests\nWrote {args.out}')


if __name__ == '__main__':
    main()
