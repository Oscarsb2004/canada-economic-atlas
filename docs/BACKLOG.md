# BACKLOG — the ordered work queue

One queue, in dependency order. Each item is self-contained enough to hand to a
session cold. `Human?` means it cannot finish without a decision only you can
make — those are the bottleneck, and they are marked so they can be batched.

Effort: **S** under an hour · **M** a few hours · **L** a day or more.

Same pattern as `world-strategic-map/docs/BACKLOG.md` and
`African-Stability-Index/methodology/BACKLOG.md`, so the three read side by side.
The division of labour between the four documents in this repo is deliberate:

| File | Answers |
|---|---|
| `docs/PLAN.md` | what this is for, and the §10 scope fence |
| `docs/ROADMAP.md` | **what is defensible** — the analysis behind the items below |
| `docs/CODE-TOUR.md` | what every file does, and the review findings |
| `STATUS.md` | what is **built**, and the findings that cost real work |
| **this file** | **what to do next in this repo, in what order** |
| [`docs/PROGRAM.md`](PROGRAM.md) | **the long-term plan across all three repos** — milestones, the dependency graph, the shared spine and the launcher |

`ROADMAP.md` is not superseded by this file and should not be folded into it. It
carries the reasoning — why MPI's capital ceiling is 6-of-18 and structural, why
an input-output multiplier is defensible and a completion-probability score is
not — and that reasoning is what stops an item here being done the wrong way.

---

## The five goals, and how you know each is met

Every item names the goal it serves. An item serving none should not be done,
however reasonable it looks alone.

### G1 · Reproduction, never authorship

> *"we should scrape the data in a format that captures all of the original
> text. Not writing any of it ourselves."*

The government's wording is reproduced; anything this project computes is
`DERIVED` and visibly ours. Numbers embedded in prose stay in prose.

**Done when:** every field on screen traces to a `SourceRef` or is labelled
derived, and the two never share a visual grammar. Currently true, and the thing
most at risk as Stages C and D add inference where v1 had only reproduction.

### G2 · The portfolio and the economy are one object

> *"an interactable view of 'Canada in the world' … sector-by-sector time-series
> analysis of Canadian growth."*

v1 shipped these as two things next to each other. The map knows nothing about
the charts, and the charts know nothing about the projects.

**Done when:** you can ask *what is being built in this sector, and how big is
that sector* and get one answer — pin count and capital by NAICS sector, beside
that sector's GDP, with the crosswalk's losses stated.

### G3 · Analysis of the baseline economic information

> *"The primary goal of the right side is visualizations of charts and different
> ways to analyze the baseline economic information."*

Nine chart forms exist. Four of seven declared StatCan tables are unpulled, so
the analyses that matter most — productivity, contribution to growth, gross
output vs value added — are not yet possible at all.

**Done when:** all seven declared tables are pulled and the five analyses in
`ROADMAP.md` §B2 are available as views.

### G4 · A structure for countries and events, not a Canada page

> *"Think about ways to design this as a structure for presenting countries,
> Canada as the main in depth one, events which are personally selected."*

Adding an event should be a `registry/events.yaml` entry plus one module under
`atlas/sources/`, with nothing in `web/` changing.

**Done when:** a **second** event ships without touching `web/`. Until that
happens the claim is untested — one event and a generic loader look identical.

### G5 · Currency stated, not implied

The pipeline already knows things the UI hides: nominal GDP is ~3 years stale,
provincial data lags ~4 months, chained dollars are non-additive by +0.311%, and
`retrieved_at` means *last seen to change*, not *last checked*.

**Done when:** a reader can see how fresh every figure is without opening a file,
and `--verify` fails on a source past its expected refresh interval.

---

## Stage A — v1 · **DONE**

| | Item | Goal | Effort |
|---|---|---|---|
| A1 | ~~Schema, registry, polite fetcher, MPO parser~~ | G1 | L |
| A2 | ~~Committed geometry, reproducible and tool-pinned~~ | G4 | M |
| A3 | ~~Four pipeline stages, zero-line diff on re-run~~ | G1 | L |
| A4 | ~~Globe, pins, verbatim project viewer~~ | G1 G2 | L |
| A5 | ~~Nine chart forms, filter row, table twins, choropleth~~ | G3 | L |
| A6 | ~~Pinned tabs, tooltips, accessibility pass~~ | G3 | M |
| A7 | ~~`verify/` (47 gates), 29 tests, `run.py`, `CLAUDE.md`~~ | G1 | M |
| A8 | ~~Locked palette, 5 validated categorical slots~~ | G3 | M |
| A9 | ~~Benefits bullets · real coastline highlight~~ | G1 | M |
| A10 | ~~Canada's fill matched to its coastline; declarative `registry/checks.yaml`; coverage manifest read from the source's own index~~ | G1 G4 | M |

---

## Stage B — finish what is already paid for

Every item here renders or pulls something the expensive part of which is
**already built and committed**. This is the highest value per hour in the repo
and it is not close.

| | Item | Goal | Effort | Human? |
|---|---|---|---|---|
| B1 | ~~**Language toggle.** EN / FR in the map layer bar, remembered per browser, and `?lang=fr` in a link. Data text comes from the bundle's own French; interface text lives in `web/src/i18n.tsx`, typed so a missing French string fails the build; numbers and dates come from the fr-CA locale. It was not "one control through the props that already accept `lang`" — twelve components rendered English directly, including every chart label, so the effort was M, not S.~~ | G1 G4 | M | |
| B1a | **French for the fields the pipeline carries in English only:** an MPO project's sector, a site's location wording, an update's date as written, GICS sector and company names, and the map's source credits. Capture each from its French source in stages 01 and 03 — never translate them in the app, which would be authoring a publisher's text. | G1 | S | |
| B1b | **Review the interface French.** Everything under `fr` in `i18n.tsx` was written by this project, not a translator. Section headings already match the federal pages ("Faits saillants", "Avantages", "Dernière mise à jour"); the rest needs a fluent reader's pass. | G1 | S | ✓ |
| B2 | ~~**Pull the declared-but-unused StatCan tables.** Three landed: nominal GDP `36100710` (current dollars, verified), capex `34100035` (every period labelled actual / preliminary actual / intentions from the cube's own note, quality grades carried), SEPH employment `14100201` (streamed — ~1 GB per language; combined codes aliased; agriculture declared absent). Each gated on identities measured before the tolerance was set. They were NOT "registry entries, not new code": that claim was written before the cubes were read.~~ | G3 | M | |
| B2a | ~~**Gross output by industry — option A, chosen 2026-09-11.** `36100488` *Output, by sector and industry, provincial and territorial*: current dollars, 1997–2022, the same accounts and years as nominal GDP. It is classified by IOIC, not NAICS, and split into business / non-profit / government members, so the twenty sectors are a `DERIVED` crosswalk read from the NAICS code each member embeds. 52, 53 and 55 separate only below the `BS5B0` aggregate; `NP999999` (no NAICS code) stays `unallocated`. Gated: members sum to the cube's own total (0.008%), output is never below value added in any sector-year, provinces + territories + enclaves abroad sum to Canada. `33100225` stays unpulled.~~ | G3 | M | |
| B2b | **A deeper statistical section — later, scope to be decided.** B2 and B2a are deliberately the basic layer: whole sectors, one slice per table, no views. An overhaul could go below the twenty sectors (IOIC detail, SEPH's four-digit industries, capex by asset type), add a seasonally adjusted employment table, reproduce StatCan's own productivity measures (`36100713`, 2011–2025) instead of dividing GDP by SEPH, separate owner-occupied dwellings from market activity in NAICS 53, and extend gross output past its 2022 end. | G3 | L | ✓ |
| **B3** | **Portfolio timeline.** 86 dated updates across 18 projects, each with `date_verbatim` and a verbatim body, captured since day one and never rendered. Filterable by project and sector. Pure reproduction — no new claims. | G1 G2 | M | |
| **B4** | **"What changed" view** off `data/history/`. Federal pages are edited in place — Crawford gained a March 2026 update long after its November 2025 referral. Showing *when the government changed what it said* is something no other view of this data offers. The history is append-only and only moves on real content change, which is what makes the view trustworthy. | G1 G5 | M | |
| B5 | **Vintage panel.** `meta.json` and every `release_time` are already carried; surface them where the reader is rather than in a footer. State the ~3-year nominal lag and the ~4-month provincial lag as facts about the source. | G5 | S | |
| B6 | **Policy annotations on the sector charts.** `events.yaml` carries `kind: policy_with_projects` and a date precisely so a policy can be a vertical rule on a GDP chart. Nothing renders it. | G2 | S | |
| **B7** | **Render the nine transformative strategies.** They are scraped, name-checked in both languages, hand-mapped to provinces in `strategies.yaml`, committed to `strategies.json` — and `Globe.tsx` and `App.tsx` contain **zero** references to them. Nine of the twenty-seven referred items are invisible, which is what "some of them are missing" looks like from the outside. They have no geometry (ArcGIS layer 2 returns empty polygons), so they render as province washes plus a list, never as pins — and `alto` stays `render: list_only`, because filling Ontario and Quebec entirely would claim a footprint ~100× the real one. | G2 G4 | M | |
| B8 | **A map error handler.** `Globe.tsx` registers none, so a bad layer spec or an unparseable source fails silently and the globe just renders less. Two rendering problems this week were diagnosed by squinting at screenshots because nothing was listening. `map.on("error")` into the console, and a visible banner in dev. | G5 | S | |

## Stage C — join the two halves

This is G2, and it is where the app becomes one thing. Read `ROADMAP.md` §A2 and
§A3 before starting: both items have honest limits that must reach the UI.

| | Item | Goal | Effort | Human? |
|---|---|---|---|---|
| **C1** | **MPO sector → NAICS crosswalk.** `registry/mpo_naics.yaml`, hand-curated, versioned, splits documented, marked `DERIVED` — the same treatment `gics_naics.yaml` gets. Lossy in a specific way that must be written down: MPO "Energy" spans NAICS 21, 22 and 486; MPO "Transport" is mostly NAICS 23 construction *activity* producing a 48-49 *asset*. Say which is meant. | G2 | M | ✓ |
| **C2** | **Capital values from NRCan's Major Projects Inventory,** joined through a curated `registry/mpi_join.yaml` — explicit slug→Project-ID pairs, hand-checked. Not fuzzy matching, which got 6/18 and would silently mismatch as either list grows. | G2 G3 | M | ✓ |
| **C3** | **State the 6-of-18 ceiling in the UI.** MPI's universe is Energy/Mining/Forest only; the MPO portfolio also spans Transport, Electricity and Industrial, which MPI does not track. Show "not published" where there is no figure and **never total across the partial set**. A "$X billion portfolio" headline from six of eighteen projects is wrong by construction, and this item is what stops C2 becoming that. | G1 | S | |
| C4 | **Pin count and capital by NAICS sector, beside that sector's GDP.** The view the whole layout implies and cannot currently produce. | G2 G3 | M | |
| C5 | **Project → province by point-in-polygon**, then capital as a share of provincial GDP. Defensible, and striking for the territories: Yukon's entire 2025 GDP is $3,243M and the DGR alone is $26,000M. | G2 G3 | M | |

## Stage D — the analyses B2 unlocks

| | Item | Goal | Effort | Human? |
|---|---|---|---|---|
| **D1** | **Contribution to growth**, properly weighted. The app shows y/y change per sector; the standard decomposition is each sector's *share* of total growth. A small sector at +12% and a huge one at +1% look opposite in the current view and identical in this one — and the second is the one that answers "what moved the economy". | G3 | M | |
| D2 | **Productivity** — real GDP per worker by sector, over time. SEPH is now pulled, and two facts shape the view: it is **unadjusted** for seasonality while GDP is adjusted at annual rates, so compare annual averages (or add a seasonally adjusted SEPH table); and it **excludes agriculture**, so NAICS 11 gets no productivity figure at all rather than forestry jobs against farm output. | G3 | M | |
| D3 | **Volatility and cyclicality** — rolling standard deviation, and each sector's correlation with all-industries. Which sectors *are* the business cycle and which ride through it. | G3 | M | |
| D4 | **Provincial specialisation** — location quotients. Standard, defensible, and the natural bridge to C5. Mark `DERIVED`. | G3 | M | |
| D5 | **Gross output vs value added by sector.** Unblocked by B2a: gross output (`output-annual.json`) is on the same accounts and years as nominal GDP. The ratio is `DERIVED`, and so is the IOIC crosswalk under the output — say both on the chart. Makes the companies-panel caveat *visible* rather than a footnote — you could show directly why summing company revenues overshoots sector GDP two- to threefold. | G1 G3 | M | |

## Stage E — keep it honest

The strongest part of the repo already. These extend it rather than repair it.

| | Item | Goal | Effort | Human? |
|---|---|---|---|---|
| **E0** | **Declare the remaining datasets in `checks.yaml`.** Sectors, companies and `country.json` still have hand-written checks in `verify/run.py` that name their fields inline. Those are correct today and are exactly what stops working when a second event arrives. Port them; keep only genuinely bespoke logic in Python. | G4 | M | |
| **E1** | **Staleness gate.** `--verify` fails when a declared source is past its expected refresh interval. Add `refresh_interval_days` to `sources.yaml`. This is the mechanism that makes G5 real rather than intended, and it is the direct analogue of `world-strategic-map` E3. | G5 | S | |
| E2 | **Gating vs advisory tiers** in `verify/run.py`, as ASI already has. *Blocking a release on a judgement call trains people to ignore the gate.* Two of the current 49 lines are already `note` rather than `gate`; make the distinction structural. | G1 | S | |
| E3 | **Scheduled refresh.** A GitHub Action that re-runs the pipeline and opens a PR when a federal page or a StatCan cube changes. The 24h cache TTL and the append-only history make this safe: a no-change run produces a zero-line diff and no PR. **Not** a build-time scrape — CI hitting canada.ca on every push would be impolite and would let one commit produce different sites. | G5 | M | |
| E4 | **`DERIVED` becomes load-bearing.** As Stages C and D land, derived values stop being rare. Audit that the UI still renders a crosswalk, a location quotient and an official figure differently. This is G1's regression test and it cannot be automated — it is a look-at-the-screen pass. | G1 | S | ✓ |

## Stage F — the second event, and the second country

**This is the only test of G4 that means anything.** One event and a generic
loader are indistinguishable until there are two.

| | Item | Goal | Effort | Human? |
|---|---|---|---|---|
| **F1** | **Pick the second event.** A landmark policy change with geolocatable consequences and published text — the Building Canada Act listings, a budget's capital measures, an interprovincial trade agreement. The choice is yours and it constrains everything below. | G4 | S | ✓ |
| **F2** | **Ship it: one `events.yaml` entry, one `atlas/sources/` module, nothing in `web/`.** If `web/` has to change, the structure claim is false and the fix belongs in the loader, not in the event. | G4 | L | |
| F3 | **Announcement scraping** (`PLAN.md` §3.6, specified and never built): four hosts, seeded from the MPO news index, change-detected via sitemap `<lastmod>`. The only way a new project gets noticed automatically, and the raw material for B3's timeline. | G4 G5 | L | |
| F4 | **Second country, if ever.** `country.json` is already the contract and generalises. Do not start this before F2 — a second country whose event structure is still untested is two unproven abstractions at once. | G4 | L | ✓ |

## Stage P — the platform

The family question. Three repos now share a spine that was copied rather than
shared, and you have asked for one place to see and run them all.

### What is actually duplicated — measured, not assumed

| Concern | `African-Stability-Index` | `canada-economic-atlas` | `world-strategic-map` |
|---|---|---|---|
| venv-bootstrapping entry point | `run_asi.py` | `run.py` (copied "almost verbatim", says its own docstring) | `run.py` — **no bootstrap** |
| polite cached fetcher | ad hoc, and monkey-patches `verify=False` process-wide | `atlas/net.py` | `wsm/net.py` |
| change-detection hashing | — | `atlas/core/jsonio.py` | `wsm` `comparable_json` |
| `verify/` that must not import the package | yes, with an AST test | yes, with an AST test | wanted (E1) |
| `SourceRef` / `Provenance` | partial | `schema.py`, banner-split portable vs project | "portable Athena core" |
| `world.json` | — | canonical | **byte-identical copy, verified 2026-09-06** |
| validated palette | own | `registry/palette.yaml`, the only validated one | needs categorical slots |

Two facts sharpen this. The atlas's `jsonio` and WSM's `comparable_json` solve
the same problem, and **WSM's version found a bug the atlas's still has in
principle**: stripping `accessed_at` from `meta` while every `SourceRef` carries
its own copy re-admits what you excluded. One implementation would have fixed
both. And ASI's fetcher disables TLS verification process-wide — a defect that
project tracks itself, and the exact thing a shared, reviewed fetcher prevents
from being reinvented badly.

### Do not merge the repositories

| | Item | Goal | Effort | Human? |
|---|---|---|---|---|
| **P1** | **Decide, and record the reason.** The recommendation is: **share the spine, keep the repos.** Three reasons. (1) The primitives genuinely differ — WSM's own STATUS records that neither sibling's record shape transferred, because it models `country ↔ country` and both siblings model `country → value`. (2) The "verify must not import the package" rule is per-package and gets muddier in a monorepo. (3) The atlas's zero-line-diff guarantee is per-repo; in a monorepo, "did my change touch the other project's committed data" becomes a live question on every commit. Revisit only if you find yourself editing two repos in one change more than occasionally. | — | S | ✓ |
| **P2** | **Extract `athena-core`** — a small Python package: the fetcher, `SourceRef`/`Provenance`, change-detection hashing, the `verify/` harness and its AST independence test, and the venv-bootstrapping entry point. Consumed as a **pinned git dependency** (`pip install git+…@v0.1.0` in each `requirements.txt`), not a submodule and not a monorepo — pinning is already this family's house style and submodules add friction on one machine. What must **not** go in: the record shapes. | G4 | L | |
| P3 | **Geometry and palette stay a contract, not a package.** `world.json` is byte-identical across two repos today because both run the same pinned mapshaper command — that contract works and needs no npm packaging. Move `palette.yaml` and its validator into `athena-core` only when a second project actually consumes it. | G4 | S | |
| **P4** | **`athena.toml` in each repo root.** Name, kind, one-line description, entry command, port, health path, docs path, and where its data vintage can be read. Small and declarative — the manifest is the whole interface between a project and the launcher, and keeping it dumb is what stops the launcher needing to know anything about any project. | G4 | S | |
| **P5** | **The launcher.** Scans a projects root for `athena.toml`; lists every project with its git branch, dirty state, last run and data vintage; starts, stops and restarts each on its declared port; streams logs; shows which are up and links to them. **Python + FastAPI on a fixed port** — Python is the one common denominator across all three, subprocess supervision is the whole job, and it keeps the launcher out of the frontend build systems it is supervising. | G4 | L | |
| P6 | **A static hub page first.** Before P5 is worth building, one page on `oscarsb2004.github.io` linking whichever projects are deployed, with a line on what each is. Nearly free, and it answers "view all of the projects" for the deployed case, leaving the launcher to solve only the local case. | G4 | S | |
| P7 | **WSM ↔ atlas link-through** (their G2t). Generalise `country.json` so any country *may* have a deep-dive bundle and the WSM selection panel links to it when one exists. Canada is the working case; the contract is already in `docs/INTEROP-world-strategic-map.md`. **This is the integration that matters** — it is worth more than the launcher, because it is the one that makes the two projects one argument rather than two tabs. | G4 | M | |
| P8 | **Publish the MapLibre globe findings to WSM** before their C3. `setProjection` inside `style.load`; the `background` layer paints the sphere, not the canvas; never guard a map-init effect on its own ref under StrictMode. All three cost real debugging here and all three are in their critical path. | — | S | |

## Stage M — municipalities, provinces and public finance

The direction: a record for every city with its population and name, room for a
deep dive into each city's budget, and provincial budgets and outlooks read
alongside, with key sectors legible throughout — the first step from a
major-projects atlas toward a wider economic, social and demographic system.
The pushback, limitations and verified sources are in
[`CIVIC-FISCAL.md`](CIVIC-FISCAL.md); read it before starting anything past M4.
Three corrections to the ask shape everything below:

- **The record is a municipality, not a city.** "City" is a provincial legal
  status — Halifax is a Regional municipality, Greenwood BC a City of 702. All
  5,161 census subdivisions are records; the type is a field; "cities" is a
  filter.
- **A census subdivision is not a government.** 992 are Indian reserves, others
  unorganized territory, and two-tier regions put one resident under two
  budgets. Money attaches to a local-government entity mapped onto subdivisions,
  never to the subdivision.
- **Budgets, actuals and outlooks are three different claims,** and functions of
  government are not NAICS sectors. No figure is summed across either line.

Identity before money. M1–M4 are cheap and mechanical and unlock everything
else. M5 onward needs decisions only you can make, and should not start before
E0 — fiscal data is exactly the "second dataset not shaped like the first" that
E0 prepares `verify/` for.

| | Item | Goal | Effort | Human? |
|---|---|---|---|---|
| M0 | ~~**`Municipality` records.** Every census subdivision from 98-10-0002 in both languages, None kept apart from zero, StatCan's symbols kept per value, gated on count, presence, province codes and exact provincial sums. `pipeline/05_municipalities.py`.~~ | G4 | M | |
| **M1** | **One parser per table.** `build_geo.mjs` still reads 98-10-0002 itself to rank place labels. Make it read `data/geography/municipalities.json`, so one definition of a subdivision's population exists. | G1 | S | |
| M2 | **Province and census-division records** from the totals and bilingual names already in the payload; the province panel reads them rather than carrying its own. | G2 G4 | S | |
| **M2a** | **Each province's largest sectors, as Statistics Canada publishes them.** Reproduce **36-10-0400**, *Gross domestic product (GDP) at basic prices, by industry, provinces and territories, percentage share*: StatCan's own current-price share of each industry in each provincial and territorial economy, 1997–2025, all 13 (the table has no Canada row). **Nothing is computed by this project** — the percentages are StatCan's, and the panel lists them largest first with the year, which is a sort of published figures, not a ranking of ours. It replaces a planned ranking this project would have calculated itself, removed 2026-09-11 (CLAUDE.md §11). Two things the panel must say: real estate (53) includes owner-occupied dwellings, which this table does not publish as a separate share, and the shares are rounded (Ontario's twenty sectors sum to 99.98 in 2025). | G2 G3 | S | |
| **M3** | **Places and projects → subdivision by geometry.** Point-in-polygon against the 2021 census subdivision boundary file, never name matching — Greater Sudbury, Saguenay, Chatham-Kent and Clarington already defeat names. Marked `DERIVED`. | G2 | M | |
| **M4** | **2016 ↔ 2021 correspondence.** StatCan's individual-municipality finance tables use 2016 codes. Load the published correspondence file; never infer the join from names. **Prerequisite for M6.** | G4 | S | |
| **M5** | **`LocalGovernment` with tiers.** Upper tier (regional municipality, county, BC regional district, MRC, agglomeration) and lower tier, many-to-many onto subdivisions, each mapping sourced. No national list exists — decide the scope (the ~110 in StatCan's tables? one province?) before building. | G4 | L | ✓ |
| **M6** | **StatCan individual-municipality finance, 2018–2020.** 10-10-0169-01 (government finance statistics) and 10-10-0170-01 (functions of government), ~110 municipalities, released 2025-04-08. Design `FiscalRecord` only after reading both cubes, with a required `basis` (`actual` / `budget` / `outlook` / `estimate`). | G3 | M | |
| M7 | **Provincial and aggregate local finance.** 10-10-0017-01 (provinces and territories, annual 2007–2024) and 10-10-0020-01 (local government in aggregate). Read the full dimension lists first — 0017's metadata call has not yet completed. Consolidated tables only for any cross-level total. | G3 | M | |
| M8 | **Ontario FIR and BC Local Government Statistics.** The two provinces that publish every municipality's return as data. One adapter each; their line items map neither to each other nor to CGFS without a crosswalk. | G3 | L | |
| **M9** | **Budgets and fiscal outlooks as documents.** Reproduce published tables with a page reference and `basis: budget` / `outlook`; narrative claims stay in their sentence (CLAUDE.md §1). Never plot a budget on an actuals axis without saying so on the axis. Choose which governments first. | G1 | L | ✓ |
| M10 | **COFOG ↔ NAICS crosswalk,** hand-curated and `DERIVED`, like `gics_naics.yaml`. Functions of government and industries answer different questions; the UI names which one a chart uses. | G2 | M | ✓ |
| M11 | **Municipal and provincial panels.** Sliced payloads per view, never the whole municipalities file. Per-capita figures name their denominator and its year. | G2 G3 | M | |
| M12 | **Census profile variables** — age, income, labour, housing — on the same identity. The social and demographic half of the system. | G3 | L | |

## Stage Q — the financial sector, evaluated critically

Finance reaches this project three ways: as an **industry** (NAICS 52 in the GDP
charts), as **market data** (the XIC company panel), and as **capital** — who
pays for the major projects, and the public finances of Stage M. Each has a
failure mode that looks correct on screen. Measured on 2026-09-10, before any of
this stage was built:

- **The company panel overstates finance about 4.5×.** Financials are 34.5% of
  XIC index weight (23 of 215 holdings; the big five banks alone 22.4%). Finance
  and insurance is about 7.7% of GDP (June 2026, chained dollars, so approximate).
  CLAUDE.md §9's caveat is carried in the payload, but a caveat does not survive
  the two numbers sitting side by side.
- **The crosswalk maps every Financials holding wholly to NAICS 52.** Brookfield
  Corporation (2.29%) earns much of its income from infrastructure, power and
  property — precisely the assets the MPO portfolio is about.
- **Real estate is the largest GDP sector and nearly absent from the market
  panel.** NAICS 53 is 312,736 M against 182,759 M for finance, while GICS Real
  Estate is 1.21% of XIC. Much of NAICS 53 is likely the imputed rent of
  owner-occupied housing, which no listed company earns — verify against table
  36-10-0434's own line before the app says so.
- **Bank output is measured indirectly** (much of it through interest margins),
  so finance GDP moves with rates. It grew +3.6% y/y against +2.0% for all
  industries. The only monetary series in the project is the policy rate.
- **Finance is concentrated.** Ontario holds about 55% of national finance GDP
  (2025, summed chained provincial values, so approximate), and finance is
  10.8% of Ontario's economy against 0.9–6.6% everywhere else.
- **Missing entirely:** household credit, mortgages, housing, bank lending, and
  who finances the major projects.

Q1–Q2 need no new data and can start after B1. Q4–Q6 wait on B2. Q7–Q9 wait on
M7 and C2. Nothing in this stage is investment analysis: it evaluates how public
data about finance is represented, and every computed figure is `DERIVED`.

| | Item | Goal | Effort | Human? |
|---|---|---|---|---|
| **Q1** | **Written critique, `docs/FINANCE.md`.** How finance appears in every current view, what each view implies, what misleads, with the measurements above re-run from committed data. No new data, no code. | G1 G3 | S | |
| **Q2** | **Fix the company-panel comparison.** Index weight must never share a scale or a row with GDP share. Choose the form in Q1 — separate panels, or an explicit weight-vs-output contrast that names both measures on the axis. | G1 | S | ✓ |
| Q3 | **Company-level crosswalk overrides for conglomerates** (Brookfield, Power Corporation and similar), `DERIVED`, each split sourced to the company's own segment disclosure. `gics_naics.yaml` is per GICS sector and cannot express this. | G2 | M | ✓ |
| Q4 | **Finance in current dollars.** Nominal share of GDP from 36100710, now pulled (B2) and gated additive to 0.01%; chained shares are approximate by construction. Ends 2022. | G3 | S | |
| Q5 | **Gross output against value added for finance.** Unblocked by B2a: finance (52) output is the sum of `BS52B00` + `BS52E000` + `BS52410`, 1.77× its value added in 2022. Most bank output is measured indirectly, from interest margins, so the ratio describes that measurement convention as much as it describes banks — the view must say so. | G3 | M | |
| Q6 | **Real estate decomposed:** owner-occupied imputed rent against market activity, if 36-10-0434 publishes the split. Verify the member exists before designing the view. | G3 | S | |
| Q7 | **Monetary and credit context:** Bank of Canada series beyond the policy rate, household credit and mortgage aggregates, housing. Source selection is the decision; table IDs are unconfirmed and must be read from each publisher before use. | G3 G5 | L | ✓ |
| **Q8** | **Who finances the major projects.** Canada Infrastructure Bank participation, federal loan guarantees, pension-fund and private partners — per project, only where published, reproduced verbatim. Joins to C2's capital values. The most important finance question this project can answer. | G2 | L | ✓ |
| Q9 | **Provincial public finance beside provincial finance GDP,** from M7. Never mixes a fiscal basis, never sums across levels of government without consolidation. | G2 G3 | M | |

## Stage H — open decisions

| | Item | Effort | Human? |
|---|---|---|---|
| **H1** | **GitHub Pages.** Prepared, CI green, deliberately not enabled — Pages needs a public repo on the Free plan. Three steps in `STATUS.md`. Going public exposes the full history, `STATUS.md`, the ~4.5 MB bundle and all 18 federal renderings; all of it is OGL content with attribution rendered and there are no credentials, but it is a choice, not a formality. | S | ✓ |
| H2 | **Delete `C:/Code/atlas-backup-pre-rewrite.git`** (32 MB) once you are satisfied with the history rewrite. It is the only copy of the pre-rewrite SHAs. | S | ✓ |
| H3 | **`data/raw/` snapshot policy.** Currently the content hash lives in `SourceRef` and the HTML snapshot is not kept. If a federal page is edited or withdrawn, the hash proves *that* it changed and nothing reproduces *what* it said. Decide: keep hashes only, or commit compressed snapshots. | S | ✓ |
| H4 | **The `status` field is dead.** All 18 projects read `Referred to MPO for consideration`. It renders as a tag that never varies. Either it becomes live when the MPO starts publishing transitions, or the tag goes. MPI's `Status 2024`/`Status 2025` pair (C2) is the nearest real lifecycle data. | S | ✓ |

---

## The critical path

**B1 → B2 → B3 → C1 → C4.** That is the shortest route from here to the thing
this project is for: the portfolio and the economy answering one question
together, in either language, against all seven declared tables.

Stage F is what proves the structure was worth building, and it can start any
time after B2 — but it needs you to choose the event, so it is the item most
worth deciding early.

Stage P should not start before C4. The shared spine is easier to extract once
both repos have finished moving; extracting it now would freeze an interface
around the atlas's current shape and force WSM to bend to it.

## The rule that should survive all of it

Every stage after B adds inference where v1 had only reproduction. The
`Provenance` enum already distinguishes `OFFICIAL_DATASET` / `PAGE_VERBATIM` /
`DERIVED` — as this work lands, **`DERIVED` stops being rare and starts being
load-bearing**, and the UI has to keep showing the difference. A crosswalk, a
location quotient and a multiplier estimate are all ours, not the government's,
and the moment they render like a StatCan figure the project has lost the thing
that makes it trustworthy.
