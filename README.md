# Louisiana Airwaves

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

`index.html` is fully self-contained (data inlined, no build step):

```bash
python3 -m http.server 8793
# → http://localhost:8793
```

Ready for GitHub Pages: serve the repo root.

## Rebuild the spending data

`build_station_spend.py` recomputes every dollar figure from the raw filings.
It needs the campaign-finance project's `.la_cache` expenditure files, which it
auto-finds as a sibling checkout:

```bash
python3 build_station_spend.py                      # auto-find the cache
python3 build_station_spend.py --cache ../la-campaign-finance/.la_cache
LA_CACHE=/path/to/.la_cache python3 build_station_spend.py
```

Stdlib only. Writes `data/station_spend.json` and prints per-station,
per-market and per-owner totals. To get the cache itself, run
`fetch_cache_assets.py` in
[doombot50/la-campaign-finance](https://github.com/doombot50/la-campaign-finance),
which pulls nightly snapshots from that repo's `data-cache` release.

## Data files

- `data/station_spend.json` — the money. Per station: total spend, filing-row
  count, distinct committees, a year-by-year series, and the top buyers by
  dollars; plus rollups by market and owner group, statewide top buyers, and
  an explicit `caveats` block (see below).
- `data/stations.json` — the 30 stations: call sign, virtual channel, network,
  DMA (with 2024–25 Nielsen rank and TV households), owner and ownership notes,
  and the vendor-factions committee counts.
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
