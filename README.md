# Louisiana Airwaves

Where Louisiana campaign TV money lands: every television station named in the
expenditure filings of the state's 500 biggest-spending committees, mapped onto
the seven Nielsen Designated Market Areas (DMAs) that cover Louisiana's 64
parishes — with market ranks, TV-household counts, and (after a year of
consolidation deals) who owns each station.

A spin-off of [Louisiana's vendor factions](https://factions.charliestephens.xyz/vendor-factions.html),
which found the buys in the first place: committees that pay the same TV
stations show up as shared-vendor edges in that graph. This page is the
geography underneath those edges.

## What it shows

- **The map** — Louisiana's 64 parishes colored by DMA (New Orleans №50
  nationally, down to Alexandria №183). Click a market for its stations.
- **Ownership** — an owner × market matrix. As of mid-2026, **23 of the 30
  stations are owned or operated by two companies**: Gray Media (a station in
  all seven markets, after picking up KATC from Scripps and KADN/KLAF from
  Allen Media) and Nexstar (thirteen stations counting the Tegna deal a
  federal injunction currently holds in limbo, plus stations operated for
  Mission and White Knight).
- **The ledger** — for each station, how many of the top-500 committees name it
  in a filing (WDSU leads at 97).
- **The buyers** — the committees buying the most stations: Gumbo PAC and the
  RGA's Right Direction PAC each bought 25+ of the 30, the two sides of the
  2023 governor's-race air war.

## Run it

`index.html` is fully self-contained (data inlined, no build step):

```bash
python3 -m http.server 8793
# → http://localhost:8793
```

Ready for GitHub Pages: serve the repo root.

## Data files

- `data/stations.json` — the 30 stations: call sign, virtual channel, network,
  DMA (with 2024–25 Nielsen rank and TV households), owner and ownership notes,
  the number of top-500 committees paying it, and the committees visible on
  vendor-factions graph edges.
- `data/parish_dma.json` — all 64 parishes → Nielsen DMA. Computed by
  point-in-polygon of parish centroids (U.S. Census cartographic boundaries)
  against Nielsen DMA polygons ([simzou/nielsen-dma](https://github.com/simzou/nielsen-dma)),
  cross-checked against published market lists.

## Method notes

- Committee counts are vendor document frequencies from the vendor-factions
  build (July 2026 run: top 500 committees by service spend, 2000–2026,
  Louisiana Ethics Administration expenditure filings), with call-sign spelling
  variants (`KADN`, `KADN-TV`, `KADN - TV`…) merged. Where filings use a bare
  call sign shared with a radio sister (WWL, KTAL), a small share of the count
  may be radio buys.
- Ownership is as reported through September 2026: the Nexstar–Tegna close
  (March 2026) and the injunction freezing integration (April 2026), the
  Gray–Scripps swap that moved KATC (May 2026), and Gray's purchase of ten
  Allen Media stations including KADN/KLAF (2026). Sources are linked in the
  page footer.
- Radio stations in the same filings (KEEL-AM, WWL radio, and two dozen FM
  stations) are out of scope here.
