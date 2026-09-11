# CLAUDE.md — working in this repo

Read `STATUS.md` first. It records what is built, what is next, and the findings
that cost real work. This file is the invariants: things that are true by
decision and stay true unless a decision is revisited.

---

## 1. Federal text is reproduced, never authored

Everything under `data/events/` is the government's wording. Do not summarise,
paraphrase, round, or "clean up" a sentence.

In particular, **numbers embedded in prose stay in prose**. The pages say
"Will attract $5 billion in investment". Lifting that into `{"capex": 5e9}`
would be this project making a claim in a form the source never used. If a
number needs to be plotted, it comes from a machine-readable dataset, not from a
sentence.

Anything this pipeline computes is `Provenance.DERIVED` and is visibly labelled
as ours in the UI.

## 2. The frontend and the backend are the same object

Identity travels with the value. `web/src/data/bundle.ts` mirrors
`atlas/core/schema.py`; when they disagree, the dataclasses are right and the
TypeScript is the bug.

The app never re-derives a label, a total, or a rank. If the UI needs it, the
pipeline publishes it — including sector labels, which come from the StatCan
cube in both languages rather than being carried by us.

## 2b. Rendering a collection is a TOTAL function, never a filter

The map built markers from `kind === "point"` and lines from
`kind === "corridor"`. A corridor therefore got a line and **no marker** — no
headpiece, nothing to click, no way into the project — and four of eighteen
projects were unreachable on the map while every count, field and coordinate
check passed. Two filters over an open enum means anything matching neither
disappears silently, and `region` was queued to arrive next.

So: iterate the whole collection, decide per member, and make the decision
exhaustive. `mapFeatures()` returns one feature per site and `assertNever`
turns a new `GeometryKind` into a build failure. Every geometry that has
coordinates publishes an `anchor`, so there is always somewhere to put the
marker. `verify/`'s `records_are_reachable` gate asks the question no coverage
check can: of what we captured, how much can the reader actually reach.

A derived anchor is labelled as one. A corridor midpoint is arithmetic — the
source published the ends of the Mackenzie Valley Highway, never its middle —
so it carries `Provenance.DERIVED` and renders with a dashed ring.

## 3. Configuration is YAML, code is Python

`registry/` is the whole configuration surface: sources, events, strategies,
sectors, the GICS→NAICS crosswalk, the palette. All hand-editable, all validated
hard on load by `atlas/core/registry.py`.

Adding an event means adding a `registry/events.yaml` entry and one module under
`atlas/sources/`. Nothing in `web/` changes.

## 4. `verify/` must never import `atlas/`

Verification that imports the code it checks inherits that code's bugs.
`tests/test_pipeline.py::test_verify_does_not_import_atlas` AST-scans the
package and fails on any such import, so the rule is mechanical rather than
aspirational.

## 5. Nothing under `data/raw/` is committed

It is all re-fetchable input — HTTP cache, 34 MB of federal renderings, 28 MB of
StatCan cube zips, 129 MB of geometry downloads. The `.gitignore` rule is the
whole directory, deliberately: an earlier version listed `cache/` and `media/`
individually and 28 MB of zips were committed before anyone noticed. A
per-directory allowlist fails open.

## 6. Re-running a stage must produce a zero-line git diff

This is the acceptance test for every pipeline stage. Current-state files are
written only when content actually differs, which also gives `retrieved_at` a
better meaning: when the content was last seen to change, not when the scraper
last ran.

## 7. The palette is a validated artifact, not a preference

`registry/palette.yaml` was produced by converting every Radix dark step to
OKLCH, filtering to the dark lightness band, and running the dataviz validator.
The recorded output is in the file.

- **Five categorical slots, and five is the cap.** All-pairs normal-vision ΔE is
  15.9 against a floor of 15. A sixth slot breaks it. Six series means folding
  to "Other" or faceting — never adding a colour.
- **`--accent-*` is chrome; `--series-*` is data.** An accent picker may remap
  the former and must never touch the latter, or a validated palette silently
  becomes unvalidated on every accent change.
- Nothing in `web/src` hardcodes a data colour. Change the registry, re-run the
  validator, replace the recorded output.

## 8. Chained dollars are not additive

Measured: goods + services vs all-industries drifts **+0.311%** on the chained
basis and **+0.000%** on 2017 constant prices.

Any chart asserting that parts make a whole reads `national-constant.json`.
`verify/` gates this: the constant basis must be additive to within 0.01%.

## 9. Company data is market data, and says so

Index weight is not output. Company revenue is gross output while GDP is value
added, so summing companies within a sector overshoots that sector's GDP by two
to three times. The caveat is carried inside the bundle payload so the panel
cannot render the numbers without it. Never label this "top GDP contributors".

## 10. `meta.schema_version` is a cross-repo contract

Semver, bumped on any breaking shape change. `world-strategic-map` asserts
compatibility against it on load. `web/public/data/country.json` is its
integration surface — `headline` is a list so new figures append harmlessly.
See `docs/INTEROP-world-strategic-map.md`.

---

## Commands

```bash
python run.py            # whole pipeline, then verify
python run.py --stage 01 # one stage
python run.py --verify   # independent verification
python run.py --test     # pytest
cd web && npm run dev    # the app
node scripts/build_geo.mjs  # rebuild committed geometry
```

## House style

Numbered stage scripts at root, logic in the package. `# ── Section ──` banners.
Module docstrings explain *why*, and name the thing that went wrong before —
a comment that only restates the code is not worth the line. Pinned
dependencies. LF endings via `.gitattributes`.

## Things that fail silently — check `STATUS.md` before assuming

canada.ca doubles some content blocks but not others · French headings are
"Faits saillants" / "Dernière mise à jour" · the French StatCan cube is
semicolon-delimited · the French ArcGIS service has French field names · YAML
1.1 reads bare `ON` as `true` · Natural Earth `ISO_A3` is `-99` for five
countries · `setProjection` must be called inside `style.load` · SEPH
(14100201) is unadjusted and excludes agriculture — `[11N]` is forestry, never
NAICS 11 · the latest two capex years (34100035) are preliminary actuals and
intentions, said only in a note · 33100225 is non-financial balance sheets,
not revenue by industry.
