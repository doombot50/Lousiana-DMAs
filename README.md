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
- **The map** — the 64 parishes colored by DMA (New Orleans №50 nationally,
  down to Alexandria №183). Click a market for its stations and totals.
- **Where the money over-weights** — spending per TV household. Alexandria
  ($77.34) and Lafayette ($76.88) run well above the $60.41 state average
  while **Shreveport, the second-largest market, draws just $42.80** —
  campaigns pay a premium for the contested middle of the state and skip the
  Republican northwest. New Orleans lands exactly at par.
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
television: **$11.7M** across ~320 stations since 2000, a tenth of the TV total.
Both pages carry the same tab bar (Television · Radio), from `site_nav.py`, which every page builder fills in so the pages can't drift apart.

Radio is not the TV page with new call signs, because the analysis inverts:

- **Format, not geography, is the spine.** Radio doesn't use DMAs — Nielsen
  Audio rates only a handful of Louisiana metros and much of this money goes to
  unrated territory (Mamou, Crowley, Berwick, Ville Platte). So the page opens
  on format, and the parish map is deliberately absent.
- **A third of it buys Black radio.** Urban, gospel and Black-talk formats take
  **33%** of all radio spending, nearly double news/talk. Nothing comparable
  exists on TV, where a station sells one undifferentiated audience.
- **Each buy is a targeting statement.** Edwards put 61% of his radio money into
  Black-audience stations, Blanco 74%, Boasso 99%; Landry put 48% into
  news/talk and the conservative PACs split ~40/40 talk and country. Jindal is
  the exception — he bought everything.
- **Retail politics shows up.** The median station's buy is **$1,351** against
  $4,221 on TV, and KVPI in Ville Platte (classic country + Cajun French) has
  taken money from **61 committees at $244 a spot** — sheriffs and school-board
  races, a layer invisible on television.
- **Different owners entirely.** iHeartMedia, Townsquare, Cumulus and Audacy,
  plus a large locally-owned share. Gray and Nexstar do not appear.

```bash
python3 build_radio_spend.py     # data/radio_spend.json, from .la_cache
python3 build_radio_page.py      # radio.html + radio.artifact.html
```

`data/radio_stations.json` is the hand-verified reference (call sign → format,
city, owner, market) for the 66 stations carrying 83% of the dollars; edit
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
  only rows explicitly marked radio.

## Rebuild the spending data

`build_station_spend.py` recomputes every dollar figure from the raw filings.
It reads the campaign-finance project's `.la_cache` expenditure files, which
`fetch_cache.py` downloads into `./.la_cache` (git-ignored) from the nightly
`data-cache` release of
[doombot50/la-campaign-finance](https://github.com/doombot50/la-campaign-finance):

```bash
python3 fetch_cache.py                              # ~47MB, 2000 → this year
python3 build_station_spend.py                      # auto-finds ./.la_cache
python3 build_radio_spend.py
python3 build_page.py && python3 build_radio_page.py
```

A sibling checkout's cache (`../la-campaign-finance/.la_cache`), `--cache
<path>` or `$LA_CACHE` work too. Stdlib only. Each spend file records
`data_through`, the newest filing date in the cache, and the pages print it
under the headline ("Filings through October 5, 2026"). The year span in the
copy (`2000–2026`) is filled from `years_covered` at build time, so neither
needs hand-editing when the calendar turns.

### Nightly rebuild

`.github/workflows/nightly-rebuild.yml` runs those five commands every morning
at 11:00 UTC, two hours after the upstream cache refreshes, and commits the
result; GitHub Pages serves the commit. A night with no new filings commits
nothing — the only diff would be the `generated` date, which the workflow
ignores. It can also be run by hand from the Actions tab.

The narrative prose (the $15.3M WWL-TV figure, the per-household comparisons,
the buyer rankings in the copy) is still hand-written and does not move with
the nightly data; the charts, ledgers and stat tiles do.

## FCC political files

`fcc/scrape_political_files.py` reads the political-file folders of the 30
stations at publicfiles.fcc.gov and writes `data/fcc_political.json`: every
document in this year's and next year's folders, with its folder path, name
and upload time. The nightly workflow runs it; publicfiles.fcc.gov is not
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
- **Gentle and incremental.** The FCC's CDN answers a burst of requests with
  a 403, so requests are spaced half a second apart, and a subfolder whose
  recursive file count is unchanged since the last run reuses that run's
  documents instead of being re-walked. On a 403 the scraper waits once,
  then stops and carries every unreached station's previous data forward,
  marked `stale`; if most stations fail it leaves the previous file alone.
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
  which one a race belongs to.
- **Low-power stations** (KLAF-LD) are exempt from the online public file
  and are reported as such rather than as failures.

## Data files

- `data/station_spend.json` — the money. Per station: total spend, filing-row
  count, distinct committees, a year-by-year series, and the top buyers by
  dollars; plus rollups by market and owner group, statewide top buyers, and
  an explicit `caveats` block (see below). `pace` holds each governor's
  cycle as cumulative dollars per week from 104 weeks before the primary to 7
  after (the anchor dates are `PRIMARIES` in `build_station_spend.py`), and
  `recent_buyers` the trailing-year buyers.
- `data/stations.json` — the 30 stations: call sign, virtual channel, network,
  DMA (with 2024–25 Nielsen rank and TV households), owner and ownership notes,
  and the vendor-factions committee counts.
- `data/map_paths.json` — the 64 parish outlines as projected, simplified SVG
  paths (equirectangular, Douglas–Peucker at ~1.1 units), each tagged with its
  DMA. This is what the map draws.
- `data/parish_dma.json` — all 64 parishes → Nielsen DMA. Computed by
  point-in-polygon of parish centroids (U.S. Census cartographic boundaries)
  against Nielsen DMA polygons ([simzou/nielsen-dma](https://github.com/simzou/nielsen-dma)),
  cross-checked against published market lists.

## Method notes

Dollars come from 1.48M Louisiana Ethics Administration expenditure rows,
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

- **Party labels.** Louisiana files most PACs and some candidates as `OTH`,
  which says nothing about which side of a race bought the airtime. For filers
  whose alignment is a matter of public record, the label is corrected in
  `PARTY_OVERRIDE` in `build_station_spend.py` — currently the RGA's Right
  Direction PAC (REP); Gumbo PAC, Walter J. Boasso and Claude "Buddy" Leach Jr.
  (DEM); and John L. "Jay" Dardenne (REP). **A filing that states REP or DEM is
  never overridden**, only `OTH` is, and every correction is listed in the
  source and echoed into the output's `caveats.party_overrides`.

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
