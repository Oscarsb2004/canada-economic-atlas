# canada-economic-atlas — Implementation Plan

## Context

You want a financial overview of the Canadian economy that does two things at
once: read the **baseline economy** (GDP by sector over time, plus the notable
companies within each sector), and read the **new policy shock** layered on top —
the Major Projects Office (MPO) created under the Building Canada Act, whose
project announcements you want captured **verbatim from the federal source** and
shown geolocated.

The screen splits in half. **Left** is Canada in the world: an interactive globe
that flies down to project pins, each pin fronted by the official rendering the
MPO published for that project, opening a **native in-app viewer** — not an
external link. **Right** is the analytical surface: sector time series and
different ways to cut the baseline economic information.

The structure has to generalise. Canada is the first deep country profile;
"Major Projects Office" is the first hand-picked **Event**. Adding the next
landmark or policy change should mean a registry entry plus a scraper, not a
rewrite.

New standalone repo, sibling to `African-Stability-Index` in the Athena platform
family. It inherits that project's disciplines — registry-driven config,
committed data, provenance on every value, an independent `verify/` — but not its
Dash stack.

---

## Decisions taken with you

| | |
|---|---|
| Stack | React + Vite + MapLibre GL JS; Python for the pipeline |
| Repo | New standalone: `canada-economic-atlas` |
| Map | 3D globe → drill down to project pins |
| Data | Committed JSON snapshots + re-runnable scrapers |
| Events | Event = curated container of geolocated projects |
| Build order | Scrapers first; you review real JSON before any React |
| Language | EN **and** FR captured verbatim |
| Charts | Observable Plot |
| Theme | Dark only, runtime-switchable accent palette from OSS |
| Tabs | Pin any view, persisted to `localStorage` |
| Companies | Two honestly separated panels (§5) |
| Style | Minimalist, compartmentalised; wire existing OSS over custom code |

**Governing rule**, carried from ASI:

> **The frontend and the backend are the same object.**
> Identity travels with the value. The app renders what it is given and never
> re-derives a label, a total, or a rank.

---

## 1. Architecture and the bundle contract

```
Python pipeline (numbered stages)   →   web/public/data/   →   React app
  01_projects   MPO: ArcGIS + HTML + images                    left:  MapLibre globe
  02_sectors    StatCan WDS                                    right: Observable Plot
  03_companies  XIC constituents
  04_bundle     assemble + validate what the web reads
```

`04_bundle.py` writes **directly into `web/public/data/`**, which is committed.
Vite serves `public/` verbatim, so the app is a plain `fetch()` with no loader
plumbing, no import graph, and no build-time data step.

**Sizing (computed, not guessed).** We take 23 national series (20 two-digit
NAICS + T001/T002/T003), not all 249 cube members:

| File | Shape | Approx |
|---|---|---|
| `sectors/national-monthly.json` | 23 series × ~354 months | ~8,100 pts |
| `sectors/provincial-annual.json` | 13 geos × 23 series × 29 yrs × 2 price bases | ~17,000 pts |
| `events/major-projects-office.json` | 27 records incl. verbatim EN+FR | ~300 KB |
| `companies/xic.json` | ~220 constituents | ~40 KB |
| `meta.json` | build stamp, source versions, licence strings | ~2 KB |

**Total ≈ 1–2 MB.** That is under a single map tile's budget, so there is **no
lazy loading, no chunking, and no pagination** anywhere in this project. Media is
the only large payload and is already size-derived (§3.3).

`meta.json` is the bundle contract: `schema_version`, per-source
`retrieved_at` / `source_version` / `licence` / `attribution`. The app renders
attribution from this file rather than hardcoding it, so a licence string is never
stale.

---

## 2. Repository layout

```
canada-economic-atlas/
├── README.md                  # thesis → quick start → stages → verification → caveats
├── CLAUDE.md                  # agent guide with numbered invariants (generate via /init)
├── .gitattributes             # LF enforcement, as in ASI
├── requirements.txt           # PINNED (ASI leaves these open; that bites it in CI)
├── run.py                     # single entry: bootstraps .venv, runs stages or dev server
├── pipeline/
│   ├── 01_projects.py  02_sectors.py  03_companies.py  04_bundle.py
├── atlas/                     # importable package; logic lives here, not in stages
│   ├── core/schema.py         # canonical dataclasses + Provenance enum
│   ├── core/registry.py       # YAML loaders, hard validation on load
│   ├── net.py                 # polite fetch: UA, 1 req/s, backoff, on-disk cache
│   └── sources/  mpo.py  statcan.py  companies.py
├── registry/
│   ├── events.yaml            # curated events; major-projects-office is entry #1
│   ├── sectors.yaml           # NAICS taxonomy ↔ StatCan coordinates
│   ├── strategies.yaml        # strategy → province codes (§3.4)
│   ├── gics_naics.yaml        # hand-curated, versioned crosswalk (§5)
│   └── sources.yaml           # every URL, licence, attribution string
├── data/
│   ├── raw/                   # dated snapshots; large media gitignored
│   └── history/               # append-only page-change log (§3.7)
├── web/
│   ├── public/data/           # THE BUNDLE (committed)
│   ├── public/media/          # thumb/ + web/ renderings (committed)
│   └── src/
│       ├── map/       Globe.tsx  pins.ts  corridors.ts  choropleth.ts
│       ├── charts/    Plot.tsx  palette.ts  specs/*.ts  TableView.tsx
│       ├── panels/    ProjectViewer.tsx  SectorPanel.tsx  CompanyPanel.tsx
│       ├── filters/   FilterRow.tsx
│       ├── tabs/      store.ts  TabStrip.tsx
│       └── theme/     accents.ts
├── verify/                    # independent checks; must NOT import atlas/
└── tests/
```

Conventions follow ASI so the repos read alike: numbered stages at root with logic
in the package, `# ── Section ──` banners, docstrings that explain *why*, config as
YAML and code as Python.

**Deliberately not carried over from ASI:** the global `verify=False` SSL
monkey-patch in its `01_pull.py` (it tracks this as a known defect), unpinned
dependencies, and the 1,200-line single-module UI.

---

## 3. Event 1 — Major Projects Office

### 3.1 Don't scrape what you can download

NRCan publishes an official machine-readable dataset with coordinates under the
**Open Government Licence – Canada**. Scraping covers only what it lacks.

**Backbone — ArcGIS REST, GeoJSON, CORS-open. Verified live: HTTP 200, 20
features, real WGS84 coordinates.**
```
https://maps-cartes.services.geo.ca/server_serveur/rest/services/NRCan/projects_referred_to_mpo_en/MapServer
  Layer 1 = Projects Referred to the MPO   (MultiPoint, 20 features)
  Layer 2 = Transformative Strategies      (Polygon, 9 features)

.../MapServer/1/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson
```
Fields: `Name, Location, Proponent, Sector, Status, Description, Link`.
`Link` is the canonical canada.ca page — **the join key** to the scraped HTML.

Licence + change detection: `metadata_modified` on
`https://open.canada.ca/data/en/dataset/8f387c74-a5d9-46ec-9aff-32bc8e0ff3b1`

### 3.2 Verbatim enrichment — `requests` + BeautifulSoup, no Playwright

Verified by fetching the Crawford page: server-rendered AEM/WET-BOEW HTML, all
text in the initial response. Field order:

**H1 → Proponent → Sector → Location → Description → Quick facts (labelled
bullets, labels vary per project) → Benefits → Latest updates (reverse-chron
dated) → Date modified.**

There is **no explicit capital-cost / jobs / status field** — those numbers live
inside Quick-facts prose ("Will attract $5 billion in investment"). We capture the
prose verbatim and **do not parse numbers out into claims of our own**.

Two gotchas that silently corrupt the scrape:
- **Every content block is emitted twice**, once in `visible-md visible-lg` and
  once in `visible-xs visible-sm`. Select one branch.
- Entities are HTML-escaped (`&rsquo;`, `&#39;`) with heavy `\r\n` and double
  spaces inside paragraphs. Normalise, and keep raw HTML alongside.

### 3.3 Images — the hero is not an `<img>` tag

```html
<div class="provisional bg-cover row"
     data-bgimg="/content/dam/pco-bcp/mpo-bgp/projects/indiv/crawford/MPO_CanadaNickelCrawfordProject_Large.png">
```
`soup.find_all('img')` misses it. Select `[data-bgimg]` for the hero,
`img[src*="/content/dam/"]` for extras.

**Always parse `data-bgimg`; never build the path from the slug** — three folders
don't match (`nouveau-monde`→`nouveau/`, `wind-west`→`atlantic-energy/`,
`vancouver`→`port-van/`) and one official filename contains a typo ("Altantic").
FR reuses identical asset paths — download once.

Heroes are full resolution (Crawford's is 2.08 MB; 27 ≈ 54 MB). Stage 01 derives
two committed variants with Pillow:
- `thumb/` — 96 px, circular-cropped → the map-pin headpiece
- `web/` — ~1400 px → the native project viewer

Originals stay in `data/raw/media/`, gitignored and re-fetchable.

### 3.4 Geometry

All projects carry official WGS84 lat/lon. **Verified: exactly 4 two-point
corridors**, which render as lines, not pins:

| Corridor | From → To |
|---|---|
| Mackenzie Valley Highway | Inuvik `-133.730, 68.359` → Wrigley `-123.479, 63.232` |
| Arctic Economic and Security Corridor | Yellowknife `-114.371, 62.454` → `-110.918, 65.420` |
| Grays Bay Road and Port | `-110.918, 65.420` → `-111.042, 67.807` |
| West Coast Oil Pipeline | Roberts Bank `-123.124, 49.052` → Bruderheim `-113.054, 53.818` |

The North Coast Transmission Line is **three separate single-point features** (one
per phase), not a corridor. AESC and Grays Bay deliberately **share** the node
`-110.918, 65.420` — the NT/NU connection point, not a duplicate to dedupe.

**The 9 transformative strategies have no usable geometry** (Layer 2 polygons
return empty; attributes come back with `f=json&returnGeometry=false`). Their
locations are prose — "All of Canada", "All provinces and territories, except
Prince Edward Island", "Toronto-Quebec Corridor".

*(Gap found in review — this was previously hand-waved.)* Prose is not geometry, so
`registry/strategies.yaml` hand-maps each strategy to province/territory codes,
with the source string retained beside the mapping so the translation is auditable:

```yaml
- slug: critical-minerals
  location_verbatim: "All provinces and territories, except Prince Edward Island"
  provinces: [NL, NS, NB, QC, ON, MB, SK, AB, BC, YT, NT, NU]   # PE excluded
  mapped_by: manual
```
Strategies then render as province fills, never as pins. Anything unmappable
(the Toronto–Quebec corridor is a line, not a set of provinces) is listed in the
panel without a map presence rather than being faked.

Surface the source's own disclaimer: *"All locations are approximate and subject
to final routing decisions."*

Ungeocoded towns named in later news releases resolve via the official NRCan
Geographical Names service (no key, authoritative for northern names):
`https://geogratis.gc.ca/services/geoname/en/geonames.geojson?q=Ignace`

### 3.5 Bilingual

`en`→`fr`, `privy-council`→`conseil-prive`,
`major-projects-office`→`bureau-grands-projets`, `projects`→`projets`,
`other/referred`→`autres/referes`; **terminal slug identical**. Even so, follow
each page's own language-toggle href — the rule is a fallback, not the truth.

### 3.6 Announcements

Split across four hosts, all covered: `canada.ca/en/one-canadian-economy/news/`,
`pm.gc.ca/en/news/`, `canada.ca/en/natural-resources-canada/news/`,
`canada.ca/en/intergovernmental-affairs/news/`.

Crawl seed (30+ items back to June 2025):
`https://www.canada.ca/en/privy-council/major-projects-office/news.html`

Change detection uses sitemaps as source of truth:
`https://www.canada.ca/en/privy-council.sitemap.xml`, filtered to
`major-projects-office`, each URL carrying `<lastmod>`. Note
`https://www.canada.ca/en/sitemap.xml` is a **404**; the index is
`https://www.canada.ca/sitemap.xml`.

### 3.7 History — new section

*(Gap found in review.)* A policy tracker whose scraper overwrites itself loses the
thing that makes it a tracker. Federal pages are edited in place: Crawford's
"Latest updates" gained a March 2026 entry after its November 2025 referral, and
`Date modified` moves without any announcement.

So stage 01 is **append-only**. Each run writes
`data/history/<slug>/<retrieved_at>.json` when and only when `content_sha256`
differs from the previous capture. `data/events/` holds the current state; the
history directory holds every prior state. This makes "what did the government say
about this project, and when did it change?" answerable, and it costs nothing
because captures that don't change write nothing.

### 3.8 Politeness

`canada.ca/robots.txt` is a single `User-agent: *` block with **no `Crawl-delay`**,
and nothing disallows `/en/privy-council/`, `/en/one-canadian-economy/`, or
`/content/dam/pco-bcp/`. The one nearby rule is `Disallow: /*/_jcr_content/par*` —
avoid AEM component URLs.

`atlas/net.py` self-imposes regardless: ~1 req/s, descriptive User-Agent,
exponential backoff on 502/504/524, on-disk cache so development re-runs don't
re-hit the federal site.

### 3.9 The extension seam

*(Gap found in review — the seam was claimed but never shown.)* Adding your next
landmark means adding a `registry/events.yaml` entry and one source module:

```yaml
- slug: major-projects-office
  title_en: "Major Projects Office"
  date: 2025-06-26                 # Building Canada Act receives royal assent
  kind: policy_with_projects       # annotates the timeline AND owns map pins
  source_module: atlas.sources.mpo
  licence: OGL-Canada-2.0
```
`kind` is what lets a future event be a **pure timeline annotation** (a rate
decision, a budget) with no geometry, while MPO is a container of geolocated
projects. Both appear as vertical rules on the sector charts; only the latter
lights up the map.

---

## 4. Baseline economy — StatCan

**Web Data Service** — `https://www150.statcan.gc.ca/t1/wds/rest/`.
**Keyless, no registration, no cost.** OGL–Canada 2.0. 25 req/s per IP.

### 4.1 Goal shift: bulk download primary, vectors incremental

*(Changed in review.)* The original plan pulled series vector-by-vector, which is
why the undocumented 300-vector POST cap mattered. But
`getFullTableDownloadCSV/36100434/en` returns the **entire cube** as a 6.7 MB zip
in one request. That is simpler, atomic, cheaper on their servers, and immune to
the cap.

**So: bulk CSV is the primary path.** Vector calls survive only for a
`--refresh-latest` mode that tops up the last few periods without re-downloading
6.7 MB. The 300-vector chunking still gets a test, because that mode still uses it.

### 4.2 Five things that would otherwise cost hours

1. **`productId` is the 8-digit cube, not the 10-digit table view.** Table
   `36-10-0434-01` → web `pid=3610043401`, but API `{"productId": 36100434}`.
   Views `-01`…`-06` are the same cube.
2. **POST bodies cap at 300 vectors** — 400 returns HTTP 416. Undocumented.
3. **Table 36-10-0402 is dead**, silently replaced by **36-10-0711** (same title).
4. **Chained dollars are non-additive** — "aggregates are not always equal to the
   sum of their components". Where components must sum, use the
   `2017 constant prices` member, not `Chained (2017) dollars`.
5. **The industry label embeds its code**: `Manufacturing [31-33]`. Parse with
   `\[([^\]]+)\]$` and the sector key is free.

### 4.3 Tables

| Purpose | PID | Freq | Coverage |
|---|---|---|---|
| **Real GDP by industry** | `36100434` | Monthly | 1997-01 → 2026-06 |
| Real GDP by industry | `36100449` | Quarterly | → 2026-Q2 |
| **Nominal GDP by industry** | `36100710` | Annual | → **2022** (SUT-derived) |
| **Provincial GDP by industry** | `36100711` | Annual | chained → **2025**; current $ → **2022** |
| Employment (SEPH, clean 2-digit NAICS) | `14100201` | Monthly | → 2026-06 |
| **Sector revenue & profit** | `33100225` | Quarterly | → 2026-Q2 |
| Capital expenditure by industry | `34100035` | Annual | → 2026 (incl. intentions) |

`36100434` coordinates are `geo.seasadj.prices.naics.0.0.0.0.0.0`;
`1.1.1.1.0.0.0.0.0.0` = Canada / SAAR / chained-2017 / All industries = **v65201210**.

**There is no monthly or quarterly current-dollar GDP by industry**, and **no
monthly or quarterly provincial** GDP by industry. The UI states these lags rather
than hiding them.

⚠ **LFS and GDP use different industry aggregations** (LFS collapses wholesale
+retail, finance+real estate, information+recreation). They do not join on a
20-sector key — use SEPH `14100201`, noting it excludes the self-employed and
agriculture. ⚠ Provincial cube `36100711` adds members absent from the monthly
cube (`4AA`, `51A`, `53A`) — filter or double-count.

### 4.4 Sector taxonomy → `registry/sectors.yaml`

The 20 two-digit NAICS sectors as StatCan labels them (11, 21, 22, 23, 31-33, 41,
44-45, 48-49, 51, 52, 53, 54, 55, 56, 61, 62, 71, 72, 81, 91), plus the aggregates
`T001` All industries, `T002` Goods-producing, `T003` Services-producing —
**T002 + T003 = T001 exactly**, which is the clean top-level split and, as §6
explains, the thing that makes the composition chart legal.

`T004`/`T007`, `T010` industrial production, `T013` ICT, `T016` energy, `T018`
public sector are **overlapping cross-cuts, not a partition** — exposed as
alternate lenses, never summed.

### 4.5 Data vintage

*(Added in review.)* GDP is revised. Every series carries the `releaseTime` from
the source and the pipeline's own `retrieved_at`, and `meta.json` records both.
Two runs a month apart legitimately disagree about 2026-04; without the vintage
stamped, that reads as a bug.

### 4.6 Bank of Canada Valet

`https://www.bankofcanada.ca/valet/`, keyless. `V39079` policy rate, `V41690973`
CPI, `CPI_TRIM`/`CPI_MEDIAN`/`CPI_COMMON`, group `FX_RATES_DAILY`. The list route
is `/valet/lists/groups/json` — `/valet/groups/json` is a 404. **No open licence**:
the Bank grants permission requiring attribution and "indicate if changes were
made". Cache daily; FX publishes once per business day by 16:30 ET.

---

## 5. Companies — two honestly separated panels

Company-level GDP contribution does not exist and cannot be defensibly
approximated. StatCan is barred by Statistics Act s.17 from publishing identifiable
enterprise data, and summing company revenues within a sector double-counts
intermediate inputs, overshooting sector GDP by 2–3× because GDP is value-added
while revenue is gross output.

**Panel A — Sector economics** (all OGL–Canada): GDP `36100434` / `36100710`,
employment `14100201`, **total operating revenue by industry `33100225`** — the
legitimate answer to "how commercially large is this sector" — firm counts
`33101095`, capex `34100035`.

**Panel B — Largest listed companies in this sector**, labelled market data, never
"top GDP contributors". *(Simplified in review.)* The original plan joined the TMX
listed-company XLSX to the BlackRock XIC holdings CSV. But XIC alone carries
ticker, name, GICS sector, index weight, shares and price for ~220 constituents —
which fully answers "top companies per sector". **XIC is the only required source.**
TMX `resource/571` is demoted to optional enrichment (it adds HQ location, which
would let company headquarters appear on the map — noted as a future idea, not v1).

Parsing notes: the CSV has a two-line preamble before the header; `Weight (%)` is
*capped* index weight, not market cap; drop the 4 `Cash and/or Derivatives` rows
and stale zero/negative rows.

**GICS ≠ NAICS.** The crosswalk is hand-curated, lossy (GICS Materials splits
across NAICS 21 and 31-33; Communication Services across 51 and 71), and lives
versioned in `registry/gics_naics.yaml` so the mapping is auditable rather than
buried in code.

Future seam: the Globe & Mail ROB Top 1000 is the only source with real revenue for
Canadian public *and* private companies by industry — paid, so
`atlas/sources/companies.py` gets a clean adapter boundary now.

---

## 6. The web app

### 6.1 Map — one library, not two

MapLibre GL JS **v5** ships a native globe projection, so one map serves the world
view and the drill-down. No globe.gl, no three.js.

```js
map.on('style.load', () => map.setProjection({ type: 'globe' }));
```
Calling `setProjection` before style load throws. The globe **auto-transitions to
Mercator around zoom 12**. GeoJSON fills render correctly on the globe (geometry is
subdivided so polygons curve).

**No basemap tiles, no API keys, no cost.** The globe draws from committed vector
data: Natural Earth country polygons with Canada highlighted, and StatCan 2021
cartographic boundary files for provinces (Open Government dataset
`ef70dc3b-1069-4037-9bce-61f47e628a1d`), simplified with `mapshaper` at build time.

Layer order: world fill → Canada highlight → **provincial choropleth** → strategy
region fills → corridor lines → project pins.

**Pins carry no sector color.** *(Changed in review.)* Map pins are an all-pairs
form, which caps categorical color at three; MPO has six sectors. Colouring them
would break the palette gates. It is also unnecessary: the project's own rendering
inside the pin is a far stronger identity cue than any hue. Pins get a single
neutral ring, sector filtering moves to the filter row, and the four corridors are
one hue with direct labels.

### 6.2 Right half — forms chosen before colors

*(Substantially rewritten in review.)* The earlier plan called for a 20-sector
stacked area. That is an anti-pattern twice over — cycling categorical hues past 8,
and more than ~7 color classes carrying meaning — and "level vs contribution to
growth" was drifting toward a dual-axis chart, the single most misleading chart
form. The taxonomy's own hierarchy solves it:

| View | Job | Form | Color job |
|---|---|---|---|
| Headline | one number | **hero figure + KPI row** (GDP, goods, services, policy rate) | none / status |
| Composition over time | part-to-whole | stacked area, **2 series** (T002/T003, which sum exactly to T001) | categorical, 2 slots |
| Sector ranking | magnitude | horizontal bar, 20 sectors | **one hue** — magnitude is not identity |
| All-sector trends | many series | **small multiples**, 20 facets | one hue |
| Growth over time | polarity | **heatmap**, sector × period, centred on 0 | **diverging** blue↔red, neutral gray midpoint |
| Selected sector | one series is the point | **emphasis** — accent line, 19 in de-emphasis gray | 1 hue + gray |
| Contribution to growth | above/below baseline | diverging bar | diverging |
| Provincial | magnitude on geography | choropleth *(on the map, left half)* | one hue |
| Companies | magnitude | bar, top N by weight | one hue |

Facets and small multiples are exactly why Observable Plot was the right pick —
they are a parameter, not a hand-written loop.

Non-negotiables this locks in: **never a dual-axis chart** (two measures of
different scale become two charts or index to 100 at t0); **color follows the
entity, never its rank**, so filtering sectors must not repaint the survivors;
**a table-view twin for every chart**; **crosshair + tooltip by default** on
line/area, per-mark tooltips on bar and heatmap cells, with hit targets ≥24 px;
and series names inserted with `textContent`, never `innerHTML` — they come from
StatCan CSV headers, which is untrusted input.

**One filter row above everything it scopes** (date range first, then geography,
price basis, sector), never per-chart filters. On refetch, charts hold the previous
render at reduced opacity — no skeleton flash.

### 6.3 Theme — and the line between chrome and data

*(Sharpened in review — these were conflated.)* Two palettes, different rules:

**UI chrome** is `@radix-ui/colors` (MIT): 30 hue scales with dark variants and
alpha, as CSS variables under `.dark`. The accent picker rewrites one alias block:
```css
--accent-1 … --accent-12  →  var(--jade-1) … var(--jade-12)
```

**Data series colors are fixed and validated, and the accent picker must not touch
them.** If accents repainted series, "color follows the entity" would break and a
validated palette would silently become unvalidated. The chart palette is built by
plugging Radix ramps into the dataviz parameter table — categorical theme
(fixed slot order), sequential hue, diverging pair + neutral gray midpoint,
reserved status colors, dark chart surface — and then:

```bash
node scripts/validate_palette.js "<hex,hex,...>" --mode dark --surface <dark-surface>
```

**This is a release gate, not a suggestion.** Adjacent-pair CVD ΔE ≥ 8 (OKLab ×100),
normal-vision ΔE ≥ 15 as a hard floor. Because we are dark-only, the dark steps are
*selected* against our surface — not an automatic flip of a light palette.

Given §6.2, the categorical palette needs **at most 3 slots** (goods/services, plus
emphasis accent). Everything else is one-hue or diverging. That is a comfortable
place to be — the all-pairs floors only bite from the 4th slot.

### 6.4 Pinned tabs

A `pin` control on any chart, project, or sector view captures a serialisable
descriptor `{kind, params, label}` — including the current filter-row state, so
reopening a tab restores the whole slice and the numbers still agree. Descriptors
become a renameable, reorderable tab strip persisted via one Zustand store with
`persist` middleware. A tab is a descriptor, not a snapshot, so it re-renders
against current data.

### 6.5 Accessibility

*(Missing before.)* Legend present for ≥2 series; ≤4 series also direct-labelled, so
identity is never color-alone. Every chart has a table-view twin. Keyboard focus
shows what hover shows. Tooltips enhance, never gate. Texture fill available for
the CVD / print / `forced-colors` case, off by default.

---

## 7. Provenance

```python
class Provenance(str, Enum):
    OFFICIAL_DATASET = "official_dataset"   # NRCan ArcGIS / StatCan WDS / BoC
    PAGE_VERBATIM    = "page_verbatim"      # scraped from the federal page as published
    NEWS_RELEASE     = "news_release"       # from a dated announcement
    MARKET_DATA      = "market_data"        # XIC — never labelled as GDP
    DERIVED          = "derived"            # computed by this pipeline
    ABSENT           = "absent"
```

Every scraped record stores `source_url`, `retrieved_at`, `content_sha256`, and its
raw snapshot. **No text under `data/events/` is written by us.** Anything computed
is `DERIVED` and visibly labelled as ours.

---

## 8. Build order

1. `atlas/net.py`, `atlas/core/schema.py`, `registry/*.yaml` — the spine.
2. `01_projects.py` end to end → **checkpoint: you review real JSON, the history
   mechanism, and the derived images before any React exists.**
3. `02_sectors.py` (bulk CSV path), then `03_companies.py`.
4. `04_bundle.py` + `meta.json` contract.
5. Palette selection → **run the validator** → only then any chart code.
6. `web/`: scaffold → globe → pins → project viewer → charts → tabs → theme.
7. `verify/` + tests + `CLAUDE.md` via `/init`.
8. `security-review` before the scrapers are considered done.

---

## 9. Verification

- `python run.py --verify` — independent checks that do **not** import `atlas/`:
  every project has geometry or a documented reason; every verbatim field has a
  `source_url` and a hash matching its snapshot; EN and FR record counts agree;
  every referenced image exists at both sizes; `T002 + T003 == T001` within
  chained-dollar tolerance; every strategy in `strategies.yaml` resolves to valid
  province codes or is explicitly marked unmappable; no series has a fabricated
  period.
- `node scripts/validate_palette.js … --mode dark` — **gates release.**
- `pytest tests/` — registry validation, doubled-HTML dedupe, the three
  slug→image-folder exceptions, corridor-vs-pin classification, the 300-vector
  chunking boundary, GICS→NAICS totality over observed sectors.
- Manual end-to-end: `python run.py` → globe loads with pins, 4 corridors, 3 NCTL
  phase points → click Crawford → viewer shows verbatim description, Quick facts,
  Latest updates, the rendering, source link → pin a sector chart, reload, tab
  survives with its filter state.
- **Re-running `01_projects.py` against unchanged sources must produce a zero-line
  git diff.** That is the real test that the scrape is deterministic.

---

## 10. Scope fence for v1

*(Missing before — this is what stops the project sprawling.)*

**In:** Canada only; MPO as the single Event; national monthly real GDP +
provincial annual; XIC company panel; globe + pins + corridors + provincial
choropleth; the nine chart forms in §6.2; pinned tabs; dark theme with accent
picker.

**Explicitly out of v1:** other countries; other events; company HQs on the map;
CMA-level GDP; the paid ROB Top 1000 adapter; scheduled CI refresh; any
forecasting, modelling, or index construction. Each has a named seam so it can
arrive later without a rewrite.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Federal markup changes | Sitemap `<lastmod>` diffing + hash checks fail loudly rather than writing empty fields |
| Page edited in place, prior wording lost | Append-only `data/history/` (§3.7) |
| Doubled mobile/desktop HTML | Explicit dedupe, with a test |
| Image folder ≠ slug (3 known) | Always parse `data-bgimg`; test asserts every hero resolves |
| Repo bloat from 2 MB renderings | Commit derived sizes only; originals gitignored |
| Nominal GDP is 3 years stale | Real GDP is the default view; nominal explicitly dated in the UI |
| GDP revisions look like bugs | Vintage stamped on every series (§4.5) |
| GICS→NAICS is lossy | Versioned YAML artefact, not hidden logic |
| Chained-dollar non-additivity | Constant-price series wherever components must sum |
| Strategy prose ≠ geometry | Hand-mapped in `strategies.yaml` with the source string retained |
| `curl` to `canada.ca` timed out from my sandbox during recon (WebFetch and the NRCan endpoint both worked) | Generous timeouts + resumable caching; if the sandbox is the blocker, the scraper runs fine from your normal shell |
| Scope creep into a world atlas | §10 fence; Event registry is the only extension seam |
