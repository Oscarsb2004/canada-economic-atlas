# CODE TOUR — what every file is for, and where it lies

_Written 2026-09-05 by reading the files on disk, not from memory. Every claim
about behaviour below was checked; every bug was reproduced against the
committed data before being written down._

> **All 13 findings were fixed on 2026-09-05.** Part III is kept as written —
> the record of what was wrong is worth more than a clean slate — with each
> finding's resolution appended. See **§ Resolutions** at the end for what
> changed and how it was verified.

Two jobs in one document:

1. **Explain the system** so you can open any file and know why it exists.
2. **Report discrepancies** — places where a comment promises something the code
   does not do, where two files disagree, or where the logic is wrong.

**Headline for the impatient:** nothing found puts a wrong *number* on screen.
The data path — scrape → parse → filter → publish → render — is sound, and
`verify/` covers it. The bugs are in the **interaction layer** (two filter
controls that silently do nothing) and in **latent assumptions** that are true
of today's data and will not stay true. Findings are in Part III with severities.

---

## 1. The system in one picture

```
   FEDERAL SOURCES                PYTHON PIPELINE              COMMITTED           WEB APP
   ───────────────                ───────────────              ─────────           ───────
   NRCan ArcGIS  ──┐
   canada.ca HTML ─┼─► 01_projects ─► data/events/  ─┐
   federal images ─┘                 data/history/   │
                                                     ├─► 04_bundle ─► web/public/data/ ─► fetch()
   StatCan WDS  ────► 02_sectors  ─► data/sectors/  ─┤                web/public/media/    │
   Bank of Canada ──┘                                │                                     ▼
                                                     │                            ┌────────┴────────┐
   iShares XIC  ────► 03_companies ─► data/companies/┘                            │ Globe   Sector  │
                                                                                  │ (left)  (right) │
   Natural Earth ──┐                                                              └─────────────────┘
   StatCan bounds ─┴─► scripts/build_geo.mjs ──────► web/public/geo/
```

Two things to internalise:

- **The pipeline never runs in the browser or in CI.** It runs on your machine,
  writes JSON, and you commit the JSON. The web app only ever reads committed
  files. This is why the app has no loading states beyond one fetch and no
  server.
- **`verify/` is a separate universe.** It re-reads the same JSON with the
  standard library and re-checks it using different logic. It is forbidden from
  importing `atlas/`, and a test enforces that.

## 2. Five invariants that explain most of the code

If a decision looks strange, it is almost always one of these.

1. **Federal text is reproduced, never authored.** No summarising, no rounding,
   and numbers embedded in prose stay in prose. This is why `Project` has no
   `capital_cost` field even though nine of eighteen pages mention a dollar
   figure.
2. **The frontend and the backend are the same object.** `web/src/data/bundle.ts`
   mirrors `atlas/core/schema.py` field for field. The UI never re-derives a
   label, a total or a rank.
3. **Configuration is YAML, code is Python.** Everything the project *covers*
   lives in `registry/`; everything it *does* lives in `atlas/`.
4. **Re-running a stage must produce a zero-line git diff.** Outputs are written
   only when content actually changed.
5. **Colour is a validated artifact, not a preference.** `registry/palette.yaml`
   holds the recorded validator output. Nothing in `web/src` hardcodes a data
   colour.

---

# Part I — the Python pipeline

## `atlas/core/schema.py` — the vocabulary

**Intent.** One definition of every object that crosses a boundary, so the
pipeline, the web app and the verifier cannot drift apart.

**What it actually does.** Frozen `slots=True` dataclasses plus two string enums.
The file is split by a banner into a *portable* half (`Provenance`, `SourceRef`,
`Geometry`, `Text`, `to_jsonable` — shared with the sibling repo) and a
*project-specific* half. `Series.__post_init__` is the only validation: it
rejects a series whose `periods` and `values` have drifted out of alignment.

Worth understanding: **`Site` exists because of one project.** The ArcGIS layer
publishes 20 features for 18 projects — the North Coast Transmission Line ships
three separately-named phase points that all link to one page. Rather than
inventing a route between them, each is a `Site` and each gets its own pin.

`to_jsonable` walks objects by field and calls a type's own `to_dict` when it has
one. It deliberately does **not** use `dataclasses.asdict`, which recurses
eagerly and would flatten nested types before their `to_dict` ever ran.

## `atlas/net.py` — the only way out to the internet

**Intent.** Every outbound request through one object, so politeness settings
cannot drift between modules.

**What it actually does.** ~1 req/s throttle, descriptive User-Agent, retry with
exponential backoff on transient statuses, and an on-disk cache keyed on the
SHA-256 of the URL. `post_json` is deliberately **not** cached — the cache keys
on URL alone, so caching a POST would serve one request body's answer to a
different body.

Explicitly *not* carried over from the sibling ASI project: a process-wide
`verify=False` monkey-patch. TLS verification stays on.

> ⚠ **See Finding 4.** The cache has no expiry and is on by default, which
> defeats the project's own change-detection story.

## `atlas/core/registry.py` — configuration, validated on load

**Intent.** Fail where the mistake is, not three stages later.

**What it actually does.** `lru_cache`d loaders for `sources.yaml`,
`events.yaml`, `strategies.yaml`, each cross-validating: a source must declare a
licence that exists; an event must reference sources that exist; a province code
must be a real two-letter string.

The province check has a specific guard worth knowing: YAML 1.1 reads bare `ON`
as boolean `true`. An unquoted `provinces: [ON, QC]` loads as `[True, "QC"]` and
silently drops Ontario. The codes are quoted in the YAML, and the loader rejects
non-strings with an explanatory error.

## `atlas/sources/mpo.py` — the Major Projects Office parser

**Intent.** Turn a federal HTML page into structured records without changing a
word of it.

**What it actually does.** The important part is `strip_mobile_twins()`, which
runs once before anything is read. canada.ca emits the Proponent/Sector/Location
cards **and the whole Description** twice — once in a `visible-md visible-lg`
wrapper, once in `visible-xs visible-sm`. Quick facts, Benefits and Latest
updates are **not** doubled. So deduplicating by repeated text would delete real
content while missing the actual duplicates; the fix has to be structural.

Three tables encode things that fail silently if guessed:

- `HEADINGS` — French sections are "Faits saillants" and "Dernière mise à jour"
  (singular), not the plausible alternatives. A wrong heading yields zero facts
  and raises nothing.
- `FIELDS` — the French ArcGIS service has French *field names* (`Nom`,
  `Promoteur`, `Etat`, `Lien`) and its `Lien` points at the French page, so the
  two services share no URL and must join on the slug.
- `_SPACE_BEFORE_PUNCT` — restricted to `, . ) ]`. French requires a space
  before `: ; ! ?` and `%`, so a broader rule would rewrite correct French and
  call the result verbatim.

`slug_from_url` validates against `^[a-z0-9][a-z0-9._-]*$` because the slug
becomes a filesystem path.

## `atlas/sources/statcan.py` — bulk cube download

**Intent.** Get whole StatCan tables cheaply and correctly.

**What it actually does.** Downloads the entire cube as one zip rather than
pulling series vector-by-vector — simpler, atomic, and immune to the
undocumented 300-vector POST cap.

`read_cube` **detects the delimiter**. The English cube is comma-separated and
the **French cube is semicolon-separated** (the European convention, since French
uses the comma as a decimal mark). Parsing the French file with a comma yields
one enormous column per row, raises nothing, and leaves every French label empty
while the English side looks perfect.

`code_of()` parses the join key out of the label itself — `Manufacturing [31-33]`
— so the code and the label always agree and neither is carried by us.

## `atlas/sources/companies.py` — index constituents

**Intent.** Answer "which large listed companies operate in this sector" without
ever implying "which companies contribute most to GDP".

**What it actually does.** Parses the iShares XIC holdings CSV past its two-line
preamble, drops non-equity rows and zero-priced stale rows with counts logged,
and attaches NAICS codes from the crosswalk. `_num()` strips thousands
separators — a bare `float()` raises on nearly every large row, which is how a
naive reader ends up with only the small constituents.

Everything is `Provenance.MARKET_DATA`. The module docstring states the reason
plainly: GDP is value added, company revenue is gross output, so summing
revenues within a sector overshoots that sector's GDP by two to three times.

## `atlas/media.py` — derived imagery

**Intent.** Turn 34 MB of federal renderings into two committable sizes.

**What it actually does.** A 96 px circular thumbnail (real alpha crop, not a CSS
`border-radius`, because a MapLibre marker sits on the globe and a square's
corners show against the terrain) and a ~1400 px JPEG. The circular mask is drawn
at 4× and downsampled so the edge is antialiased.

## `pipeline/01_projects.py` … `04_bundle.py`

Numbered stages at root, logic in the package. Each writes only when content
changed, which is what makes the zero-diff guarantee testable.

- **01** joins ArcGIS geometry to scraped pages, groups the 20 features into 18
  projects on the page link, derives images, and appends to `data/history/`
  **only when the content hash moves**.
- **02** pulls the cubes, checks the goods+services partition, and pulls the
  Bank of Canada policy rate.
- **03** builds the company panel and carries its caveat *inside the payload*, so
  the UI cannot render the numbers without it.
- **04** copies everything into `web/public/data/`, and writes the three files
  that only exist at this stage: `meta.json` (the contract), `country.json` (the
  sibling repo's integration surface) and `palette.json`.

## `verify/run.py` — independent checking

42 gate checks. The ones that earn their keep are the ones that catch *plausible*
wrongness: coordinates must fall inside Canada's bounding box (a lat/lon swap
lands in the Indian Ocean and otherwise looks like data), periods must be ordered
and unique (a repeated month passes every other check), and referenced images
must **exist**, not merely be referenced.

---

# Part II — the web app

## `web/src/data/bundle.ts` — the contract, in TypeScript

Mirrors `schema.py`. When they disagree, **the dataclasses are right and the
TypeScript is the bug**. Loads everything in one parallel fetch (~1.4 MB plus
385 KB of geometry — less than a single map tile, which is why there is no lazy
loading anywhere) and asserts the schema major version before returning.

`asset()` resolves site-absolute paths against `BASE_URL`. It exists because
paths *inside* the committed JSON are not visible to Vite's import graph, so a
GitHub Pages project site would 404 every image.

`safeExternalUrl()` allowlists http(s) before any scraped URL reaches an `href`.

## `web/src/map/Globe.tsx`

One library does both views: MapLibre v5's globe projection transitions to
Mercator around zoom 12, so the world view and the drill-down are the same map.

Two things that cost real time and are now commented in place:

- **`setProjection` must be called inside `style.load`.** Before the style is
  ready it throws and the map renders blank.
- **The `background` layer paints the sphere, not the canvas.** Under globe
  projection it *is* the ocean; space is the container's CSS background.

The init effect has **no `if (map.current) return` guard**, deliberately. That
guard fights React StrictMode's mount→unmount→mount: the second setup bails while
the first map is torn down, leaving a live canvas whose map object is destroyed.

Pins carry **no sector colour**. Map markers are an all-pairs form, which the
validated palette caps at three categorical slots, and the MPO publishes five
sector values. The pin's face is the project's own rendering, which identifies it
better than a hue could.

## `web/src/charts/` and `panels/SectorPanel.tsx`

`Plot.tsx` owns the imperative ref/effect dance once and holds the mark specs, so
no individual chart restates bar thickness or line width. `specs.ts` is one
builder per question — the form is chosen before the colour, which is why there
is no single "sector chart" that tries to do everything.

The composition chart uses **two** series and not twenty because twenty stacked
NAICS sectors would cycle categorical hues past eight; and it reads
`national-constant.json` because chained dollars are non-additive (+0.311%
measured) while a stacked chart asserts that the parts make the whole.

## `web/src/tabs/store.ts`

A pin stores the **question**, not the answer: `{kind, params, label}` re-renders
against current data, so a tab pinned last month shows this month's figures.

---

# Part III — findings

Ordered by whether they affect a reader today.

## Live bugs — visible in the running app

### F1. The Range filter does nothing on the Heatmap view · **medium**

`web/src/panels/SectorPanel.tsx:172-174`

```tsx
deps={[bundle.national, width, bundle.palette]}
spec={() => growthHeatmap(bundle.national, bundle.palette, width, months || 360)}
```

`months` changes the output but is **not in `deps`**. `PlotFigure` re-runs its
effect only when `deps` change, so switching 5 years / 10 years / All re-renders
the component, builds a new closure, and never redraws the chart. The control is
silently inert.

**Fix:** add `months` to `deps`.

### F2. The Range filter does nothing on the Growth view · **medium**

`web/src/panels/SectorPanel.tsx:137-138`

```tsx
deps={[national, width, bundle.palette]}          // windowed
spec={() => growthBars(bundle.national, ...)}     // UNWINDOWED
```

The inverse mistake: the dependency is the windowed series, so the effect *does*
re-run on a range change, but the spec reads the unwindowed data, so the output
is identical every time. Wasted renders and an inert control.

Arguably y/y-at-latest-month is range-independent by nature — but then the
control should be hidden on this view rather than present and dead.
`FilterRow`'s own docstring claims "filters scope everything below them", and on
two of five views that is false.

**Fix:** pass `national`, or disable the Range group for this view.

### F3. The y-grid is drawn twice, and once unthemed · **low**

`web/src/charts/Plot.tsx:69` sets `y: { grid: true }` for every chart, and
`specs.ts` adds a themed `gridY()` mark on top for composition and emphasis. So
those two charts have overlapping grids, and the other three show only Plot's
default grid, which does not use the palette token.

**Fix:** drop `grid: true` from `chartDefaults` and add `gridY()` where wanted,
or drop the mark and theme the axis. Not both.

## Design-level — a documented guarantee that does not hold

### F4. The HTTP cache defeats change detection on a default run · **high**

`atlas/net.py:126-141`, all three scraping stages.

The cache has **no expiry** and is **on by default**. `python run.py` therefore
re-reads cached federal pages forever. The consequences run right through the
project's central story:

- `data/history/` is append-only *and conditional on the content hash moving*.
  Served from cache, the hash never moves, so **the history mechanism cannot
  fire on a default run**.
- The sitemap `<lastmod>` change-detection described in `PLAN.md` §3.6 is
  likewise blind.
- `STATUS.md` says a re-run produces a zero-line diff and presents that as proof
  the scrape is deterministic. It is currently also consistent with the scraper
  never looking at the network at all.

Nothing is *incorrect* — the committed data is right — but a guarantee the docs
lean on is weaker than it reads.

**Fix (pick one):** a TTL on cached entries; or `--refresh` as the default for
stage 01 with `--cached` as the opt-in; or exempt the sitemap/index pages from
caching so change detection always sees live `lastmod` values. The third is
cheapest and targets the actual need.

## Latent — correct today, wrong on plausible future data

### F5. `yoyBySector` reads the last index, not the last non-null · **medium (latent)**

`web/src/charts/specs.ts:104-107`

```ts
const now  = s.values[n - 1];
const then = s.values[n - 1 - step];
```

`latestBySector` (line 90) correctly walks backwards to the last non-null.
`yoyBySector` does not. If StatCan publishes a sector one month behind the rest —
routine, and suppression happens too — that sector **silently disappears** from
the growth chart and its table, with no note. Ranking would still show 20 rows
while growth showed 19.

Verified against the committed data: no sector currently has a null final value,
so this is latent rather than live. Sector 55 has 120 nulls in its early
history, so nulls in this dataset are real, not hypothetical.

**Fix:** find the last non-null index, then look 12 rows back from *that*.

### F6. `yoyBySector` hardcodes a 12-period step · **low (latent)**

Same function, `const step = 12`. Correct for monthly. Called with the annual
provincial series it would compare **2025 against 2013** and label the result
"year-over-year". Nothing calls it that way today.

**Fix:** derive the step from `series.frequency`, which every `Series` carries.

## Code that says one thing and does another

### F7. A comment describing behaviour the code does not implement

`web/src/charts/Plot.tsx:72-73`

```ts
// Hairline, solid, one step off the surface. Recessive by construction.
...({ } as object),
```

Spreading an empty object. The comment promises grid styling that this code does
not apply — see F3 for where the styling actually (partly) happens.

### F8. A dead guard

`web/src/tabs/TabStrip.tsx:32`

```ts
const pinned = pins.length >= 0 && isPinned(kind, params);
```

`pins.length >= 0` is **always true**. It was presumably meant to force a
subscription to `pins`, but `useTabs((s) => s.pins)` on the line above already
does that. Pure noise that reads like a meaningful condition.

### F9. A misleading verifier diagnostic

`verify/run.py`, `check_projects`

```python
fr_gaps = [ f'{p["slug"]} qf {len(p["quick_facts"])}'
            for p in projects if not p["description"]["fr"] ]
r.gate(not fr_gaps, "every project has a French description", str(fr_gaps))
```

The predicate tests the French *description*; the failure message reports the
*quick-facts count*. If this ever fires, it points at the wrong field.

### F10. A parameter named for the wrong directory

`atlas/media.py:111-112` — `derive(src, media_root, ...)` immediately does
`media_root.parent / thumb_rel`. It is called with `WEB_MEDIA_DIR`
(`web/public/media`) and wants `web/public`. It works, but the name is wrong and
a caller who passes the actual public root gets silently wrong paths.

### F11. `_strip_volatile` is inconsistent across stages

Stage 01 strips `generated_at` **and** `retrieved_at`; stages 02, 03 and 04 strip
only `generated_at`. Harmless today because the values that would differ happen
to be stable, but it is the kind of inconsistency that makes a future
"why did this file rewrite?" hard to answer.

### F12. A type assertion that is not true

`web/src/tabs/store.ts:114` — `partialize: (s) => ({ pins: s.pins }) as TabsState`.
The returned object is not a `TabsState`; the cast silences the compiler about a
shape that is intentionally partial. Zustand's own typing wants a partial here.

### F13. A source-shape change yields zero rows rather than an error

`atlas/sources/statcan.py`, `build_series`. `cell()` returns `""` for a missing
column, and the filter then rejects every row. So a renamed StatCan column or a
renamed filter value produces an **empty series list**, not an exception.

This is caught downstream — `verify/` fails on "every registry sector is
present" — so it is loud eventually. But it is loud in the wrong place, and the
error will read as "the registry is wrong" rather than "the cube changed shape".

---

## What I would fix first

1. **F4** — it undercuts the change-detection story the project is built on.
   Exempting index/sitemap fetches from the cache is a small change.
2. **F1 and F2** — two controls that silently do nothing are the only findings a
   user will actually hit.
3. **F5** — cheap, and the failure mode (a sector vanishing without explanation)
   is exactly the kind of silent wrongness the rest of the project works hard to
   avoid.
4. **F7, F8, F9** — delete or correct. Comments that misdescribe code are worse
   than no comments, because they are trusted.

Everything else is housekeeping.

## What held up

Worth saying, since the point of a review is to be told both:

- No finding produces an incorrect figure. Values, units, vintages and
  provenance are correct throughout, and `verify/`'s 42 checks genuinely
  constrain the data rather than restating it.
- The parsing quirks that fail silently — doubled markup, French headings, the
  semicolon delimiter, the French field names, YAML's boolean coercion — are all
  handled, tested, and documented where they happen.
- The security posture is sound: TLS on, no credentials, no `innerHTML`, scraped
  URLs allowlisted, slugs validated before they touch the filesystem.


---

# Resolutions — 2026-09-05

Each fix went to the root cause rather than the symptom. Three of the findings
had an obvious fix that would not actually have worked; those are marked.

| # | Fix | Verified by |
|---|---|---|
| **F1** | `months` added to the heatmap's `deps` | Heatmap redraws at 1200 / 2400 / 6720 cells for 5y / 10y / All |
| **F2** | Range **disabled** on latest-period views, not faked | Range enabled on Composition/Trends/Heatmap, disabled with an explanatory title on Size/Growth |
| **F3** | `grid: true` removed from `chartDefaults`; the themed `gridY()`/`gridX()` marks are now the only grid | Build clean, charts render |
| **F4** | 24-hour cache TTL + hit/fetch/expiry accounting | `test_cache_entries_expire` |
| **F5** | `yoyBySector` walks back to the last non-null | 25 tests pass; `lastRealIndex` shared with `latestBySector` |
| **F6** | Step derived from `series.frequency` | Same |
| **F7** | Dead spread and its false comment deleted | — |
| **F8** | Subscribe to the derived boolean instead of the always-true guard | Typecheck clean |
| **F9** | Diagnostic reports the field the predicate tested | 42 gate checks pass |
| **F10** | `derive()` takes `public_root`; `WEB_PUBLIC_DIR` added to the registry | Stage 01 re-run, images intact |
| **F11** | Four copies replaced by `atlas/core/jsonio.py` | `test_write_if_changed_ignores_only_volatile_keys` |
| **F12** | `partialize` typed `Pick<TabsState, "pins">` | Typecheck clean |
| **F13** | Missing filter column or unmatched value now raises, naming what it looked for | `test_cube_filter_mismatch_raises_instead_of_yielding_nothing` |

## Three fixes that were not the obvious one

**F4 — "exempt sitemaps from the cache" would not have worked.** The history
mechanism hashes *project page* content, so exempting index pages would still
have served an edited Crawford page from cache and the hash still would not have
moved. The real axis is staleness, not URL class, so the fix is a **TTL**: 24
hours, which keeps same-session re-runs free while a next-day run sees what the
government changed. `Fetcher` now also counts hits, fetches and expiries, so a
run says how much of it came off disk — a fully cached scrape and a scrape that
genuinely found no change used to look identical in the output.

**F2 — "pass the windowed data" would not have worked either.** `growthBars`
computes y/y at the *latest* month, and a window never moves the latest month.
Range is genuinely meaningless there. So the honest fix is to stop offering the
control: `VIEWS` gained a `usesRange` flag, and the Range chips render disabled
with the title "This view reads the latest period only". A live-looking dead
control makes the reader doubt the data rather than the UI.

**F11 — fixing the four copies would have left the class of bug.** The
inconsistency was a symptom of `_strip_volatile`/`_write_if_changed` being
copy-pasted into every stage. Extracting `atlas/core/jsonio.py` removed the
drift and the possibility of it recurring, and gave the rule one place to be
stated.

## Verified after all 13

Full pipeline end to end · 25 tests · 42 gate checks · production build clean ·
a re-run from a clean baseline leaves a zero-line git diff · Range control
behaviour confirmed in a browser across all five views.
