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
| `atlas/media.py` | Done. Circular 96 px thumb + 1400 px JPEG, deterministic. |
| **`pipeline/01_projects.py`** | **Done and run.** All 18 projects + 9 strategies. |
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

## Next steps, in order

1. `pipeline/02_sectors.py` — StatCan, **bulk CSV path** (`getFullTableDownloadCSV`),
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

**The French ArcGIS service has French field names.** It is not the English
service with translated values: the fields are `Nom`, `Emplacement`, `Promoteur`,
`Secteur`, `Etat`, `Lien` — and `Lien` points at the French page. The two
services therefore share no URL, so they are joined on the terminal slug, which
is identical in both languages. `mpo.FIELDS` holds the mapping; use `mpo.attr()`.

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

- Which Radix hues become the fixed categorical slots. Needs the validator run
  against the dark surface before any chart is written.
- Whether `data/raw/` HTML snapshots are committed or only hashed. Currently the
  hash lives in `SourceRef`; the snapshot policy is not yet implemented.
