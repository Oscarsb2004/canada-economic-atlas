# ROADMAP — major projects, and statistical analysis

_Written 2026-09-05, after v1. Every number below was checked against the live
sources or the committed data; nothing here is estimated._

v1 delivered the two halves of the brief: the MPO portfolio geolocated with
verbatim text, and sector GDP over time. But it delivered them as **two things
next to each other**, not as one thing. The projects are static dots with no
time dimension and no dollar amounts; the sector charts know nothing about the
projects. This document is about closing that.

Two tracks. Track A is the primary goal and is where the interesting problems
are. Track B is cheaper and partly just unfinished work.

---

## Where v1 actually stands

| Asserted | Reality |
|---|---|
| 18 projects, geolocated, verbatim | ✅ true |
| 86 dated updates captured | ✅ captured, ❌ **never rendered** |
| 18 slugs of change history | ✅ captured, ❌ **never rendered** |
| Project status as a dimension | ❌ all 18 read `Referred to MPO for consideration` — currently a dead field |
| Capital values | ❌ none structured. 9 of 18 have a `$` figure, in prose only |
| Projects ↔ sectors | ❌ unjoined. MPO uses 5 sector values, StatCan uses NAICS |
| News/announcement scraping | ❌ planned in `PLAN.md` §3.6, never built |
| StatCan tables | ⚠️ **3 of 7 declared tables are actually pulled** |

That last row is the cheapest fix in the project and is why Track B starts there.

---

# Track A — major projects: visualisation and modelling

## A1. Give the portfolio a time axis · _high value, low risk_

The single biggest gap. The MPO is a *process* — projects get referred,
assessed, listed under the Building Canada Act — and the app currently shows
only a snapshot.

Everything needed is already captured and sitting unused:

- **86 dated updates** across 18 projects, each with `date_verbatim` and
  verbatim body.
- **`data/history/`**, append-only, one entry per project per content change.

Build:
1. A **portfolio timeline** — every update as a dated event, filterable by
   project and sector. This is the "what has the MPO actually done" view, and it
   is pure reproduction: no new claims.
2. A **"what changed" diff view** off `data/history/`. Federal pages are edited
   in place — Crawford gained a March 2026 update long after its November 2025
   referral — and being able to show *when the government changed what it said*
   is something no other view of this data offers.
3. **Timeline annotations on the sector charts.** `events.yaml` already carries
   `kind: policy_with_projects` and a date precisely so a policy can be a
   vertical rule on a GDP chart. Nothing renders it yet.

## A2. Capital values — what is actually possible · _honest limits_

**The MPO pages do not publish a structured capital figure.** Nine of eighteen
projects mention a dollar amount inside Quick-facts prose, and the pipeline
deliberately refuses to parse those into numbers (see `CLAUDE.md` §1).

The legitimate source is **NRCan's Major Projects Inventory** (OGL, verified
2026-09-05):

```
https://ftp.maps.canada.ca/pub/nrcan_rncan/Natural-resources_Ressources-naturelles/
  major_projects_inventory/MPI_2025_Active_Projects_en.xlsx    →  sheet "MPI 2025 Data"
```

What it actually contains, measured:

- **474 projects, 100% with a cost value.** Total $636,589M; median $320M.
- `Cost 2025 (CAD) {$M}` **and** `Cost 2024` → cost *revisions* over time.
- `Status 2025`, `Status 2024`, `Status change 2024 to 2025` → real lifecycle
  transitions: Announced & Planning (158), Under Construction (142), In Review
  (101), Approved (72).
- Up to six lat/lon pairs per project, P/T, proponent, sector.

**But it only covers 6 of our 18 projects**, and that ceiling is structural, not
a matching problem: MPI's universe is **Energy (318), Mining (132), Forest
(24)** — natural resources only. The MPO portfolio also spans Transport
(Mackenzie Valley Highway, Grays Bay, Roberts Bank, AESC), Electricity
(Darlington, NCTL, Taltson, Nukkiksautiit) and Industrial (Contrecoeur), none of
which MPI tracks.

Verified matches: Crawford $2,835M · Deep Geological Repository $26,000M ·
Ksi Lisims LNG $10,000M · LNG Canada Phase 2 $25,000M · McIlvenna Bay $1,082M ·
Matawinie $481M.

So the rule for this feature is:

> Adopt MPI's cost where a project matches, show **"not published"** where it
> does not, and **never impute, interpolate, or total across a partial set**
> as though it were the portfolio. A "$X billion portfolio" headline computed
> from six of eighteen projects would be wrong by construction.

The join must be a **curated `registry/mpi_join.yaml`** — explicit slug→Project
ID pairs, hand-checked — not fuzzy name matching. Fuzzy matching got 6/18 here
and would silently mismatch as either list grows.

Worth adding alongside: **Alberta's Major Projects inventory** (open.alberta.ca,
$5M+, all sectors, not just resources) is the broadest project-level capital
data in Canada, though single-province.

## A3. Join projects to sectors · _the analytical unlock_

Right now the map and the charts are strangers. The question the whole app is
shaped to answer — *what is being built in this sector, and how big is that
sector?* — cannot currently be asked.

MPO publishes 5 sector values across the 18 projects (Electricity, Energy,
Industrial, Mining, Transport). StatCan uses NAICS. Bridging them needs the same
treatment `gics_naics.yaml` already gets: a **hand-curated, versioned, lossy
crosswalk with its splits documented**, marked `Provenance.DERIVED`.

It is lossy in a specific way worth writing down: MPO "Energy" spans NAICS 21
(extraction) and 22 (utilities) and 486 (pipelines); MPO "Transport" is mostly
NAICS 23 construction *activity* producing a 48-49 transportation *asset*. The
crosswalk should say which it means.

Then: pin count and capital by NAICS sector, sitting beside that sector's GDP.

## A4. Provincial context · _cheap once A2 lands_

Projects carry official coordinates; `provinces.json` carries the boundaries;
provincial GDP is already pulled. Point-in-polygon gives project→province, and
then **project capital as a share of provincial GDP** is a defensible ratio —
and a striking one for the territories, where a single project can rival annual
output (Yukon's entire 2025 GDP is $3,243M; the DGR alone is $26,000M).

## A5. Announcement scraping · _planned, never built_

`PLAN.md` §3.6 specifies it: four hosts (`one-canadian-economy`, `pm.gc.ca`,
`natural-resources-canada`, `intergovernmental-affairs`), seeded from the MPO
news index, change-detected via sitemap `<lastmod>`. This is the raw material
for A1's timeline and the only way new projects get noticed automatically.

## A6. Modelling — what is defensible and what is not

`PLAN.md` §10 fenced out "any forecasting, modelling, or index construction",
and that fence was right for v1. If it is to be crossed, it should be crossed
deliberately and in one specific direction.

**Defensible — descriptive, no new claims:**
- Capital aggregated by sector, province, status (where published — see A2).
- Cost *revisions* (MPI 2024 vs 2025) and status *transitions*. This is genuine
  analysis of published change, not prediction.
- Ratios against published denominators: capital vs provincial GDP, vs sector
  capex (StatCan 34-10-0035, which includes forward *intentions* and is the
  closest official thing to a pipeline indicator).

**Defensible with heavy caveats — using the government's own instrument:**
StatCan publishes **input-output multipliers** (the 36-10-01xx family) — the
official tool for "what does $1B of construction in this industry do to output,
GDP and jobs". Applying a published multiplier is using a government
instrument, not inventing economics. But it is a *static open-model estimate*
that assumes fixed production structure and no capacity constraints, and it
answers a narrower question than readers assume. If built: label every output an
estimate, cite the multiplier table and vintage, show the assumption, and never
put it in the same visual grammar as measured GDP.

**Not defensible — would make this project the source:**
- Our own job-creation or GDP-impact numbers not traceable to a published
  multiplier.
- Completion-probability or schedule-risk scoring.
- Any index that ranks projects by a weighting we invented.

The distinction that matters: **reproducing, applying a published instrument,
and asserting are three different things, and the UI must not render them the
same way.**

---

# Track B — statistical analysis

## B1. Pull the four declared-but-missing tables · _cheapest work in the repo_

`registry/sources.yaml` declares seven StatCan tables. `registry/sectors.yaml`
pulls **three**. The loaders, the bilingual handling, the delimiter detection and
the determinism guarantees all already work — these are registry entries, not
new code:

| Missing | PID | Unlocks |
|---|---|---|
| Employment (SEPH) | `14100201` | GDP per worker; the productivity view |
| Revenue by industry | `33100225` | Gross output vs value added, made visible |
| Capex by industry | `34100035` | Investment context for A2; includes 2026 *intentions* |
| Nominal GDP annual | `36100710` | Current-dollar shares (with its ~3-year lag stated) |

**Corrected 2026-09-10, after the cubes were downloaded and read.** Three of the
four landed (BACKLOG B2), and none of them was only a registry entry:

- `36100710` is current dollars, as assumed — verified by value, since the
  product id says nothing about price basis.
- `34100035` has no column separating actual spending from intentions; one of
  its notes says the latest two years are preliminary actuals and intentions,
  and the payload now labels every period by that note.
- `14100201` is ~1 GB of CSV per language, unadjusted for seasonality, excludes
  agriculture (`[11N]` is forestry alone), and publishes four sectors under
  combined codes such as `[22,221]`.
- `33100225` is **not** revenue by industry. It is quarterly balance sheets and
  income statements for *non-financial* industries, in enterprise groups that
  mostly do not map to two-digit NAICS. Not pulled.
- Gross output came instead from `36100488` (BACKLOG B2a, 2026-09-11). It is
  classified by IOIC rather than NAICS and split by institutional sector, so
  its twenty sectors are a declared, `DERIVED` crosswalk — gated on summing to
  the cube's own total and on never falling below value added.

⚠ Use SEPH `14100201`, **not** LFS `14100355`: the LFS industry aggregation
collapses wholesale+retail, finance+real estate and information+recreation, so
it will not join to the 20-sector GDP key.

## B2. Analyses the current nine chart forms cannot do

- **Contribution to growth**, properly weighted. The app shows y/y change per
  sector; the standard decomposition is each sector's *share* of total growth,
  which answers "what moved the economy" rather than "what grew fastest". A
  small sector growing 12% and a huge one growing 1% look opposite in the
  current view and identical in this one.
- **Productivity proxy** — real GDP per worker by sector, over time (needs B1).
- **Volatility and cyclicality** — rolling standard deviation, and each sector's
  correlation with all-industries. Which sectors *are* the business cycle and
  which ride through it. COVID is already visible in the heatmap; this
  generalises it.
- **Provincial specialisation** — location quotients (a sector's share of a
  province's economy ÷ its share nationally). A standard, defensible measure,
  and the natural bridge to A4.
- **Gross output vs value added by sector** (needs B1 revenue). This makes the
  companies-panel caveat *visible* rather than a footnote: you could show
  directly why summing company revenues overshoots sector GDP.

## B3. Data-quality surfaces the reader should see

The pipeline already knows things the UI hides: nominal GDP is ~3 years stale,
provincial data lags ~4 months, chained dollars are non-additive by +0.311%.
A small "how current is this" panel reading `meta.json` and the `release_time`
stamps would put the vintage where the reader is, rather than in a footer.

---

## Suggested order

1. **B1** — four table pulls. Hours, not days, and everything else leans on it.
2. **A1** — the timeline. Uses data already captured; no new sources.
3. **A2 + the `mpi_join.yaml` registry** — capital values, with the 6-of-18
   ceiling stated in the UI.
4. **A3** — the sector crosswalk. This is where the two halves finally meet.
5. **B2** — the analyses B1 unlocked.
6. **A4, A5** — provincial ratios, announcement scraping.
7. **A6** — only if wanted, only the multiplier path, only heavily labelled.

## The rule that should survive all of it

Every one of these adds inference where v1 had only reproduction. The existing
`Provenance` enum already distinguishes `OFFICIAL_DATASET` / `PAGE_VERBATIM` /
`DERIVED` — as this work lands, **`DERIVED` stops being rare and starts being
load-bearing**, and the UI has to keep showing the difference. A crosswalk, a
location quotient and a multiplier estimate are all ours, not the government's,
and the moment they render like a StatCan figure the project has lost the thing
that makes it trustworthy.
