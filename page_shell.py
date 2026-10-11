"""
page_shell.py — the shell every page on airwaves.charliestephens.xyz shares
================================================================================
The tab bar, the document <head>, the template tokens, and the two-output
publish step all three page builders use. Each page ships twice: as a
complete standalone document for GitHub Pages (doctype, charset, viewport,
social-preview metadata), and as a body fragment for the Claude Artifact
publisher, which supplies its own <head>. Keeping both built from one
template, through publish(), means they can't drift.

Each template carries `__NAV__` and `__NAV_CSS__`, `__SPAN__`,
`__SPAN_WORDS__` and `__THROUGH__`, and its copy `{{name}}` markers for
figures the builder computes (see prose.py); fill_tokens() fills them all
and stops the build on any left over. Links are absolute because the same markup also
ships in the Artifact fragments, which aren't served from the site.
"""
import re
import time

from prose import fill

SITE = 'https://airwaves.charliestephens.xyz/'
PAGES = [
    ('tv', 'Television', SITE),
    ('radio', 'Radio', SITE + 'radio.html'),
    ('committees', 'Committees', SITE + 'committees.html'),
]

NAV_CSS = (
    '.sitenav{display:flex; gap:2px; padding-top:18px; font-family:Archivo,system-ui,sans-serif;}\n'
    '.sitenav a{font-size:12.5px; font-weight:600; letter-spacing:.02em; padding:7px 12px; '
    'border-radius:999px; color:var(--ink2); text-decoration:none;}\n'
    '.sitenav a:hover{background:var(--hair); color:var(--ink);}\n'
    '.sitenav a[aria-current="page"]{background:var(--ink); color:var(--page);}\n'
    '.sitenav a:focus-visible{outline:2px solid var(--accent); outline-offset:2px;}\n'
)


def nav(current):
    links = ''.join(
        f'<a href="{url}"' + (' aria-current="page"' if key == current else '') + f'>{label}</a>'
        for key, label, url in PAGES)
    return f'<nav class="sitenav" aria-label="Louisiana Airwaves">{links}</nav>'


# The document head for the standalone page. `site_name` is the brand the
# page belongs to, `title` its own name in a social preview.
HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{desc}">
<meta name="color-scheme" content="light dark">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{site_name}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22><text y=%2214%22 font-size=%2214%22>{icon}</text></svg>">
<style>
  html,body{{margin:0}}
  img{{max-width:100%}}
  [hidden]{{display:none!important}}
</style>
'''
TV_ICON, RADIO_ICON = '&#128250;', '&#128251;'


def fill_tokens(tpl, spend, page, facts=None):
    """Fill the template's tokens: the nav for `page`, and the year span and
    "filings through" stamp from the spend file, so they move with the data
    instead of being hand-edited."""
    lo, hi = spend['years_covered']
    through = time.strftime('%B %-d, %Y', time.strptime(spend['data_through'], '%Y-%m-%d'))
    for tok, val in (('__SPAN__', f'{lo}–{hi}'), ('__SPAN_WORDS__', f'{lo} to {hi}'),
                     ('__THROUGH__', through), ('__NAV__', nav(page)), ('__NAV_CSS__', NAV_CSS)):
        tpl = tpl.replace(tok, val)
    tpl = fill(tpl, facts or {})
    left = sorted(set(re.findall(r'__[A-Z_]+__|\{\{\w+\}\}', tpl)))
    if left:
        raise SystemExit(f'unfilled template tokens: {left}')
    return tpl


def publish(template, blob, spend, page, html, artifact, desc, url,
            title='Louisiana Airwaves', site_name='Louisiana Airwaves', icon=TV_ICON, facts=None):
    """Write a page's two outputs from its template: the body fragment
    (`artifact`) and the standalone document (`html`). `blob` replaces the
    template's /*__DATA__*/ placeholder and `facts` its {{name}} markers. The template opens with
    <title>/<link>/<style>, which belong in <head>; everything from its
    <div class="wrap"> on is body."""
    tpl = open(template, encoding='utf-8').read()
    if '/*__DATA__*/' not in tpl:
        raise SystemExit(f'{template} is missing the /*__DATA__*/ placeholder')
    frag = fill_tokens(tpl.replace('/*__DATA__*/', blob), spend, page, facts)
    with open(artifact, 'w', encoding='utf-8') as f:
        f.write(frag)
    split = frag.index('<div class="wrap">')
    head = HEAD.format(desc=desc, url=url, title=title, site_name=site_name, icon=icon)
    with open(html, 'w', encoding='utf-8') as f:
        f.write(head + frag[:split] + '</head>\n<body>\n' + frag[split:] + '\n</body>\n</html>\n')
    return html, artifact
