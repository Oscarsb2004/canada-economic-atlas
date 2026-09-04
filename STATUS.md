# STATUS — where this project actually is

_Last updated: 2026-09-03._

Read this first when picking the project back up. The full design is in
`docs/PLAN.md`; this file records only what is **built and verified** versus
what is **next**, and the findings that were bought with real work and should
not be rediscovered.

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
| Environment | `.venv` created, all pins from `requirements.txt` installed and confirmed. |

**Stage 01 output, committed:** 18 projects, every one with a French description
and a hero rendering; 4 corridor sites; `nctl` carrying its 3 phase sites under
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

**All five interop asks are now landed** (A1 country.json, A2 geometry, A3
palette, A4 semver, A5 schema banners).

## Next steps, in order

1. **M3 first light** — Vite + React scaffold, MapLibre globe, pins with
   thumbnails, corridors, native project viewer.
2. **M4 analysis panel** — `<Plot>` wrapper, one filter row, the nine chart
   forms + a table twin for each, company panel.
3. **M5** — pinned tabs, accessibility pass.
4. **M6** — `verify/`, `tests/`, `CLAUDE.md` via `/init`, `security-review`.

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
