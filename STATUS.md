# STATUS — where this project actually is

_Last updated: 2026-09-02._

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
| `registry/*.yaml` | Done for MPO. `sectors.yaml` and `gics_naics.yaml` not yet written. |
| Environment | `.venv` created, all pins from `requirements.txt` installed and confirmed. |

Verified end to end on the live Crawford page, EN and FR: 5 quick facts and
2 updates in both languages, identical hero image path, description/benefits
extracted, French update dates parsed ("3 mars 2026").

---

## Next steps, in order

1. **`pipeline/01_projects.py`** — the remaining piece of stage 01. Wire together
   what already exists: fetch ArcGIS layer 1 (GeoJSON) + layer 2 (attributes),
   group the 20 features into 18 projects on the page `Link`, fetch and parse
   each page EN+FR via `mpo.parse_page`, download heroes, derive `thumb/` (96 px
   circular) and `web/` (~1400 px) with Pillow, write `data/events/` plus the
   append-only `data/history/`.
2. `pipeline/02_sectors.py` — StatCan, **bulk CSV path** (`getFullTableDownloadCSV`),
   not vector-by-vector.
3. `pipeline/03_companies.py` — XIC holdings CSV only.
4. `pipeline/04_bundle.py` → `web/public/data/` + `meta.json`.
5. Palette selection → **run `validate_palette.js` before any chart code**.
6. `web/` — Vite + MapLibre globe, Observable Plot.
7. `verify/`, `tests/`, `CLAUDE.md` via `/init`, `security-review`.

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

**Strategies have no geometry.** Layer 2 polygons return empty; only attributes
come back. Their locations are prose, hand-mapped in `strategies.yaml` with the
verbatim string retained. `alto` (Toronto-Quebec Corridor) is `render: list_only`
— filling ON and QC entirely would claim a footprint ~100× the real one.

**canada.ca fetches fine from Python.** An earlier `curl` timeout was a curl/sandbox
artifact, not a network block. `requests` with a proper User-Agent: 2.4 s.

---

## Open decisions

- Which Radix hues become the fixed categorical slots. Needs the validator run
  against the dark surface before any chart is written.
- Whether `data/raw/` HTML snapshots are committed or only hashed. Currently the
  hash lives in `SourceRef`; the snapshot policy is not yet implemented.
