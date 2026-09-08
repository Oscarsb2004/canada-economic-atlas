# STATUS — where this project actually is

_Last updated: 2026-09-08._

Read this first when picking the project back up. The full design is in
`docs/PLAN.md` and **the ordered work queue is [`docs/BACKLOG.md`](docs/BACKLOG.md)**.
This file records only what is **built and verified**, and the findings that were
bought with real work and should not be rediscovered. It is a progress log, not
a work queue — two lists of "next" is how one of them goes stale.

---

## Built and verified live

| Component | State |
|---|---|
| `atlas/core/schema.py` | Done. Canonical dataclasses, `Provenance`, `Geometry`, `Site`, `Project`, `Series`, `Company`. Round-trip tested. |
| `atlas/net.py` | Done. Polite fetch: 1 req/s, retries with backoff, on-disk cache. Live-tested: 0.9 s cold, 0.001 s cached. |
| `atlas/core/registry.py` | Done. Loads + hard-validates `sources.yaml`, `events.yaml`, `strategies.yaml`. |
| `atlas/sources/mpo.py` | Done. Full project-page parser, EN **and** FR, verified against live pages. |
| `registry/*.yaml` | Done: sources, events, strategies, sectors, gics_naics, palette. |
| `atlas/media.py` | Done. Circular 96 px thumb + 1400 px JPEG, deterministic. |
| **`pipeline/01_projects.py`** | **Done and run.** All 18 projects + 9 strategies. |
| `atlas/sources/statcan.py` | Done. Bulk cube download, both languages, delimiter-safe. |
| **`pipeline/02_sectors.py`** | **Done and run.** 23 national + 299 provincial series. |
| `registry/sectors.yaml` | Done. 20 NAICS + T-codes, partition and cross-cuts. |
| `atlas/sources/companies.py` | Done. XIC holdings parser. |
| **`pipeline/03_companies.py`** | **Done and run.** 216 companies, 6 junk rows dropped. |
| **`pipeline/04_bundle.py`** | **Done and run.** 10 files, 1.40 MB in `web/public/data/`. |
| `registry/gics_naics.yaml` | Done. Lossy crosswalk, versioned, splits documented. |
| **`registry/palette.yaml`** | **LOCKED.** 5 validated categorical slots, dark only. |
| **`scripts/build_geo.mjs`** | **Done and run.** Reproducible world + provinces geometry. |
| **`web/` (M3)** | **Done and verified in a browser.** Globe, pins, corridors, project viewer. |
| **`web/` (M4)** | **Done and verified.** Nine chart forms, filter row, table twins, choropleth. |
| **`web/` (M5)** | **Done and verified.** Pinned tabs, tooltips, accessibility pass. |
| **`verify/` (M6)** | **Done.** 58 gate checks, 0 failures. Does not import `atlas/`. Bespoke checks in `run.py`; declarative ones in `registry/checks.yaml` + `verify/checks.py`. |
| **`tests/` (M6)** | **Done.** 44 tests, each explaining the failure it prevents. |
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

Full pipeline runs end to end; 44 tests pass; 58 gate checks pass; a re-run from
a clean baseline leaves a zero-line git diff.

```
python run.py          # pipeline + verify
python run.py --test   # 44 tests
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

- **Only 3 of the 7 StatCan tables declared in `registry/sources.yaml` are
  actually pulled.** Employment, revenue, capex and nominal-annual are declared
  and unused. That is the cheapest high-value work left.
- **86 dated project updates and 18 slugs of change history are captured and
  never rendered.** The portfolio has no time axis in the UI despite having one
  in the data.

### What to do next

**[`docs/BACKLOG.md`](docs/BACKLOG.md) is the single ordered queue** — five
goals, stages B through P, with effort and the items that need a decision from
you flagged. Critical path: **B1 language toggle → B2 the four unpulled StatCan
tables → B3 the portfolio timeline → C1 the sector crosswalk → C4 projects
beside sector GDP.**

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

- **`04_bundle.py`** additionally writes `web/public/data/country.json` — Canada as
  an ISO3 node with ~4 headline figures, each carrying its `SourceRef`.
- **The palette gate validates 5 categorical slots, not 3.** Slots 1–3 stay what
  this project would have chosen; the sibling needs 5 for bloc encoding, and one
  validator run is cheaper and safer than two independent ones.
- Plus: world geometry at a documented path with its `mapshaper` command recorded,
  `meta.schema_version` treated as semver, and a portable/project-specific banner
  in `schema.py`.

**Full detail, with the exact JSON shape: [`docs/INTEROP-world-strategic-map.md`](docs/INTEROP-world-strategic-map.md).**
Read it before writing `04_bundle.py` or running `validate_palette.js`.

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
nothing and appearing in the diff as a real change. `post_json` now retries, and
an empty fetch falls back to the vintage already on disk. Only a successful
fetch may move the stamp. Caught by `verify/` on its first real run.

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
