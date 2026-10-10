"""
site_nav.py — the tab bar shared by every page on airwaves.charliestephens.xyz
================================================================================
Each page template carries `__NAV__` and `__NAV_CSS__`; its builder fills them
with nav(current) and NAV_CSS, so the pages can't drift apart. Links are
absolute because the same markup also ships in the Claude Artifact
fragments, which aren't served from the site.
"""
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
