#!/usr/bin/env python3
"""
merge_documents.py — fold another copy of data/fcc_documents.json into ours
===========================================================================
The nightly rebuild and the document reader (.github/workflows/
read-documents.yml) both record documents in data/fcc_documents.json, and
either can push while the other runs. Before committing, each folds the
branch's copy into its own, so neither loses what the other read:

    python3 fcc/merge_documents.py origin/<branch>     # a git ref
    python3 fcc/merge_documents.py path/to/other.json  # or a file

A document in both keeps the record read later.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OURS = os.path.join(os.path.dirname(HERE), 'data', 'fcc_documents.json')


def merge(ours, theirs):
    """`ours` with every document of `theirs` it lacks, or has read earlier."""
    docs = ours.setdefault('documents', {})
    added = 0
    for k, v in (theirs.get('documents') or {}).items():
        if k not in docs or (v.get('read_at') or '') > (docs[k].get('read_at') or ''):
            docs[k] = v
            added += 1
    ours['documents'] = dict(sorted(docs.items()))
    return added


def load_other(src):
    if os.path.exists(src):
        with open(src, encoding='utf-8') as f:
            return json.load(f)
    r = subprocess.run(['git', 'show', f'{src}:data/fcc_documents.json'], capture_output=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout else {}


def main():
    theirs = load_other(sys.argv[1])
    try:
        with open(OURS, encoding='utf-8') as f:
            ours = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        ours = {'documents': {}}
    n = merge(ours, theirs)
    with open(OURS + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(ours, f, indent=1, ensure_ascii=False)
    os.replace(OURS + '.tmp', OURS)
    print(f'Merged {n} documents from {sys.argv[1]}; {len(ours["documents"]):,} in all')


if __name__ == '__main__':
    main()
