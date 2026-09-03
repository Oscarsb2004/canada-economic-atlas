# INTEROP — `world-strategic-map`

_Written 2026-09-03. Addressed to whoever picks up `canada-economic-atlas` next._

A sibling repo is being built alongside this one: **`world-strategic-map`**, third
member of the Athena family after `African-Stability-Index` and this project.

**Nothing in here blocks your next steps.** Stages 02, 03 and the `web/` build
proceed exactly as `STATUS.md` describes. Four of the five asks below are small
additions to work you are already going to do; the fifth is a comment banner.
Read this before writing `04_bundle.py` and before running the palette validator,
because those two are the places where doing it now costs nothing and doing it
later costs a migration.

---

## 1. What the sibling is

A **strategic map**: one globe, no split screen, showing conflicts, theatres,
maritime chokepoints and alliance structure worldwide, viewable **by bloc and by
alliance**. It reads geography, published economic scale, and published military
expenditure together, so that a question like "what does a Hormuz closure do to
the countries that depend on it" is answerable by looking rather than by
modelling.

It is a **thin overlay by design**. v1 ships a handful of layers over committed
static data and grows source by source. It is explicitly not an intelligence
platform and not a forecasting tool.

**Every dataset it uses is keyless.** UCDP's REST API, GDELT's DOC API, IMF
PortWatch's ArcGIS open-data endpoints, World Bank WDI, and static downloads from
SIPRI, Correlates of War, ATOP and the Caldara–Iacoviello GPR index. ACLED is out
of v1 precisely because it requires registration. No account, no key, no secret
ever enters either repo.

## 2. Why it is a separate repo, and why that protects this one

`PLAN.md` §10 fences three things out of v1: other countries, other events, and
"any forecasting, modelling, or index construction". That fence is correct and
the sibling exists so it can hold. Every request to make this project a little bit
global now has somewhere else to go.

The division:

| | `canada-economic-atlas` | `world-strategic-map` |
|---|---|---|
| Subject | one country, in depth | ~40 countries, one dimension each |
| Question | how is this economy structured, and what is the new policy doing to it | where are the theatres, who is aligned with whom, what flows through the chokepoints |
| Time | time series, revisions, vintages | current state plus a coarse event window |
| Source discipline | federal text reproduced verbatim | third-party datasets republished under their own licences; **no original data is created** |
| Screen | globe left, analytical panel right | one globe, layer switcher, side panel on selection |

The sibling **will never**: import `atlas/`, write into this repo's `data/`,
scrape canada.ca, or re-derive any number this project publishes. It reads
committed JSON at a documented path, or it does without.

---

## 3. What it needs from here

### A1 — Emit a country-level record for Canada · _land it in `04_bundle.py`_

This is the entire data integration surface. The sibling needs Canada as one node
among many: an ISO3 key and a few headline figures, so its country panel shows
real StatCan numbers instead of a second-hand World Bank approximation, and can
link through to this app for the deep read.

Write `web/public/data/country.json`:

```jsonc
{
  "schema_version": "1.0.0",
  "iso3": "CAN",
  "iso2": "CA",
  "name": { "en": "Canada", "fr": "Canada" },
  "generated_at": "2026-09-03T18:22:00Z",
  "atlas": {
    "repo": "canada-economic-atlas",
    "meta": "/data/meta.json"          // where the full bundle contract lives
  },
  "headline": [
    {
      "key": "gdp_real_all_industries",  // stable key; the sibling joins on this
      "label": { "en": "Real GDP, all industries", "fr": "PIB réel, ..." },
      "value": 2345678.9,
      "unit": "CAD",
      "scalar": "millions",              // schema.Series.scalar, unchanged
      "period": "2026-06",
      "frequency": "monthly",
      "source_table": "36100434",
      "release_time": "2026-08-28T12:30:00Z",
      "provenance": "official_dataset",
      "source": { /* SourceRef.to_dict() verbatim */ }
    }
  ]
}
```

Notes that matter:

- **`headline` is a list, not an object.** New figures append; nothing in the
  sibling breaks when they do.
- Suggested initial keys, all of which you will already have after stage 02:
  `gdp_real_all_industries` (T001), `gdp_real_goods` (T002),
  `gdp_real_services` (T003), `policy_rate` (BoC V39079). Four is plenty.
- Every entry carries its own `SourceRef` and `provenance`, so **the governing
  rule survives the repo boundary** — the sibling renders identity that travelled
  with the value and re-derives nothing, exactly as this app does.
- `release_time` alongside `period` matters here for the same reason it matters
  internally (§4.5): the sibling will show Canada beside countries whose figures
  are annual and years stale, and the vintage is what makes that comparison
  honest rather than flattering.
- This file is **additive**. It does not change `meta.json`, the existing bundle
  files, or any schema type.

### A2 — Publish the world geometry as a reproducible artifact

`PLAN.md` §6.1 has this project drawing "Natural Earth country polygons with
Canada highlighted", simplified with `mapshaper` at build time. The sibling needs
the *same* polygons at the *same* simplification, or the two apps will disagree
about where borders are and flipping between them will look broken.

Please:

1. Write the simplified world file to a documented path — `web/public/geo/world.json`
   is suggested — separate from `web/public/data/`, since it is geometry, not bundle.
2. Record the exact provenance and build command in a committed script
   (`scripts/build_geo.ps1` or `.js`, your call): the Natural Earth **scale**
   (1:110m or 1:50m), the **version**, the download URL, and the verbatim
   `mapshaper` invocation including simplification percentage.

The sibling then reproduces the file byte-identically rather than shipping a
second, subtly different world. Natural Earth is public domain, so there is no
licence question — only a reproducibility one.

### A3 — Run the palette validator with 5 categorical slots, not 3

`STATUS.md` lists "which Radix hues become the fixed categorical slots" as an open
decision, and `PLAN.md` §6.3 concludes 3 slots suffice here. That conclusion is
right for this project and wrong for the family.

The sibling's primary encoding is **bloc membership**, which needs at least five
categorical slots (a treaty-bound Western bloc, the China–Russia–DPRK–Iran
grouping, non-aligned, contested, and no-data). Validating a 5-slot ramp costs the
same single validator run as a 3-slot one, and the first three slots stay exactly
what this project would have chosen. Validating separately later risks two
palettes that were each fine alone and clash side by side.

So, when you get to the palette gate:

- Validate a **5-slot** categorical ramp against the dark surface.
- Commit the chosen values and the validator's **actual output** to
  `registry/palette.yaml` (or `web/public/data/palette.json` — either is fine,
  say which), including the sequential ramp, the diverging pair, the neutral
  midpoint and the reserved status colours.
- This project keeps using slots 1–3. The sibling reads the file and uses all five.

Adjacent-pair CVD ΔE ≥ 8 and normal-vision ΔE ≥ 15 remain the floors. Slots 4 and
5 are exactly where those floors start to bite, which is the argument for doing
it in one deliberate pass.

### A4 — Treat `meta.json`'s `schema_version` as a cross-repo contract

Already planned (§1). The only change is the promise: **semver, and bumped on any
breaking shape change**. The sibling asserts compatibility against it on load and
fails loudly rather than rendering a half-read bundle.

### A5 — Mark the portable half of `schema.py`

`Provenance`, `SourceRef`, `Geometry`, `to_jsonable` and the `Text` pattern are
not Canada-specific — they are the Athena vocabulary, and the sibling needs the
same one so that provenance means the same thing in both apps.

The ask is a **comment banner and one docstring line**, nothing structural:

```python
# ── Portable (Athena core) ─────────────────────────────────────────────────────
# Provenance, SourceRef, Geometry, to_jsonable and the Text pattern are shared
# with world-strategic-map. Changing their wire shape is a cross-repo break;
# bump meta.schema_version. Everything below the "Project-specific" banner is
# free to change without telling anyone.
```

Two notes for whoever eventually extracts this into a real shared package:

- `Text(en, fr)` is the boundary case. Bilingual EN/FR is a Canadian federal
  requirement, not a general one. The sibling will use a language-keyed map
  (`{"en": ..., "zh": ...}`) with the same `.get(lang)` fallback semantics. If
  these types are ever pulled into `athena-core`, `Text` generalises to the map
  and this project's pair becomes a two-key instance of it. **No change is needed
  now** — just don't let anything depend on `Text` having exactly two fields.
- `Geometry.provinces` is likewise Canada-shaped. The general form is a tuple of
  subdivision codes; the sibling's REGION geometry holds ISO3 country codes in
  the same slot.

---

## 4. What the sibling does not need

Stated so nobody builds any of it on its behalf:

- No new scraping, of anything.
- No changes to `atlas/sources/mpo.py`, the history mechanism, or `data/`.
- No API, no server, no shared database. The interface is committed files.
- No provincial, sector, company or MPO data. The sibling operates at country
  resolution and would have nowhere to put it.
- No changes to stages 01–03.

---

## 5. Summary for the impatient

| Ask | Where it lands | Cost |
|---|---|---|
| A1 `country.json` — ISO3 + 4 headline figures with `SourceRef` | `04_bundle.py` | ~30 lines, additive |
| A2 world geometry at a documented path + build script | `web/` scaffold | you were doing this anyway; add the script |
| A3 validate **5** categorical slots, commit the palette artifact | palette gate | same single validator run |
| A4 `meta.schema_version` is semver and honoured | `04_bundle.py` | a promise, not code |
| A5 portable/project-specific banners in `schema.py` | `schema.py` | a comment |

Questions about any of this go through Oscar; the sibling repo is
`C:\Code\world-strategic-map`.
