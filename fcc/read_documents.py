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
reads as is fcc/documents.py's parse(), regression-tested on real
documents' text (tests/documents/); a document whose amount can't be found
is kept with `gross: null`, never guessed.

Must run where publicfiles.fcc.gov is reachable (GitHub Actions).
"""
import argparse
import gzip
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
from documents import parse  # noqa: E402
D = lambda *p: os.path.join(ROOT, 'data', *p)

MAX_BYTES = 8 << 20   # a 40-page scan isn't worth the request budget twice over


# ---------------------------------------------------------------- reading text

OCR_PAGES = 2         # a scan is read from its first and last pages this many each
OCR_SECONDS = 90      # per document: a poster-sized scan page can take tesseract many minutes


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
        deadline = time.time() + OCR_SECONDS
        for pg in pages:
            left = deadline - time.time()
            if left <= 5:
                break
            # 200 dpi for a letter page, never more than 2,200 pixels a side:
            # an oversized page is scaled down rather than rendered huge.
            subprocess.run(['pdftoppm', '-r', '200', '-scale-to', '2200', '-gray', '-png', '-f', str(pg),
                            '-l', str(pg), pdf, os.path.join(tmp, f'p{pg}')], capture_output=True, timeout=left)
            for png in sorted(x for x in os.listdir(tmp) if x.startswith(f'p{pg}') and x.endswith('.png')):
                t = subprocess.run(['tesseract', os.path.join(tmp, png), '-', '--psm', '6',
                                    '-c', 'preserve_interword_spaces=1'], capture_output=True,
                                   timeout=max(5, deadline - time.time()))
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
    # Cable systems and satellite list one file in every system of a sales
    # market (fcc/summary.py counts it once); read it once.
    names = set()
    for kind, call, f in out:
        if media in ('cable', 'dbs'):
            if f['name'] in names:
                continue
            names.add(f['name'])
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
    import scrape_political_files as sp
    try:
        data = get(download_url(f), raw=True, max_bytes=MAX_BYTES)
    except sp.TooBig as e:
        return {'status': 'too_big', 'bytes': e.args[0]}
    if data is None:
        return {'status': 'missing'}
    if not data.startswith(b'%PDF'):
        return {'status': 'not_pdf', 'bytes': len(data)}
    text, how = pdf_text(data)
    if not text:
        return {'status': 'scan'}
    return dict(parse(text), status='read', via=how), text


def text_path(cache, did):
    return os.path.join(cache, did[:2], did + '.txt.gz')


def keep_text(cache, did, text):
    os.makedirs(os.path.dirname(text_path(cache, did)), exist_ok=True)
    with gzip.open(text_path(cache, did), 'wt', encoding='utf-8') as f:
        f.write(text)


def reparse(docs, cache):
    """Re-read every kept document's text with the current parser, so a fix
    to fcc/documents.py reaches documents read before it. Returns how many."""
    n = 0
    for did, d in docs.items():
        if d.get('status') != 'read':
            continue
        try:
            with gzip.open(text_path(cache, did), 'rt', encoding='utf-8') as f:
                text = f.read()
        except OSError:
            continue
        d.update(parse(text))
        n += 1
    return n


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
    ap.add_argument('--minutes', type=float, default=30,
                    help='stop reading after this long, keeping what was read (OCR is slow)')
    ap.add_argument('--out', default=D('fcc_documents.json'))
    ap.add_argument('--text-cache', default=os.path.join(ROOT, '.doc_text'),
                    help="where each document's extracted text is kept (git-ignored; the nightly run "
                         "carries it between runs in the Actions cache), so a parser change re-reads "
                         "every document without downloading it again")
    args = ap.parse_args()

    import scrape_political_files as sp
    listing = json.load(open(D(FILES[args.media]), encoding='utf-8'))
    try:
        store = json.load(open(args.out, encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        store = {'documents': {}}
    docs = store.setdefault('documents', {})
    if not args.sample:
        n = reparse(docs, args.text_cache)
        if n:
            print(f'Re-read {n:,} documents from the text cache with the current parser')
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
            except (RuntimeError, subprocess.SubprocessError) as e:
                print('ERROR', type(e).__name__, e)
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

    def save():
        """Write what has been read so far, atomically, so a run cut off by
        its step's timeout keeps every document it finished."""
        store.update({'source': 'FCC political-file documents (publicfiles.fcc.gov), read with pdftotext',
                      'updated': now, 'blocked': blocked})
        store['documents'] = dict(sorted(docs.items()))
        with open(args.out + '.tmp', 'w', encoding='utf-8') as fh:
            json.dump(store, fh, indent=1, ensure_ascii=False)
        os.replace(args.out + '.tmp', args.out)

    t0 = time.time()
    for call, f, kind in queue[:budget]:
        if time.time() - t0 > args.minutes * 60:
            print(f'  {args.minutes:g} minutes up; the rest wait for the next run', flush=True)
            break
        t1 = time.time()
        try:
            res = read_one(sp.get, f)
        except sp.Blocked as e:
            blocked = str(e)
            print(f'  blocked at {call} ({e}); keeping what was read', flush=True)
            break
        except subprocess.TimeoutExpired:
            # Recorded, so it doesn't take a slot every night.
            res = {'status': 'too_slow'}
        except (RuntimeError, subprocess.SubprocessError, OSError) as e:
            print(f'  {call} {f["name"]}: {e}', flush=True)
            continue
        if isinstance(res, tuple):
            res, text = res
            keep_text(args.text_cache, doc_id(f), text)
        res.update({'media': args.media, 'call': call, 'path': f['path'], 'name': f['name'],
                    'uploaded': f['uploaded'], 'name_kind': kind, 'read_at': now})
        docs[doc_id(f)] = res
        counts[res['status']] = counts.get(res['status'], 0) + 1
        print(f"  {call:<8} {res['status']:<8} {res.get('via') or '':<4} {time.time() - t1:5.1f}s  "
              f"{res.get('gross') or '':>10}  {(res.get('agency') or '')[:30]:<30}  {(f['name'] or '')[:50]}",
              flush=True)
        save()
    save()
    left = len(queue) - sum(counts.values())
    print(f'{args.media}: read {sum(counts.values())} documents {counts}; {left:,} still unread; '
          f'{sp.SENT[0]} requests\nWrote {args.out}')


if __name__ == '__main__':
    main()
