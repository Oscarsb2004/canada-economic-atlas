# STATUS — where this project actually is

_Last updated: 2026-09-12._

Read this first when picking the project back up. The full design is in
`docs/PLAN.md` and **the ordered work queue is [`docs/BACKLOG.md`](docs/BACKLOG.md)**.
This file records only what is **built and verified**, and the findings that were
bought with real work and should not be rediscovered. It is a progress log, not
a work queue — two lists of "next" is how one of them goes stale.

---

## Built and verified live

| Component | State |
|---|---|
| `atlas/core/schema.py` | Done. Canonical dataclasses, `Provenance`, `Geometry`, `Site`, `Project`, `Series`. Round-trip tested. |
| `atlas/net.py` | Done. Polite fetch: 1 req/s, retries with backoff, on-disk cache. Live-tested: 0.9 s cold, 0.001 s cached. |
| `atlas/core/registry.py` | Done. Loads + hard-validates `sources.yaml`, `events.yaml`, `strategies.yaml`, `mpo_naics.yaml`. |
| `atlas/sources/mpo.py` | Done. Full project-page parser, EN **and** FR, verified against live pages. |
| `registry/*.yaml` | Done: sources, events, strategies, sectors, mpo_naics, palette. |
| `atlas/media.py` | Done. Circular 96 px thumb + 1400 px JPEG, deterministic. |
| **`pipeline/01_projects.py`** | **Done and run.** All 18 projects + 9 strategies. |
| `atlas/sources/statcan.py` | Done. Bulk cube download, both languages, delimiter-safe. |
| **`pipeline/02_sectors.py`** | **Done and run.** Seven declared pulls: real GDP (23 national monthly on two price bases, 299 provincial), nominal GDP (23), gross output (330, IOIC crosswalk), capital expenditures (280), SEPH employment (350, streamed). The StatCan section is complete at its basic level. |
| `registry/sectors.yaml` | Done. 20 NAICS + T-codes, partition and cross-cuts. |
| **`pipeline/03_business_counts.py`** | **Done and run.** BACKLOG Q2b, replacing the removed BlackRock company panel. Statistics Canada's newest *Canadian Business Counts, with employees* table, found by title (33101174, June 2026): Canada and 13 provinces and territories × 20 sectors, all industries and Unclassified × 9 size ranges, both languages, StatCan's notes carried. 260 unpublished cells carried as null, each shown by its total to be zero. `business-counts.json`, bundled. |
| **`pipeline/99_bundle.py`** | **Done and run.** 12 files, 1.53 MB in `web/public/data/`. |
| `atlas/sources/census.py` | Done. Table 98-10-0002, both languages, symbols kept, EN/FR cross-checked. |
| **`pipeline/05_municipalities.py`** | **Done and run.** 5,161 `Municipality` records, `data/geography/municipalities.json` (5.6 MB). Not bundled. |
| **`pipeline/06_industries.py`** | **Done and run.** BACKLOG C1, option B + C. All 18 MPO projects placed in NAICS Canada 2022, every quote checked verbatim against Statistics Canada's EN/FR classification files and the project page. 10 joined to NRCan's Major Projects Inventory 2025 by declared ID for status; 3 counted in construction. `industries.json`, bundled, shown in the project viewer as derived. |
| **`pipeline/07_vessels.py`** | **Done and run.** BACKLOG S1. Transport Canada's Canadian Register of Large Vessels, EN + FR paired by row: 26,907 entries, of which the 1,161 carrying an IMO number are committed to `data/vessels/large-vessel-register.json` (1.42 MB). Not bundled. |
| **`live/collect_ais.py`** | **Built and run once (75 s, 2026-09-12): whole-world subscription accepted, 168 messages/s, 11,767 vessels heard, 346 Canadian, 7 also in the register.** The `AISSTREAM_API_KEY` repository secret exists (GitHub lists it as created 2026-09-12T22:01:36Z), so the daily job collects once PR #8 is on main. BACKLOG S2/S3. aisstream.io → Canadian vessels by MMSI 316… or register IMO → a snapshot that keeps each vessel's last heard position. `python run.py --live` on localhost; a daily GitHub Action commits the snapshot to the `vessel-positions` branch and every build copies it in. The globe's "Canadian-flagged vessels" layer reads it. |
| **`registry/palette.yaml`** | **LOCKED.** 5 validated categorical slots, dark only. |
| **`scripts/build_geo.mjs`** | **Done and run.** Reproducible world + provinces geometry. |
| **`web/` (M3)** | **Done and verified in a browser.** Globe, pins, corridors, project viewer. |
| **`web/` (M4)** | **Done and verified.** Nine chart forms, filter row, table twins, choropleth. |
| **`web/` (M5)** | **Done and verified.** Pinned tabs, tooltips, accessibility pass. |
| **`verify/` (M6)** | **Done.** 160 gate checks, 0 failures. Does not import `atlas/`. Bespoke checks in `run.py`; declarative ones in `registry/checks.yaml` + `verify/checks.py`. |
| **`tests/` (M6)** | **Done.** 114 tests, each explaining the failure it prevents. |
| **`run.py`, `CLAUDE.md`** | **Done.** Single entry point; agent invariants. |
| Environment | `.venv` created, all pins from `requirements.txt` installed and confirmed. |

**Stage 01 output, committed:** 18 projects, every one with a French description,
its **Benefits bullets** (76 in total, 18/18 in both languages) and a hero
rendering; 4 corridor sites; `nctl` carrying its 3 phase sites under
one project; 9 strategies joined to the hand-made province mapping.
35 MB of originals reduce to 2.7 MB committed (400 KB thumbs + 2.3 MB web).
`projects.json` is 198 KB.

**Determinism verified:** two consecutive full runs against unchanged sources
produce a zero-line `git diff`. Current-state files are written only when content
actually differs, so `retrieved_at` means "when this was last seen to change",
not "when the scraper last ran".

---

**Stage 02 output, committed:** 23 national monthly series (20 two-digit NAICS +
T001/T002/T003), 1997-01 → 2026-06, on two price bases; 299 provincial series
(13 geographies × 23 codes), 1997 → 2025; the BoC policy rate. 1.1 MB total.
Spot-checked: all-industries 2026-06 = 2,369,309 M chained-2017; Ontario 2025 =
900,844.9 M. Re-run leaves a zero-line diff.

**Chained dollars really are non-additive — measured, not assumed.** On 2026-06,
goods + services vs all-industries drifts **+0.311%** chained and **+0.000%** on
2017 constant prices. Both bases are stored; any view where components must sum
reads `national-constant.json`. `check_partition()` warns past 1%.

---

**The pipeline is complete.** `web/public/data/` holds the full bundle:
7 data files + `country.json` + `palette.json` + `meta.json`, 1.40 MB.

**M2 output, committed:** `web/public/geo/world.json` (66 KB, 177 countries,
Natural Earth 1:110m v5.1.2) and `provinces.json` (319 KB, 13 provinces, StatCan
2021, reprojected to WGS84), plus `SOURCES.json` recording every input and the
verbatim mapshaper commands. Byte-identical across rebuilds.

`canada.json` (277 KB) was added 2026-09-06: the national outline, `-dissolve2`
from `provinces.json` so its arcs are identical to them. The globe highlights
Canada from this, as a glow plus a hairline coastline, rather than filling the
world source's CAN feature — which at 1:110m is **9 polygons and 146 points**,
with no Vancouver Island, no Haida Gwaii and an Arctic archipelago reduced to
lozenges. The dissolved outline is **451 polygons and 16,121 points**, reaching
83.14 degrees N. `verify/` gates both numbers.

**All five interop asks are now landed** (A1 country.json, A2 geometry, A3
palette, A4 semver, A5 schema banners).

**M3 output, committed:** React 19 + Vite 7 + MapLibre 5.24. Split screen:
globe left, context-sensitive panel right. 18 project pins faced with their own
renderings, 4 dashed corridors, Canada highlighted, provinces fading in on zoom.
Clicking a pin flies to the site and opens the verbatim viewer. KPI row reads
real StatCan figures with the vintage stated. No console errors.

Run it: `cd web && npm run dev` → http://localhost:5173

**M4 output, committed:** Observable Plot behind one wrapper. Five switchable
views (composition, ranking, growth, small multiples, heatmap) plus an emphasis
chart, the company panel, and a provincial choropleth on the map. One filter row
scopes everything. Every chart has a table twin. Production build clean; app code
69 KB gzipped with vendor chunks split.

**M5 output, committed:** Pinned tabs persisted to `localStorage`
(`atlas.pins.v1`) — pin any view or project, rename inline, reorder, unpin;
verified to survive a reload. Pointer-driven hairline + formatted tips on lines
and areas, per-mark tips on bars and cells. `prefers-reduced-motion` honoured at
the `flyTo` call site, `forced-colors` block, and a skip link past the map.

**M6 output, committed:** `verify/run.py` (42 gate checks), 22 tests, `run.py`
as the single bootstrapping entry point, `CLAUDE.md`, and a security pass that
found and fixed two real issues (see below).

---

## v1 is COMPLETE per the `PLAN.md` §10 scope fence

Full pipeline runs end to end; 114 tests pass; 160 gate checks pass; a re-run from
a clean baseline leaves a zero-line git diff.

```
python run.py          # pipeline + verify
python run.py --test   # 114 tests
cd web && npm run dev  # the app
```

### Explicitly out of v1, each with a seam already in place

Other countries · other events · company HQs on the map · CMA-level GDP · the
paid ROB Top 1000 adapter · scheduled CI refresh · any forecasting or index
construction.

**[`docs/CODE-TOUR.md`](docs/CODE-TOUR.md) explains the whole codebase file by
file and reports 13 review findings.** Four are worth acting on: the HTTP cache
defeats change detection on a default run (F4), two Range controls silently do
nothing (F1, F2), and `yoyBySector` drops any sector whose latest month is null
(F5). No finding puts a wrong number on screen.

**[`docs/ROADMAP.md`](docs/ROADMAP.md) carries the reasoning behind that queue**
— what is defensible and what would make this project the source of a claim
rather than a reproducer of one. It is not superseded by the backlog and should
not be folded into it: it is what stops an item being done the wrong way.

Two facts from that audit worth surfacing here:

- ~~Only 3 of the 7 StatCan tables declared in `registry/sources.yaml` are
  actually pulled.~~ Resolved by B2 and B2a (2026-09-10/11). `33100225` turned
  out not to be revenue by industry and stays unpulled; gross output comes from
  `36100488` instead.
- **86 dated project updates and 18 slugs of change history are captured and
  never rendered.** The portfolio has no time axis in the UI despite having one
  in the data.

### What to do next

**[`docs/BACKLOG.md`](docs/BACKLOG.md) is the single ordered queue** — five
goals, stages B through Q, with effort and the items that need a decision from
you flagged. Critical path: ~~B1 language toggle~~ → ~~B2 the unpulled StatCan
tables~~ **→ B3 the portfolio timeline → C1 the sector crosswalk → C4 projects
beside sector GDP.** C1 is deferred to you: the work stops there and
lays out the options before anything is built.

**B1 landed 2026-09-10.** EN / FR toggle in the map layer bar, remembered per
browser, `?lang=fr` in a link. Interface text lives in `web/src/i18n.tsx`,
typed so a string missing in French fails the build; numbers and dates come
from the fr-CA locale via `Intl` (en-CA output is character-for-character what
the old hand-written formatter produced). What it found on the way: every chart
label read `label.en` directly, the composition chart's colour domain was a
hardcoded English string that would have matched no French row, the company
panel rendered its own English caveat instead of the payload's bilingual one,
and two chart axes printed bare numbers with no % in either language. Some
fields are carried in English only by the pipeline (B1a), and the interface
French is ours, not a translator's (B1b).

**B2 landed 2026-09-10 — three of four tables, and none was "just a registry
entry".** The backlog said the loaders already handled them; downloading and
reading each cube before writing its entry found otherwise:

- **`36100710` nominal GDP** is current dollars, verified by value ($2,674,953M
  for 2022 against $2,206,344M chained). Additive: goods + services and the
  twenty sectors each equal the total to 0.0002% over 26 years — gated at 0.01%.
- **`34100035` capital expenditures** has no column saying which years are
  actual. Note 4 says the latest two are preliminary actuals and intentions, so
  the payload labels every period from that note (2025 preliminary_actual, 2026
  intentions) and the stage stops if the note disappears. STATUS mixes
  suppression ("x", "..") with quality grades A–F, and both now travel with the
  values. Its "All Industries" total has no code, and the twenty sectors do not
  sum to it where any is suppressed (1.39%), so no total is invented.
- **`14100201` SEPH** is 986 MB of English CSV and 1,075 MB of French. It is
  streamed, and the French file is read only until every wanted label is seen —
  the whole stage runs in about a minute. It is **unadjusted for seasonality**
  (`measure: employment_nsa`) and **excludes agriculture**: `[11N]` is forestry
  alone, so NAICS 11 is declared absent and gated to stay absent. Four sectors
  are published under combined codes (`[22,221]`, `[54,541]`, `[55,551,5511]`,
  `[61,611]`) and aliased; the build refuses any alias that would merge two
  published members. Its partition holds exactly: services fell 123,578 short
  until `[55,551,5511]` was found — that sector is 123,577 employees.
- **`33100225` is not revenue by industry.** It is quarterly balance sheets and
  income statements for *non-financial* industries, in enterprise groups where
  only 5 of the 20 sectors stand alone. Not pulled; decision B2a, which blocks
  D5 and Q5.

Also found: stage 02 never re-downloads a cube zip that already exists (not even
with `--refresh`) while fetching the release stamp live, so a payload can claim a
newer release than the data inside it. Out of B2's scope; raised as its own task.

And the zero-line-diff rule caught a bug older than B2: `write_if_changed` compared
a file as read (lists) against a payload as built (tuples), so any payload holding
a tuple rewrote itself on every run. It now compares against the payload as it
reads back.

**B2a landed 2026-09-11 — gross output, option A.** `36100488` *Output, by sector
and industry, provincial and territorial* is current dollars, 1997–2022, the same
accounts and years as nominal GDP — and it is **not classified by NAICS**. It uses
the Input-Output Industry Classification and splits each industry by institutional
sector: business (`BS…`), non-profit (`NP…`), government (`GS…`). No member is
"NAICS 61"; education is `BS610 + NP61000 + GS610`. So the twenty sectors are a
crosswalk in `sectors.yaml`, each member assigned by the NAICS code it embeds,
summed by `statcan.build_crosswalk_series` and labelled `derived`; the cube's own
"Total industries" is reproduced as official.

- 52, 53 and 55 are one IOIC aggregate (`BS5B0`) and separate only one level
  down, where `BS5A000` is exactly other finance + real estate agents + holding
  companies. `NP999999` embeds no NAICS code and is kept as `unallocated`.
- A sector with any blank member is blank, never a partial sum: 62, 81 and
  unallocated are blank for 14 early years because a non-profit member is not
  published.
- Measured, then gated: members sum to the total within 0.008%; output is never
  below value added in any of 518 code-and-year comparisons (1.14× utilities to 3.61×
  manufacturing, 1.89× overall in 2022); provinces + territories + "Canadian
  territorial enclaves abroad" sum to Canada within 0.001% — without the
  enclaves, public administration is 0.56% short.

The StatCan section is complete at its basic level. Going deeper — below the twenty
sectors, seasonally adjusted employment, StatCan's own productivity measures — is
BACKLOG B2b, deliberately later.

**Stage M (municipalities and public finance) and Stage Q (a critical
evaluation of the financial sector) were added 2026-09-10.** M0 — `Municipality`
records for all 5,161 census subdivisions — is done. Q1 and Q2 need no new data
and are the natural next finance work.

Stage P covers the family: what the three repos actually duplicate, why the
recommendation is to share a spine rather than merge, and the `athena.toml` +
launcher design for running them all from one place.

**[`docs/PROGRAM.md`](docs/PROGRAM.md) is the long-term plan across all three
repos** — nine milestones, namespaced IDs so `CEA-B1` and `WSM-B1` stop
colliding, the dependency graph, every decision you owe batched by when it is
needed, and what would make the plan wrong.

---

## Sibling repo — read before step 4 and step 5

A third Athena project, **`world-strategic-map`** (`C:\Code\world-strategic-map`),
is being built alongside this one: a global strategic map of conflicts, theatres,
maritime chokepoints and alliance blocs. It exists so the §10 scope fence here can
hold — every "make it global" request now has somewhere else to go.

It asks five small things of this repo, none of which block steps 1–3, but two of
which are much cheaper done in the same pass as the work already planned:

- **`99_bundle.py`** additionally writes `web/public/data/country.json` — Canada as
  an ISO3 node with ~4 headline figures, each carrying its `SourceRef`.
- **The palette gate validates 5 categorical slots, not 3.** Slots 1–3 stay what
  this project would have chosen; the sibling needs 5 for bloc encoding, and one
  validator run is cheaper and safer than two independent ones.
- Plus: world geometry at a documented path with its `mapshaper` command recorded,
  `meta.schema_version` treated as semver, and a portable/project-specific banner
  in `schema.py`.

**Full detail, with the exact JSON shape: [`docs/INTEROP-world-strategic-map.md`](docs/INTEROP-world-strategic-map.md).**
Read it before writing `99_bundle.py` or running `validate_palette.js`.

---

## Remote and deployment

**`github.com/Oscarsb2004/canada-economic-atlas` — PUBLIC, and live at
<https://oscarsb2004.github.io/canada-economic-atlas/>** since 2026-09-06.

Every push to `main` now builds and deploys. Verified on the first deploy: all
10 data files, all 3 geometry files and all 18 project thumbnails returned 200,
with no console errors.

Going public exposed the full commit history, this file, `BACKLOG.md`,
`PROGRAM.md`, the ~4.5 MB data bundle and all 18 federal renderings. All of it
is Open Government Licence content with attribution rendered in the app, and
there are no credentials in the repo.

⚠ **The base path is the thing that breaks on a rename.** A project site serves
from `/<repo>/`, and `VITE_BASE` is derived from the repository name in the
workflow rather than hardcoded, so a rename or a fork cannot silently ship a
site whose assets all 404. `asset()` in `bundle.ts` is the runtime half of the
same guarantee — it resolves every site-absolute path in the committed data
against `import.meta.env.BASE_URL`, which is why the bundle stays
deployment-agnostic rather than being rewritten per host.

**The workflow builds but does not scrape.** The bundle is committed, so a
deploy is a pure build of the repo — CI hitting canada.ca and StatCan on every
push would be impolite and would let one commit produce different sites. Refresh
data locally with `python run.py` and commit the diff.

`VITE_BASE` is derived from the repository name, so a rename or a fork will not
silently ship a site whose assets all 404.

⚠ **Building locally on Windows:** Git Bash rewrites an env var whose value
starts with `/` into a Windows path, so `VITE_BASE=/foo/ npm run build` silently
produces `/Program Files/Git/foo/`. Prefix with `MSYS_NO_PATHCONV=1`. CI is on
Linux and unaffected.

---

## History was rewritten on 2026-09-05

`git filter-repo --path data/raw --invert-paths` removed the 28 MB of StatCan
cube zips (and two scratch JSON files) that were committed before the
`.gitignore` rule was widened to the whole of `data/raw/`.

`.git` went **32 MB → 3.3 MB**. All 22 commits and 132 tracked files are
preserved; every commit SHA changed. Verified after the rewrite: 22 tests pass,
42 gate checks pass, `npm run build` succeeds, `git fsck` is clean.

**A full mirror of the pre-rewrite history is at
`C:/Code/atlas-backup-pre-rewrite.git` (32 MB).** Delete it once you are
satisfied — it is the only copy of the old SHAs. Note that `filter-repo`
rewrites tags too, so a tag taken before the run is NOT a backup; only a
separate clone is.

This was done while the repo had no remote, which is the only cheap moment for
it. Do not repeat it after pushing without coordinating.

---

## Security posture

TLS verification is on throughout; there are no credentials in the repo; no
`dangerouslySetInnerHTML` or `innerHTML` anywhere in `web/src`. Two findings were
fixed in M6:

- **`safeExternalUrl()`** allowlists http(s) before any scraped URL reaches an
  `href`. A `javascript:` href from upstream would otherwise be stored XSS.
- **`slug_from_url()` validates** against `^[a-z0-9][a-z0-9._-]*$`, because the
  slug becomes a filesystem path; a URL ending `/../` would write outside
  `data/raw/media/`.

---

## Findings that cost real work — do not rediscover

**Q2b (2026-09-12): StatCan's business counts publish no zero rows.** Of 85,793
rows in table 33101174, not one VALUE is 0; a size range with no locations has
no row. 260 of the 2,772 cells the atlas reads are absent, never a total, and
in all 260 the published ranges already reach the published total. They are
carried as null and shown as zero with that reason — reading an absent row as
zero without the check would be a guess. Each half-year is also a new product
ID, so stage 03 finds the newest table by title.

**2026-09-12: the company panel's source does not permit what the atlas does
with it.** BlackRock Canada's terms limit site content to personal,
non-commercial use, forbid public reuse, and forbid robot copying without
permission. Stage 03 fetches the XIC holdings by script and the public site
republishes them. `sources.yaml` had described the file as "free to consume";
nobody had read the terms. The panel was removed entirely the same day, on the
owner's decision (BACKLOG Q2a).

**No government publishes live ship positions, and AIS filters cannot select
a country.** aisstream.io filters by bounding box or by an explicit MMSI list,
not by prefix, so the collector subscribes to the world and filters on
Canada's MID, 316 (ITU; the Coast Guard's own worked example is 316010115).
Only the nine-digit ship-station form counts — 316 also appears inside coast
station, group and aid-to-navigation identities. The register joins only by
IMO, because it publishes no MMSI.

**2026-09-12: aisstream.io does not answer keepalive pings in time, and the
websockets library drops the stream for it.** The first long localhost run kept
logging `keepalive ping timeout`. Measured on two connections side by side:
with the library's default 20 s ping timeout, 3 drops in 150 s — two at exactly
50.0 s into a connection — and 82 messages/s kept. With client pings off, 1 drop
in 160 s (an abrupt close from the server, 138 s in) and 131 messages/s; the
replies that did come back took 8,230 to 38,631 ms. Processing was never the
cause — 13–16 µs a message. The collector now sends no pings and reopens the
stream after 60 s without a message. The same run found two collectors bound to
port 8765 at once: on Windows the stdlib server's SO_REUSEADDR allows it
silently, so the collector no longer sets it and a second one refuses to start.

**The inventory disputes were settled outside the MPO pages.** The MPO pages
never name Foran, Newcrest or NTPC. McIlvenna Bay: Eldorado Gold closed its
purchase of Foran on 2026-04-14. Red Chris: Newmont bought Newcrest on
2023-11-06. Taltson stayed unresolved on evidence and was matched on the
owner's decision, with its 134 km distance waived and disclosed on screen.

**S1 (2026-09-12): the vessel register's Official Number is not an identity.**
843892 (MTS 3504) and 849528 (THE OLDER I GET) each appear twice, with
different gross tonnage, in both languages. A join keyed on the number keeps
one row and silently drops the other, so vessels are identified by number and
row, and English and French are paired by row with the number checked on all
26,907. Of those, 1,161 carry an IMO number (the only field AIS shares — the
register publishes no MMSI); one of them, 946245, has six digits. Year of Build
is published as values like 188700, 2026 and 0 and is not interpreted. The
French file's header is on its first row and the English file's on its second,
and the French file has a registration-expiry column that is empty in every row.

**C1 (2026-09-12): StatCan's French NAICS element file is not in the English
file's order.** Every code has the same number of elements in both files, so
pairing by position looks safe, and every pair would look plausible. It is
wrong: each file is sorted by its own language's wording, so the sixth English
illustrative example of 488310, "waterfront terminal operation", sits beside
the French "voie maritime, exploitation de". French quotes are declared in
`registry/mpo_naics.yaml` and found in their own file, never paired.

**The two open C1 classes were answered by StatCan's own text, not by us.**
LNG liquefaction is an example under 488990 ("liquefaction and
regasification of natural gas for purposes of transport"); the construction
sector's exclusions send "operating highways, streets and bridges" to 48-49.
Neither was findable by searching for "LNG" or "road operation".

**The Major Projects Inventory covers more of the portfolio than the roadmap
said.** Joined by declared ID and checked by distance, 10 of the 18 MPO
projects are in it, not 6 — including the Darlington SMR project, an MPO
Electricity project filed under the inventory's Energy sector. The English
file writes the status in two casings ("Under Construction", "Under
construction"); the French file has one ("En construction"). Proponent names
disagree for the same project (McIlvenna Bay: Foran Mining vs Eldorado Gold),
which is why the join is by ID and distance.

**B3 (2026-09-11): the update date had never been parsed.** `Update.date` was
documented as ISO 8601 and held the English page's words ("November 13, 2025")
in 56 of 86 updates and nothing in the other 30; the French wording was not
stored at all. Nothing read the field, so nothing noticed until the timeline
had to sort by it. The pattern also missed the publisher's own separators
("January 5,2026", "19 mai, 2026") and had no form for "In July 2026" or
"In 2022". Stage 01 now stores ISO at the precision published — 57 to the day,
4 to the month, 1 to the year, 24 undated — with each language's wording, and
`verify/` re-reads the words independently in both languages.

**A better parser is not a content change.** `verbatim_blob` hashed
`date_verbatim`, our reading of the page. The improved parser moved seven hashes
and stage 01 appended seven "content changed" history entries on a day the
government changed nothing — six English pages had gained a newly-read date,
Nouveau Monde a French one. The hash now reads `_HASHED_UPDATE_DATE`, a frozen
copy of the old pattern (the `benefits_block_text` decision again); the re-run
added 0 entries. Also fixed in the same function: on an EN/FR count mismatch
`_updates` kept the English list and dropped every French entry.

**Stage M0 (2026-09-10): the record is a `Municipality`, not a `City`.** City
is a provincial legal status — 165 subdivisions are typed City, Halifax is a
Regional municipality, Greenwood BC is a City of 702 — and 992 subdivisions are
Indian reserves with no municipal budget. Every census subdivision is a record,
the type is a field, and money will attach to a separate local-government entity
(BACKLOG Stage M, `docs/CIVIC-FISCAL.md`).

**98-10-0002's Symbols column carries meaning.** An unpublished value is a BLANK
cell with its reason beside it: `..` not available (63 reserves), `...` not
applicable (a change from zero). Published values are flagged too: `r` revised on
604 subdivisions' 2016 counts (seven flagged `r,E`), `E` use with caution. The first parser ignored
the column; `Municipality.symbols` keeps it, and a blank with no reason or an
unknown symbol raises.

**The 2021 counts sum exactly to their province; the 2016 counts do not.**
Population, private dwellings and occupied dwellings for 2021 match all 13
published totals at zero tolerance, and `verify/` gates all three. The 2016
columns differ in NL, QC and ON (Ontario by 344), so no 2016 identity is
declared — gating on it would assert something the publisher never claimed.

**The French metadata's municipal type is not always translated.** "Town" appears
698 times in the FRENCH file (Ontario and elsewhere); "Ville" and "Municipalité"
appear in the ENGLISH file for Quebec. Reproduced as published, both sides.

**Verification that passes on nothing.** The declared-check runner read records
with `.get(key, [])`, so a renamed array passed every check on an empty list;
`fields_present` read 0 as missing; `unique_ids` passed records with no id. All
fixed and tested — and a throwaway EN/FR comparison in the same session filtered
rows with `len(row) > 30` on 30-column rows, matched nothing, and printed
"identical". A check that ran over zero rows must say so. The full scan, 14
defects and their tests, is in `docs/TESTS.md`.

**The page markup doubles itself.** canada.ca emits the Proponent/Sector/Location
cards and the entire Description twice — once in `visible-md visible-lg`, once in
`visible-xs visible-sm`. Quick facts, Benefits and Latest updates are **not**
doubled, so blanket text deduplication corrupts those instead. `strip_mobile_twins()`
handles it structurally, once, before anything is read.

**The hero rendering is not an `<img>` tag.** It is a `data-bgimg` attribute on a
div. `find_all('img')` returns nothing. Never construct the path from the slug:
three folders don't match (`nouveau-monde`→`nouveau/`, `wind-west`→`atlantic-energy/`,
`vancouver`→`port-van/`) and one official filename has a typo ("Altantic").

**French headings are not what you would guess.** The pages say **"Faits saillants"**
and **"Dernière mise à jour"** (singular) — not "Faits en bref" / "Dernières mises
à jour". A wrong heading does not raise; it silently yields zero facts while every
other field looks fine. All headings now live in `mpo.HEADINGS`, read off live pages.

**French typography must survive normalisation.** French puts a space before
`: ; ! ?` and before `%` ("90 %"). The whitespace cleanup is therefore restricted
to `, . ) ]` — marks neither language spaces. A broader pattern silently rewrites
correct French and calls the result verbatim.

**The slug is not unique per feature.** ArcGIS publishes **20 features for 18
projects**: `nctl` ships three separately named phase points that all link to one
page. Group on `Link`. The three points are kept as three `Site`s and rendered as
three pins — joining them into a polyline would assert a route alignment the
government never published.

**YAML ate Ontario.** `provinces: [ON, QC]` loads as `[True, "QC"]` — YAML 1.1
coerces bare `ON`/`NO`/`YES`/`OFF` to booleans. Province codes are quoted, and
`registry.py` now rejects non-string codes with an explanatory error.

**The French ArcGIS service has French field names.** It is not the English
service with translated values: the fields are `Nom`, `Emplacement`, `Promoteur`,
`Secteur`, `Etat`, `Lien` — and `Lien` points at the French page. The two
services therefore share no URL, so they are joined on the terminal slug, which
is identical in both languages. `mpo.FIELDS` holds the mapping; use `mpo.attr()`.

**The French StatCan cube is semicolon-delimited.** The European convention,
since French uses the comma as a decimal mark. Parsing it with a comma yields
one enormous column per row, raises nothing, and leaves every French label empty
while the English side looks perfect. `read_cube()` detects the delimiter. Its
NAICS column is also `Système de classification … (SCIAN)`, not a translation of
the English header.

**An empty fetch must never overwrite good committed data.** `getCubeMetadata`
timed out mid-run, `release_time()` returned `""` as designed, and that blank was
written straight into the committed files — replacing a known-good vintage with
nothing and appearing in the diff as a real change. `post_json` now retries.
Caught by `verify/` on its first real run. The fallback first written for it —
reuse the stamp already in the output — was itself half of the next finding.

**The zip never followed the release (2026-09-10).** `download_cube` skipped any
zip already on disk while `release_time()` was fetched live on every run, and
`--refresh` reached only the HTTP text cache. So the first run after a StatCan
release wrote the NEW stamp over figures parsed from the OLD zip: a file
claiming a vintage it did not contain, invisible to `verify/`, which can only
see that a stamp is present. Each zip now has a
`data/raw/statcan/<pid>-<lang>.release` sidecar naming the release it was
downloaded under; the zip is re-fetched when the live stamp differs or on
`--refresh`, and payloads carry the RECORDED stamp. When getCubeMetadata fails,
the zip and its stamp stay put, and a zip with no stamp at all is not parsed —
the committed file is left alone rather than stamped with a guess. Zips from
before the sidecar are dated by file time against the release read as UTC-5
(the stamp has no offset), so existing downloads are adopted, not re-fetched.
Still blind to StatCan replacing a zip without moving `releaseTime`; `--refresh`
and the `_cubes.json` hashes cover that.

**The two language pages do not always publish the same number of benefits.**
The French Taltson page has a fifth bullet the English page omits (on
integrating the grids north and south of Great Slave Lake). Positional pairing
is therefore unsafe — an *inserted* bullet would put every later French sentence
under an unrelated English one and look perfectly correct — but the
`_quick_facts` response of dropping the FR side would have deleted a published
federal sentence from the app in every language. On a mismatch both lists are
carried whole and unpaired, tagged by source language, and `ProjectViewer`
selects the reader's. `verify/` notes the mismatch rather than failing on it.

**Reading a field differently is not the government changing the page.**
`verbatim_blob()` gates history appends, so when Benefits was re-read as a list
of bullets the blob kept hashing the old flattened form. Otherwise the next run
appends a "content changed" entry to all 18 histories on a day nothing moved.
Any future change to how a field is *extracted* owes the same treatment.

**A pinned tab stores the QUESTION, not the answer.** `{kind, params, label}`
re-renders against current data. Storing rendered output would make every tab a
stale copy of the bundle and grow `localStorage` without bound.

**`Plot.crosshairX` prints its own unformatted readouts.** A raw
`2021-06-01T05:00Z` appears beside the tip's formatted one. Use a bare
`Plot.ruleX` + `Plot.pointerX` for the hairline and let the tip carry the
numbers.

**Never guard a MapLibre init effect on its own ref.** An
`if (map.current) return` fights React StrictMode's mount → unmount → mount: the
second setup bails while the first map is torn down, leaving a live canvas whose
map object is destroyed. Every `getSource` / `getStyle` afterwards returns
undefined. The effect's cleanup is the mechanism; the guard is the bug.

**A filter is not a renderer.** Markers came from `kind === "point"` and lines
from `kind === "corridor"`, so the four linear projects — the Arctic Economic
and Security Corridor, Grays Bay Road and Port, the Mackenzie Valley Highway and
the West Coast Oil Pipeline — drew as anonymous dashes with no marker at all.
Nothing to click, no headpiece, no route into the project. Every coverage,
field and coordinate check passed, because none of them asks whether the reader
can reach what we captured. Fixed structurally: `Geometry.anchor` gives every
coordinate-bearing geometry one representative point, `mapFeatures()` is a
total pass with an `assertNever` guard, and `verify/` gates reachability.

**The French page slug is not always the English one.** Eight of the nine
transformative strategies use the same terminal slug in both languages;
`critical-minerals` is published as `mineraux-critiques`. The documented join —
"joined on the terminal slug, which is identical in both languages" — was true
of every project and false of one strategy, so its French name was empty from
the first run until a declared `fields_present` check asked for it. The
exception is declared as `slug_fr:` in `registry/strategies.yaml`, and stage 01
now reports any French feature matching no English slug.

**Coverage has to be checked against the source, not against a number.**
`events.yaml` asserts 20 features / 18 projects / 9 strategies, and every one of
those counts was right while nothing compared them to what canada.ca actually
LISTS. The ArcGIS service and the website are separate publications with
separate cadences; a project with a page and no map presence satisfies every
count. Stage 01 now reads both index pages and commits `coverage.json` so
`verify/` can compare offline. An unreadable index records `null` rather than an
empty list — an empty list reads as "the site lists nothing" and passes.

**Four of nineteen coordinates are outside every province, correctly.** The
committed boundaries are StatCan's **cartographic** file, whose own description
is "major land mass, no coastal water". Roberts Bank is a causeway into the
Strait of Georgia, Contrecoeur is on the St. Lawrence, Grays Bay is a bay and
Ksi Lisims floats. A containment check with no tolerance reports a data problem
that does not exist, and a checker that cries wolf on four of nineteen is one
nobody reads. The tolerance is declared per dataset in `registry/checks.yaml`,
so an event whose sites are all inland can set it to zero.

**Census population centres are agglomerations, not places.** Place labels
ranked by a join to 2021 population centres left 12,071 of 13,018 places
unranked and pushed Ottawa (1,017,449), Mississauga, Brampton, Surrey, Laval and
Gatineau to street zoom: Mississauga and Brampton sit inside the "Toronto"
centre, and Ottawa's is published as "Ottawa - Gatineau (Ontario part)".
Municipal (census subdivision) population now fills ONLY the gaps — 2,858
places ranked (947 census centre, unchanged; 1,911 municipal) — because
replacing centres outright would have demoted Vancouver (municipal 662,248
against a centre of 2,426,160). Duplicate municipal names within a province are
withheld (131), and `population_source` records which figure each label
carries. Four amalgamations stay unmatched — Greater Sudbury, Saguenay,
Chatham-Kent, Clarington — because the placename source records the historic
community, and hand-mapping them would be authoring a join.

Note what the new place-label gates do NOT do: they would not have caught this.
A missing population at the last zoom tier is internally consistent. What makes
a failed join visible is the coverage note — "N of 13,018 ranked" — which is
advisory by design, since any "enough places matched" threshold would be
invented.

**`isStyleLoaded()` is false while ANY source is loading.** The selected-province
highlight returned early on it with no retry, so it failed for the second or two
after rail's 16 MB `setData`. Reproduced: enable rail, click Ontario, and the
panel opens but the province never highlights, even after the map goes idle.
Gate on the specific source (`getSource("provinces")`) and fall back to
`once("style.load")`. The rail lazy-load had the same shape — `railLoaded` set
after an optional `source?.setData` — and now marks itself loaded only once the
data has reached a source.

**MapLibre rejects the WHOLE STYLE for one bad paint expression.** A zoom-based
`interpolate` must be the TOP-LEVEL expression of a paint property, with any
data-driven `match` in its output slots — not a `match` containing ramps, and not
an `interpolate` wrapped in arithmetic. Both were tried on the NHS line width and
both are rejected with *"Only one zoom-based step/interpolate subexpression may
be used"*. The failure is total and silent-looking: the globe renders as a bare
grey sphere with no land, no coastline and no provinces, while the HTML markers
keep drawing because they never touch the style. It reads as "the geometry failed
to load". `buildStyle` is now wrapped in a try/catch that names the error, and
`map.on("error")` is attached — but note the constructor throws BEFORE any
handler can exist, which is why the try/catch is the one that mattered.

**`keep-shapes` guards polygon rings, not short lines.** Every simplify setting
tried on the NHS — 2%, 6%, interval=200 m, interval=1000 m — collapsed the same
37 route groups to `geometry: null`, features with properties and no shape that a
map ignores and a count includes. `-dissolve` alone yields zero. Coordinate
precision does the reduction instead, and its cost was measured rather than
assumed: at 0.01° the collapsed groups total **10.1 km of 49,617 (0.020%)**, the
longest a 0.7 km interchange stub. `build_geo.mjs` prunes them and says how many.

**Natural Earth 1:110m is not a coastline.** It is a globe backdrop, and it is
right for that — but Canada's feature there is 9 polygons for a country with
thousands of islands. Anything that traces, outlines or measures Canadian
geography reads `canada.json`; `world.json` is only ever the other 176 countries
underneath. The two are also drawn differently on purpose: `world` gets a fill,
Canada gets lines, so the archipelago reads as channels rather than a mass.

**Two fills over the same ground stack.** The provincial choropleth looked
broken — every province identical — because the Canada highlight was still
painting at 0.22 underneath, flattening a ramp spanning 3,243 to 900,845. The
highlight now fades out as the choropleth fades in.

**A Plot `cell` mark puts x on a BAND scale.** Handing it raw Dates makes every
timestamp its own category; declare `interval` (e.g. `"month"`) rather than
suppressing the warning.

**`setProjection` must be called inside `style.load`.** Before the style is
ready it throws, and the map renders blank — the single most common way to get
a dead MapLibre globe.

**The `background` layer paints the SPHERE, not the canvas.** Under globe
projection it is the ocean. A first attempt bound an `ocean` fill layer to the
world source, which painted the same country polygons as `land` twice and gave
a planet with no sea. Space is the container's own CSS background.

**Nothing under `data/raw/` may be committed.** It is all re-fetchable input:
HTTP cache, 34 MB of federal renderings, 28 MB of StatCan cube zips, 129 MB of
geometry downloads. An early `.gitignore` listed only `cache/` and `media/`, and
28 MB of zips were committed before anyone noticed. The rule is now the whole
directory, because a per-directory allowlist fails open. The already-committed
zips remain in history before commit `047082b`.

**Natural Earth `ISO_A3` is `-99`** for Norway, France, N. Cyprus, Somaliland and
Kosovo — a dataset quirk, not a download error. Join on `ADM0_A3`.

**Pin the tool, not just the data.** `npx --yes mapshaper` fetches whatever is
current and would silently change committed geometry. mapshaper is a pinned
devDependency called via its Node API.

**Radix has no in-band yellow on dark.** Amber and gold have NO step inside the
dark lightness band (OKLCH L 0.48-0.67) — their dark scales sit above it
entirely. Radix orange has exactly one eligible step (8, the muted `#a35829`,
not the vivid `#f76b15`). So the reference palette's yellow slot has no Radix
equivalent and grass takes slot 3. See `registry/palette.yaml`.

**Five categorical slots pass `--pairs all`, but only just.** Worst normal-vision
ΔE is 15.9 against a floor of 15. A sixth slot breaks it. Six series means
folding to "Other" or faceting — never a palette change.

**Strategies have no geometry.** Layer 2 polygons return empty; only attributes
come back. Their locations are prose, hand-mapped in `strategies.yaml` with the
verbatim string retained. `alto` (Toronto-Quebec Corridor) is `render: list_only`
— filling ON and QC entirely would claim a footprint ~100× the real one.

**canada.ca fetches fine from Python.** An earlier `curl` timeout was specific to
canada.ca HTML over curl, not a network block — the NRCan ArcGIS endpoint returned
200 over curl in the same session. `requests` with a proper User-Agent: 2.4 s.

**`ftp.maps.canada.ca` sends no CORS headers.** Relevant when stage 02/03 fetch the
StatCan and NRCan bulk CSV/GDB files: they cannot be pulled from browser JavaScript,
only server-side. Harmless for us — the pipeline is Python and `requests.get()`
retrieves them without issue — but it rules out ever moving those fetches into the
web app to "skip the pipeline".

---

## Open decisions

- Whether `data/raw/` HTML snapshots are committed or only hashed. Currently the
  hash lives in `SourceRef`; the snapshot policy is not yet implemented.
