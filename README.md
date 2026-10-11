# Louisiana Airwaves

**Live at [airwaves.charliestephens.xyz](https://airwaves.charliestephens.xyz/)**

**$121 million** of Louisiana political money has gone to the state's
television stations since 2000. This maps where it landed: every station named
in campaign expenditure filings, placed in the seven Nielsen Designated Market
Areas (DMAs) that cover all 64 parishes, with what each station was paid, who
buys it, and — after a year of consolidation deals — who owns it.

A spin-off of [Louisiana's vendor factions](https://factions.charliestephens.xyz/vendor-factions.html),
which found the buys in the first place: committees that pay the same TV
stations show up as shared-vendor edges in that graph. This page is the
geography and the money underneath those edges.

Figures quoted in this README are a snapshot (October 2026). The pages' own
copy is computed from the data on every build, so the live site is the
current word.

## What it shows

- **The pulse** — annual totals. **78% of every dollar** lands in a
  governor's-race year (2003, 2007, 2011, 2015, 2019, 2023). The 2019
  Edwards–Rispone runoff alone moved $26.4M.
- **The 2027 pace** — cumulative TV dollars week by week before each
  governor's primary since 2003, with the 2027 cycle to date drawn over them
  (primary October 9, 2027, per the Secretary of State's calendar). A year
  out, 2027 sits level with 2019 and behind 2023; in past races a median of
  just 7% of the money had been spent this far out. Below it, **who is buying
  television now**: the top committees over the trailing twelve months of
  filings, with each one's latest buy.
- **The political file** — what the stations themselves say is being
  bought, from their FCC public inspection files: every buyer with documents
  in the current cycle, which stations carry them, and how many were posted
  in the last two weeks, filterable to federal, state & local, or issue ads.
  Stations must post orders within days, so this runs weeks ahead of the
  state finance reports, and it is the only public record here of federal
  races. Counts are documents, not dollars.
- **The map** — the seven markets drawn whole: the 64 parishes in full color
  by DMA (New Orleans №50 nationally, down to Alexandria №183), and the
  markets' 25 Texas, Arkansas and Mississippi counties in a lighter shade.
  Click a market for its stations and totals.
- **Where the money over-weights** — spending per *Louisiana* TV household.
  Nielsen counts a market's households whole, and 46% of Shreveport's are in
  Texas and Arkansas, so over the whole market Shreveport looks like the
  state's bargain ($43 a household against $60). Counted on its Louisiana
  side it is the most heavily bought market in the state (~$80 against ~$69);
  Monroe–El Dorado (13% Arkansas) is the one market below average either
  way. The section's prose is written from the data, so it moves with it.
- **Cycle benchmarks** — each market's TV money in every governor's-race
  year since 2003, as a share of the state, in 2024 dollars (BLS CPI-U, from
  `data/cpi.json`), or per Louisiana TV household. Shreveport's share has halved, from
  23% in 2003 to 11% in 2023, while Lafayette's went from 11% to 18%; in real
  terms 2015 and 2019 were the biggest air wars (~$32M each) and 2023 spent
  half that. These are payments to stations, not ad rates: the filings don't
  say how many spots a payment bought.
- **Ownership** — the count/revenue inversion: **Nexstar owns or operates 13
  of the 30 stations but collects 30.5% of the money, while Gray's 10 collect
  47.6%**, because Gray's ten include the news-leading CBS or NBC affiliate in
  six of seven markets.
- **The ledger** — every station by dollars. WWL-TV leads at $15.3M; WBRL-CD
  has taken $27K in twenty-six years.
- **The buyers** — John Bel Edwards ($11.3M across 29 stations) and Bobby
  Jindal ($8.6M) lead, followed by the outside groups that fought 2019 and
  2023: the RGA's Right Direction PAC, Gumbo PAC, and The Fund for Louisiana's
  Future.

## Run it

`index.html` is fully self-contained — all data is inlined, no network calls
except the webfonts:

```bash
python3 -m http.server 8793
# → http://localhost:8793
```

GitHub Pages serves the repo root; `CNAME` pins the custom domain.

## Rebuild the page

`build_page.py` assembles the page from `page.template.html` + `data/`, and
writes **two** outputs, because the page ships to two places that need
different things:

```bash
python3 build_page.py
```

| output | for | shape |
|---|---|---|
| `index.html` | GitHub Pages | complete document — doctype, charset, viewport, canonical + Open Graph tags |
| `artifact.html` | Claude Artifact | body fragment; the artifact publisher supplies its own `<head>` |

Edit `page.template.html` (never the generated files) and re-run. The doctype
and viewport meta in the standalone build are load-bearing: without them a
raw-served page falls into quirks mode and renders at desktop width on phones.

## Louisiana Dial — the radio sibling

`radio.html` is a second, standalone page covering **radio** rather than
television: **$13.2M** across ~320 stations since 2000, about a ninth of the TV
total. Every page carries the same tab bar and document head, from
`page_shell.py`, which every page builder uses so the pages can't drift apart.

Radio is not the TV page with new call signs, because the analysis inverts:

- **Format, not geography, is the spine.** Radio doesn't use DMAs — Nielsen
  Audio rates only a handful of Louisiana metros and much of this money goes to
  unrated territory (Mamou, Crowley, Berwick, Ville Platte). So the page opens
  on format, and the parish map is deliberately absent.
- **More than a quarter of it buys Black radio.** Urban, gospel and Black-talk
  formats take **29%** of all radio spending, just ahead of news/talk (27%).
  Nothing comparable exists on TV, where a station sells one undifferentiated
  audience. WWL (870 AM / 105.3 FM, news/talk) is the single biggest radio
  earner, at $1.52M.
- **Each buy is a targeting statement.** Edwards put 59% of his radio money into
  Black-audience stations, Blanco 70%, Boasso 99%; Landry put 48% into
  news/talk and Citizens Fighting Crime PAC split 40/40 talk and country.
  Jindal is the exception — he bought everything.
- **Retail politics shows up.** The median station's buy is **$1,372** against
  $4,221 on TV, and KVPI in Ville Platte (classic country + Cajun French) has
  taken money from **62 committees at $246 a spot** — sheriffs and school-board
  races, a layer invisible on television.
- **Different owners entirely.** iHeartMedia, Audacy, Townsquare and Cumulus,
  plus 17% locally owned. Gray and Nexstar do not appear.

```bash
python3 build_radio_spend.py     # data/radio_spend.json, from .la_cache (or build_spend.py for both)
python3 build_radio_page.py      # radio.html + radio.artifact.html
```

`data/radio_stations.json` is the hand-verified reference (call sign → format,
city, owner, market) for the 67 stations carrying 85% of the dollars; edit
`radio.template.html`, never the generated pages.

### Two things the radio build has to handle that the TV build didn't

- **Call signs collide with English.** A plain `[KW][A-Z]{3}` match over these
  filings returns `WINE` (Total Wine), `KING` (Smoothie King Center), `WORD`
  (Last Word Strategies), `WEST` (Ryan West) and `KYLE` (Kyle Ardoin) as radio
  stations — about **$9.0M** of phantom spend. Nothing is matched on shape
  alone: a row counts only if the call sign is in the verified reference or
  carries an explicit `-AM`/`-FM` marker, and the rejected total is reported in
  the output's `caveats`.
- **The unclassified tail is disclosed, not dropped.** ~$2.0M sits on ~254
  small stations identifiable as radio but not individually verified (largest
  about $55K). It is counted in the total and shown as its own bucket, so
  format shares are diluted honestly rather than quoted against a flattering
  denominator.
- **No double-counting with the TV page.** WWL and KTAL share call signs across
  television and radio. Airwaves counts their bare-call rows as TV; Dial counts
  only rows explicitly marked radio. (WWL has three letters, so until October
  2026 the four-letter pattern never matched it, and ~$1.5M of `WWL-AM` /
  `WWL RADIO` rows, excluded from TV as radio, appeared on neither page. The
  test suite caught it.)

## The committees page

`committees.html` profiles every committee that has paid a TV or radio
station since 2000 (about 1,300): totals on each medium, spending by year,
TV by market and station, radio by format and station. It is a searchable
list; `committees.html#f=<filer number>` opens one profile, so profiles can
be linked to directly. The two spend builders write the per-committee detail
(`data/committees_tv.json`, `data/committees_radio.json`), using exactly the
station matching their own pages use, and `build_committees_page.py`
assembles the page. Committees are keyed by state filer number, so a
candidate who filed under two committees appears twice.

**Linked to the political file.** A state or local candidate, or a PAC, in
the FCC political-file list is matched to its state filer, and the two link
both ways: its name on the TV page opens its profile, and the profile shows
a *Booking now* box (documents posted in the last two weeks, at which
stations, each linking to that station's FCC folder for the buyer). A filer
that is booking airtime but hasn't yet reported paying a station gets a
profile too, so the list carries a few dozen more than the ~1,300 that have
paid; a *Booking now* filter narrows it to them. `build_station_spend.py`
writes every filer active in the last three years to `data/filers.json`
for this, and `fcc/normalize.py` matches on first name (spelled out:
"Don" → Donald) and surname, or a PAC's whole name, linking only when
exactly one filer fits. Federal candidates report to the FEC, not the
state, so they are never matched.

**Linking around the site.** A profile's TV markets and stations open the
TV page's map on that market (`/#m=SHV`); each station in the map panel opens
its FCC political file. The TV page keeps the selected market and the
political-file filter in the URL (`#m=LAF&pf=local`; filters `fed`, `local`,
`issue`, `away`), so any view can be shared.

**Linked to the campaign-finance dashboard.** Each profile links to the same
filer on [finance.charliestephens.xyz](https://finance.charliestephens.xyz/)
(`#/campaign/<name>?filer=<n>`: who funds it, cash on hand, its races), and
the dashboard links back. Going the other way, `build_committees_page.py`
writes `data/filer_media.json`, every profile in brief (TV and radio dollars,
years, top stations, and the political-file counts), which the dashboard's
nightly refresh pulls from this site to show each campaign's airtime on its
own profile. Both sides key on the state filer number.

## Rebuild the spending data

`build_spend.py` recomputes every dollar figure from the raw filings, running
the TV build (`build_station_spend.py`) and the radio build
(`build_radio_spend.py`) off one pass over the 1.5M rows; either also runs
on its own.
It reads the campaign-finance project's `.la_cache` expenditure files, which
`fetch_cache.py` downloads into `./.la_cache` (git-ignored) from the nightly
`data-cache` release of
[doombot50/la-campaign-finance](https://github.com/doombot50/la-campaign-finance):

```bash
python3 fetch_cache.py                              # ~47MB, 2000 → this year
python3 build_spend.py                              # TV + radio data; auto-finds ./.la_cache
python3 build_page.py && python3 build_radio_page.py && python3 build_committees_page.py
python3 -m unittest discover -s tests               # the regression tests
```

A sibling checkout's cache (`../la-campaign-finance/.la_cache`), `--cache
<path>` or `$LA_CACHE` work too. Stdlib only. Each spend file records
`data_through`, the newest filing date in the cache, and the pages print it
under the headline ("Filings through October 5, 2026"). The year span in the
copy (`2000–2026`) is filled from `years_covered` at build time, so neither
needs hand-editing when the calendar turns.

### How the code is laid out

- `filings.py` — what the TV and radio builds share: finding and reading the
  cache (one pass, every row handed to each build), vendor-name
  normalization, the party corrections (`party_of`, read from
  `data/party_corrections.json`), the
  committee-detail writer and the governor's-race calendar (`PRIMARIES`).
- `build_station_spend.py`, `build_radio_spend.py`, `build_spend.py` — the
  spend data (above).
- `markets.py` — the seven Nielsen markets: keys, names, ranks, households.
- `fcc/` — the political files: `scrape_political_files.py` (the nightly
  scrape), `normalize.py` (folder path → level, office, buyer; name keys;
  filer matching), `summary.py` (buyers rolled up across stations).
- `page_shell.py` — the tab bar, document head, template tokens and the
  two-output publish step every page uses; `prose.py` — the phrases the copy
  is built from.
- `build_page.py`, `build_radio_page.py`, `build_committees_page.py` — one
  per page, each from its `*.template.html`.
- `build_map.py`, `fetch_households.py` — reference geography and Census
  households, run only when those change.
- `tests/` — regression tests, many of them real filings that were once
  misread. The nightly run starts with them and stops on a failure.

**Copy written from the data.** The templates' paragraphs carry `{{name}}`
markers that each page builder fills from the data (`facts()` in
`build_page.py` and `build_radio_page.py`), and comparisons like "nearly
double" or "more than the next two combined" are decided by `prose.py` on
every build, so a sentence can't outlive the numbers it was written about. A
marker left unfilled stops the build.

### Nightly rebuild

`.github/workflows/nightly-rebuild.yml` runs the tests and then those commands every morning
at 11:17 UTC (off the hour: GitHub drops scheduled runs at :00 under load), after the upstream cache refreshes, and commits the
result; GitHub Pages serves the commit. A night with no new filings commits
nothing — the only diff would be the `generated` date, which the workflow
ignores. It can also be run by hand from the Actions tab.

Each step is built to keep the site up when a source falters, so the last
step, `check_freshness.py`, makes sure someone hears about it. It checks the
age of the la-campaign-finance `data-cache` release (from the GitHub API),
of this site's own build, and of the FCC political files, plus any station
not refreshed in a week. When any is more than three days behind, it opens
an issue titled "Nightly rebuild: site data has stopped updating" (GitHub
emails the repo's watchers), rewrites it each night while the problem lasts,
and closes it once every source is fresh. It cannot notice the workflow
not running at all: GitHub pauses scheduled workflows in a repository with
no activity for 60 days.

The narrative prose (the $15.3M WWL-TV figure, the per-household comparisons,
the buyer rankings in the copy) is still hand-written and does not move with
the nightly data; the charts, ledgers and stat tiles do.

## FCC political files

`fcc/scrape_political_files.py` reads the political-file folders of the 30
stations at publicfiles.fcc.gov and writes `data/fcc_political.json`: every
document in this year's and next year's folders, with its folder path, name
and upload time. In an odd year it also reads the year before: Louisiana's
cycle pairs a federal even year with a state odd year (2026 then the 2027
governor's race), and stations file early buys for the odd-year race in the
even year's folder, so those stay in view after 1 January. The nightly workflow runs it; publicfiles.fcc.gov is not
reachable from every network, and GitHub's runners are where it is known to
work.

```bash
python3 fcc/scrape_political_files.py                      # all stations
python3 fcc/scrape_political_files.py --stations WDSU KATC --years 2026
```

- **The API.** Facility ids come from `/api/service/facility/search/<CALL>`
  (cached in `data/fcc_facilities.json`); the "Political Files" folder from
  the station's profile page; folder contents from
  `/api/manager/folder/id/<folder>.json?entityId=<facility>`.
- **Light on the FCC.** The FCC's CDN blocks scripted traffic it judges
  heavy: a first full run of ~700 requests drew 403s that then held for every
  request, even from a fresh runner. So each night refreshes at most eight
  stations (`--max-stations`), least recently scraped first, which rotates
  all 28 stations with online files through every four nights; requests are
  two seconds apart; and a subfolder whose recursive file count is unchanged
  reuses the previous run's documents instead of being re-walked. On a 403
  the scraper waits once, then stops for the night and keeps everything it
  didn't reach as it was. Each station records `scraped_at`; one not
  refreshed in a week is flagged `stale` and named on the page.
- **Listed, not read.** Amounts sit inside PDFs whose layout varies by
  station and sales system (and the document download URL refuses
  scripted requests), so the record is the folder and file names.
- **Normalizing who bought.** Below the FCC's level folder (Federal, State,
  Local, Non-Candidate Issue Ads) each station improvises —
  `US Senate/Bill Cassidy` at WDSU, `US Senate/Cassidy-R for US Senate/Orders`
  at WWL-TV. `fcc/normalize.py` drops document-type folders, splits office
  from buyer, and merges spellings across stations only where the match is
  unambiguous: a bare surname joins a full name only when exactly one full
  name in the group ends in it, so "John Young" and "John-Paul Young" stay
  two candidates. State and Local are grouped, because stations disagree on
  which one a race belongs to; a full name some stations file under Federal
  and others under State is the federal candidate it is (KTVE and KARD file
  the Senate and House races under State). A race any station marks as
  another state's ("US Senate/Texas/Ken Paxton Victory Fund") is that
  state's everywhere, so KTBS's plain `Federal/US Senate/Ken Paxton` stays
  out of the Louisiana totals. Spelling slips ("Mike Johson") are folded by
  a short, hand-audited `ALIASES` list, and names are shown without the
  office a station wrote onto them ("Don Landry - District Attorney").
- **Links.** On the page each station's call sign under a buyer opens that
  buyer's folder at that station, using the FCC site's own URL form
  (`/tv-profile/<call>/political-files/<path>/<folder id>`); the folder id
  alone decides the page. The scraper records every folder's id by path
  (`folders`) for this. Until a station's next refresh records them, a
  buyer whose documents sit in Orders/Invoices subfolders links to the
  station's political file for the year instead.
- **No buyer folders.** KPLC and KVHP (Lake Charles) file every document
  straight into the office folder and name the buyer only in the file name
  ("Mike Johnson 10.12.26 thru 10.18.26", "BILL CASSIDY FOR US SENATE KVHP
  4378339 INVOICE"). There `buyer_from_filename()` reads the buyer from the
  name, cutting it at the first date or order number and dropping document
  words and call signs; the result then merges with the same buyer at other
  stations by the usual rules, and the page says which stations it applies to.
- **Low-power stations** (KLAF-LD, KSWL-LD) are exempt from the online
  public file; they are listed as such and never requested.

## Data files

- `data/station_spend.json` — the money. Per station: total spend, filing-row
  count, distinct committees, a year-by-year series, and the top buyers by
  dollars; plus rollups by market and owner group, statewide top buyers, and
  an explicit `caveats` block (see below). `pace` holds each governor's
  cycle as cumulative dollars per week from 104 weeks before the primary to 7
  after (the anchor dates are `PRIMARIES` in `filings.py`), and
  `recent_buyers` the trailing-year buyers.
- `data/stations.json` — the 30 stations: call sign, virtual channel, network,
  DMA (with 2024–25 Nielsen rank and TV households), owner and ownership notes,
  and the vendor-factions committee counts.
- `data/map_paths.json` — the outlines of every county in the seven markets
  (the 64 parishes and 25 counties in Texas, Arkansas and Mississippi) as
  projected, simplified SVG paths (equirectangular, Douglas–Peucker at ~1.1
  units), each tagged with its DMA and state, plus the projection so labels
  can be placed by longitude and latitude. Built by `build_map.py` from
  Census county outlines ([plotly/datasets](https://github.com/plotly/datasets))
  and the Nielsen DMA polygons below; this is what the map draws.
- `data/county_dma.json` — those 89 counties → DMA, by the same
  point-in-polygon method; `build_map.py` stops if it disagrees with
  `parish_dma.json` on any parish. The DMA polygons date from the early
  2010s; Nielsen rarely moves a county, but a reassignment since then would
  not show.
- `data/households.json` — Census households (ACS 5-year, table B11001) for
  each of those counties, from `fetch_households.py`. The Census API now
  requires a key, so it reads the ACS table-based summary file instead, and
  www2.census.gov isn't reachable from every network: the **Reference data**
  workflow runs it on GitHub's runners and commits the result (it re-runs
  when the script or county list changes, or by hand each December when a
  new 5-year release comes out). A market's *Louisiana TV households* are its
  Nielsen count scaled by the Louisiana share of these Census households:
  Nielsen publishes TV households only for a market as a whole.
- `data/parish_dma.json` — all 64 parishes → Nielsen DMA. Computed by
  point-in-polygon of parish centroids (U.S. Census cartographic boundaries)
  against Nielsen DMA polygons ([simzou/nielsen-dma](https://github.com/simzou/nielsen-dma)),
  cross-checked against published market lists.

- `data/filer_media.json` — filer number → TV and radio dollars, station
  counts, first and last year, top stations, and the FCC political-file
  counts (`pf`: documents this cycle, in the last two weeks, latest upload,
  stations, stations active now). One line per filer. Read by the
  campaign-finance dashboard; see *The committees page*.

- `data/party_corrections.json` — the filer-keyed party corrections, a
  synced copy of la-campaign-finance's `la_party_corrections.json` (see
  *Method notes*). Don't edit it here; the nightly fetch overwrites it.

## Method notes

Dollars come from 1.5M Louisiana Ethics Administration expenditure rows,
2000–2026. Three corrections are applied, and each is reported in the output's
`caveats` block rather than hidden:

- **Spelling variants.** One station is filed 15–30 ways (`KADN`, `KADN-TV`,
  `KADN - TV`, `KADN-FOX`, `KADN-TV CHANNEL 15`). All fold to one call sign.
- **Radio sisters.** WWL and KTAL share call signs with radio stations. Rows
  explicitly marked radio (`WWL-AM`, `WWL RADIO`, `KTAL-FM`) are excluded —
  $1,600,531 in total. Rows carrying only the *bare* call sign can't be
  resolved either way; they are counted as TV and that amount ($5,270,736,
  nearly all WWL) is disclosed, so **WWL-TV's and KTAL's totals are ceilings**.
- **Combined buys.** $318,380 sits in 72 rows naming two co-owned stations at
  once (`KARD-TV KTVE-TV`, `WGMB WVLA-TV`); those are split evenly rather than
  assigned to whichever sorts first.

One editorial correction is applied on top of the filings:

- **Party labels.** The filings' party is matched from the filer's name
  upstream, which leaves most PACs and some candidates as `OTH` (saying
  nothing about which side bought the airtime) and can hand a filer a
  namesake's label. For filers whose alignment is a matter of public record,
  the label is corrected **by filer number** in
  [la-campaign-finance](https://github.com/doombot50/la-campaign-finance)'s
  `la_party_corrections.json`, the one list both sites apply: currently the
  RGA's Right Direction PAC and John L. "Jay" Dardenne (REP); Gumbo PAC,
  Walter J. Boasso and Claude "Buddy" Leach Jr. (DEM), all where the label
  would otherwise be `OTH`; and Blair Downing Edwards (filer 1314), a
  Republican Supreme Court candidate in 2026 whom the name match put on a
  Democratic namesake, corrected outright. Each entry carries its reason and
  public source. `fetch_cache.py` syncs the file into
  `data/party_corrections.json` nightly, `party_of()` in `filings.py`
  applies it, and the applied list is echoed into each output's
  `caveats.party_corrections`. Add or change corrections upstream, not here.

Two further limits worth knowing:

- **2008 is missing.** That year's expenditure file is absent from the upstream
  data release, so 2008 is absent from every figure here. It was an off-cycle
  year (neighbouring off-years run under $1M), so the effect is small but real.
- Amounts are **nominal dollars**, not inflation-adjusted, and stations
  operated under sharing agreements (`·op`) have their dollars attributed to
  the operator, not the nominal licensee.

Ownership is as reported through September 2026: the Nexstar–Tegna close
(March 2026) and the injunction freezing integration (April 2026), the
Gray–Scripps swap that moved KATC (May 2026), and Gray's purchase of ten Allen
Media stations including KADN/KLAF (2026). Sources are linked in the page.

Radio buys in the same filings (WWL-AM, KEEL, two dozen FM stations) are out of
scope here.
