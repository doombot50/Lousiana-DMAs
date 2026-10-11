"""
prose.py — numbers and comparisons for the pages' written copy
================================================================================
The pages' paragraphs carry `{{name}}` markers that the builders fill from
the data on every build (page_shell.publish stops on any left unfilled), so
a sentence like "nearly double news/talk" or "more than the next two
combined" is re-decided each night instead of outliving the numbers it was
written about. These are the shared ways of saying a number.
"""

WORDS = ('zero one two three four five six seven eight nine ten eleven twelve thirteen '
         'fourteen fifteen sixteen seventeen eighteen nineteen twenty').split()
TENS = {30: 'thirty', 40: 'forty', 50: 'fifty', 60: 'sixty', 70: 'seventy', 80: 'eighty', 90: 'ninety'}


def words(n):
    """A count as a word, the way the copy writes small numbers: 13 -> thirteen,
    66 -> sixty-six; larger numbers as digits with commas."""
    if n <= 20:
        return WORDS[n]
    if n < 100:
        t, u = divmod(n, 10)
        return TENS[t * 10] + (f'-{WORDS[u]}' if u else '')
    return f'{n:,}'


def money(x):
    """$11.3M / $1.52M / $948K / $245, matching the pages' own money()."""
    if x >= 1e7:
        return f'${x / 1e6:.1f}M'
    if x >= 1e6:
        return f'${x / 1e6:.2f}M'
    if x >= 1e3:
        return f'${round(x / 1e3)}K'
    return f'${round(x):,}'


def money_words(x):
    """$121 million."""
    return f'${round(x / 1e6):,} million' if x >= 1e7 else money(x)


def dollars(x):
    return f'${round(x):,}'


def pct(f, digits=0):
    return f'{f * 100:.{digits}f}%'


FRACTIONS = [(1 / 4, 'a quarter'), (1 / 3, 'a third'), (1 / 2, 'half'),
             (2 / 3, 'two-thirds'), (3 / 4, 'three-quarters')]


def share_words(f):
    """A share as a fraction a reader holds in their head: 0.289 -> "nearly a
    third", 0.34 -> "a third", 0.53 -> "more than half"."""
    frac, name = min(FRACTIONS, key=lambda x: abs(x[0] - f))
    if f < frac - 0.015:
        return f'nearly {name}'
    if f > frac + 0.015:
        return f'more than {name}'
    return name


def ahead_of(a, b):
    """How far a leads b, for "X takes 29% — {ahead_of} news/talk"."""
    r = a / b if b else float('inf')
    if r >= 2.1:
        return f'{r:.1f} times'
    if r >= 1.9:
        return 'double'
    if r >= 1.7:
        return 'nearly double'
    if r >= 1.25:
        return 'well ahead of'
    return 'just ahead of'


def series(items):
    """a, b and c."""
    items = list(items)
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def fill(tpl, facts):
    """Replace each {{name}}; the caller checks for any left over."""
    for k, v in facts.items():
        tpl = tpl.replace('{{' + k + '}}', str(v))
    return tpl
