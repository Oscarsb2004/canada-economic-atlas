# PROGRAM — the long-term plan across the three repos

_Written 2026-09-06. Horizon: from v1 to a running platform._

`docs/BACKLOG.md` is this repo's queue. **This file is the plan across all
three repos and the platform they eventually share** — what happens in what
order, what blocks what, and which decisions are needed when.

Mirror of this file's sync points belongs in
`world-strategic-map/docs/`, the same way the two `INTEROP-*.md` files already
point at each other.

---

## How to read this

**IDs are namespaced**, because two repos now both have a `B1` and a `C1`:

| Prefix | Repo | Queue that owns it |
|---|---|---|
| `CEA-` | `canada-economic-atlas` | `docs/BACKLOG.md` (this repo) |
| `WSM-` | `world-strategic-map` | `world-strategic-map/docs/BACKLOG.md` |
| `ASI-` | `African-Stability-Index` | `methodology/BACKLOG.md` |
| `PLAT-` | the shared spine and launcher | **this file** — nowhere else yet |

`WSM-` items are **referenced, not re-planned**. That queue is owned by work in
that repo; duplicating it here is how the two go out of sync. This file only
records where the two must meet.

**Effort is in sessions**, not hours — one session being a focused sitting that
starts cold and ends with something committed and verified. `S` = part of a
session · `M` = about one · `L` = two or more.

**Detail decays with distance.** M1–M3 are specified to the sub-task, because
they start from what exists today and that is knowable. M4 onward is specified
as outcomes and acceptance tests, because sub-tasks written now for work that
starts after four milestones of change would be confidently wrong. Re-specify
each milestone when the one before it lands.

---

## The horizon at a glance

| | Milestone | Track | Ends when | Effort |
|---|---|---|---|---|
| **M1** | Atlas: reachable | CEA | The app is bilingual and reads all seven declared tables | ~3 |
| **M2** | Atlas: the portfolio has a time axis | CEA | The MPO renders as a process, not a snapshot | ~3 |
| **M3** | Atlas: the two halves join | CEA | Projects and sector GDP answer one question | ~4 |
| **M4** | Atlas: the analyses | CEA | The five `ROADMAP.md` §B2 views ship | ~4 |
| **M5** | Sibling reaches sight | WSM | Their globe renders the corpus | *their queue* |
| **M6** | The link-through | CEA + WSM | WSM's Canada panel opens the atlas | ~2 |
| **M7** | The spine | PLAT | `athena-core` pinned in all three | ~4 |
| **M8** | The launcher | PLAT | One place lists and runs every project | ~4 |
| **M9** | The structure proves itself | CEA | A second event ships with no change in `web/` | ~5 |
| **M10** | Atlas: the Canadian fleet, live | CEA | On localhost, every Canadian-flagged vessel in receiver range is on the globe, its flag basis stated (`BACKLOG.md` Stage S, `AIS.md`) | ~4 |
| **M11** | Atlas: where people are | CEA | Population renders as 3D columns from published census counts (`BACKLOG.md` Stage V) | ~3 |

**Added 2026-09-11.** M10 starts before M3 finishes — its register stage needs no
decision — and M11 follows M3. The ordered sequence is in `BACKLOG.md`, *The
whole roadmap, in order*.

**M5 runs in parallel with M1–M4 throughout.** It is on a different repo and a
different person-shaped bottleneck — their Stage F needs *you* reading articles,
not a session writing code — so it should be started early and fed
continuously rather than scheduled as a block.

---

# M1 · Atlas: reachable

The whole bundle is bilingual and none of the French is reachable; four of seven
declared StatCan tables are unpulled. Nothing here needs a new source, a new
schema, or a decision from you. It is the cheapest milestone in the program and
everything after it is wider for having it.

## CEA-B1 · Language toggle · **M**

`web/src/App.tsx:31` reads `const [lang] = useState<Lang>("en")` — no setter,
no control. Every downstream component already takes `lang` and calls `t()`.

| | Task | Notes |
|---|---|---|
| B1.1 | Add the setter; persist to `localStorage` under `atlas.lang.v1` | Same versioned-key convention as `atlas.pins.v1` |
| B1.2 | The control, in the header beside the KPI row | Also set `document.documentElement.lang` — screen readers switch voice on it, and it is the difference between accessible and merely translated |
| B1.3 | Audit every consumer: `ProjectViewer`, the panels, `FilterRow`, `TabStrip`, chart titles and axis labels | Grep for `t(` and for hardcoded strings; the second set is the work |
| B1.4 | Number and date formatting through `Intl` with the active locale | French uses a comma decimal mark and a space thousands separator. A chart axis reading `1,234.5` in French mode is wrong by a factor of a thousand to a French reader |
| B1.5 | **`ui-strings.ts`** — the headings the components author themselves | "Description", "Quick facts", "Benefits", "Latest updates", "Sites", "Composition", "Ranking"… These are ours, not the government's, and are the one place in this repo where authored text is correct. One file so the set is countable |
| B1.6 | Decide what a pinned tab's label does on switch | A tab stores the *question*, not the answer — so a label captured in English should re-derive, not persist. Renamed labels are the user's words and must survive |
| B1.7 | Gate: every `ui-strings` key exists in both languages | Cheap, and it is what stops the FR side rotting the moment someone adds a view |

**Acceptance:** switch to French, open any project, read every section in French
including the axis numbers; reload and the choice survives.

## CEA-B2 · The four unpulled StatCan tables · **M**

Registry entries, not new code — the loaders, bilingual handling, delimiter
detection and determinism all work. `build_series` now raises naming the column
when a cube's shape moves, so a wrong entry fails loudly.

| | Task | Notes |
|---|---|---|
| B2.1 | `sectors.yaml` entries for `14100201`, `33100225`, `34100035`, `36100710` | ⚠ SEPH `14100201`, **not** LFS `14100355` — the LFS industry aggregation collapses wholesale+retail, finance+real estate and information+recreation and will not join to the 20-sector key |
| B2.2 | Read each cube's member names before writing the filters | Each cube's filter columns differ from the GDP cube's. Do this from the downloaded CSV header, not from the web table view |
| B2.3 | Record that SEPH is establishment-based and **excludes the self-employed** | It travels with the productivity view or that view overstates output per worker in exactly the sectors where self-employment is highest |
| B2.4 | Label capex `34100035`'s current year as **intentions**, not actuals | Different provenance from a measured figure. It is also the closest official thing to a forward pipeline indicator, which is why it is worth the care |
| B2.5 | State nominal `36100710`'s ~3-year lag wherever it is plotted | Never on the same axis as monthly real without it |
| B2.6 | **Decide national-only first.** | Four more tables at provincial granularity could double a 1.4 MB bundle. National first, provincial only where a view needs it |
| B2.7 | Gates: join-key coverage against the 20-sector key; additivity where the measure permits it | The partition check already exists; extend rather than duplicate |

**Acceptance:** `run.py` pulls seven tables, `verify` passes, re-run is a
zero-line diff, and every new series carries its own `release_time`.

## CEA-B5 · Vintage panel · **S**

`meta.json` and every `release_time` are already carried. Surface them where the
reader is. State the ~3-year nominal lag, the ~4-month provincial lag, and that
`retrieved_at` means *last seen to change*, not *last checked* — which is a
better guarantee than most dashboards offer and currently invisible.

---

# M2 · Atlas: the portfolio has a time axis

The MPO is a process — projects get referred, assessed, listed — and the app
shows a snapshot. Everything needed is captured and committed already.

## CEA-B3 · Portfolio timeline · **M**

86 dated updates across 18 projects, each with `date_verbatim` and a verbatim
body. Filterable by project and by sector. Pure reproduction, no new claims.

Sub-tasks worth naming: `date_verbatim` is the government's string and `date` is
our parse of it — the timeline sorts on the second and **displays the first**;
projects with no updates must appear as "no updates published" rather than
vanishing from a view that claims to be the portfolio; and the existing filter
row scopes it like every other view rather than growing its own controls.

## CEA-B4 · "What changed" view · **M**

Off `data/history/`, which is append-only and only grows when content actually
moves. Federal pages are edited in place — Crawford gained a March 2026 update
long after its November 2025 referral — so *when the government changed what it
said* is a fact only this repo holds.

One caution that is now written into `STATUS.md` and belongs in the UI's own
copy: a history entry means the page's text changed, **not** that the project
changed. If a future entry is ever produced by a parser change rather than an
edit, this view is where it will look like news.

## CEA-B6 · Policy annotations on the sector charts · **S**

`events.yaml` already carries `kind: policy_with_projects` and a date precisely
so a policy can be a rule on a GDP chart. Nothing renders it.

---

# M3 · Atlas: the two halves join

This is the goal the layout has implied since v1. **Read `ROADMAP.md` §A2 and
§A3 before starting** — both items have limits that must reach the screen, and
this is the milestone where `DERIVED` stops being rare.

- **CEA-C1** · ~~MPO → NAICS crosswalk~~ **Done 2026-09-12**, option B + C: each
  project in the industry its finished asset operates in, quoting the page and
  Statistics Canada, and also in construction while NRCan's inventory says so.
  Stage 06, `registry/mpo_naics.yaml`. · **M**
- **CEA-C2** · Capital from NRCan's Major Projects Inventory through the join C1
  built — 10 of 18 projects by declared ID, confirmed 2026-09-12, never by name. · **S**
- **CEA-C3** · The ceiling on screen: 10 of 18 projects are in the inventory,
  and none of the Transport or Industrial ones. Show "not published" and
  **never total across the partial set** — a portfolio headline from nine of
  eighteen is wrong by construction, and this item is what stops C2 becoming
  that. · **S**
- **CEA-C4** · Pin count and capital by NAICS sector, beside that sector's GDP.
  **The milestone's actual deliverable.** · **M**
- **CEA-C5** · Point-in-polygon project→province, then capital as a share of
  provincial GDP. Striking for the territories: Yukon's whole 2025 GDP is
  $3,243M and the DGR alone is $26,000M. · **M**

---

# M4 · Atlas: the analyses

Specified as outcomes; sub-tasks when M3 lands. `CEA-D1` through `D5` in
`BACKLOG.md`: contribution to growth properly weighted, productivity, volatility
and cyclicality, provincial location quotients, gross output vs value added.

The one to build first is **D1**. The app currently shows y/y change per sector,
where a small sector at +12% and a huge one at +1% look opposite; the standard
decomposition shows each sector's *share* of total growth, which is the question
people actually mean.

**Acceptance for the milestone:** every one of the five renders with a table
twin, and each is visibly `DERIVED` rather than dressed as a StatCan figure.

---

# M5 · Sibling reaches sight · *parallel, their queue*

Their critical path is **WSM-B1 → B2 → C1 → C3 → D1**: migrate the 49 bloc
memberships into ties, code the casus foederis, bundle, globe, activation trace.
Their Stage F — the present-day corpus — starts the moment B1 lands and is the
stage that decides whether their tool is worth having.

**Start this early and feed it continuously.** It is the only track in the
program whose bottleneck is you reading and judging rather than a session
writing code, and it does not compress. Batching it into a block late is the one
scheduling mistake that would cost real calendar time.

### PLAT-P8 · Hand over the globe findings · **S** · *before WSM-C3*

Three things that cost real debugging in this repo and sit directly on their
critical path:

1. `setProjection` must be called **inside** `style.load` — before the style is
   ready it throws and the map renders blank.
2. The `background` layer paints the **sphere** under globe projection, not the
   canvas. It is the ocean. Binding an "ocean" fill to the world source instead
   paints the country polygons twice and gives a planet with no sea.
3. Never guard a MapLibre init effect on its own ref. `if (map.current) return`
   fights StrictMode's mount→unmount→mount: the second setup bails while the
   first map is torn down, leaving a live canvas whose map object is destroyed.

Worth adding, from today: **Natural Earth 1:110m is a backdrop, not a
coastline.** Anything traced, outlined or measured needs a real boundary file.

---

# M6 · The link-through

**Worth more than the launcher**, and the smallest of the three integration
items. It is what makes the two projects one argument rather than two tabs.

| | Task | Effort |
|---|---|---|
| P7.1 | Generalise `country.json`: any ISO3 *may* declare a deep-dive bundle, with its URL and schema version | S |
| P7.2 | WSM's selection panel renders the link when one exists and nothing when it does not — **absence must not read as an error** | S |
| P7.3 | The atlas accepts a deep link to a country and, later, to a sector | S |
| P7.4 | A schema-major mismatch degrades to no link, never to a broken one | S |

The contract already exists in `docs/INTEROP-world-strategic-map.md`. Canada is
the working case; the generalisation is what makes it a contract rather than a
special case.

---

# M7 · The spine

**Do not start before M3 lands.** Extracting now would freeze an interface
around this repo's current shape and force the sibling to bend to it.

### What is duplicated — measured

| Concern | ASI | CEA | WSM |
|---|---|---|---|
| venv-bootstrapping entry point | `run_asi.py` | copied "almost verbatim" | none |
| polite cached fetcher | ad hoc, **forces `verify=False` process-wide** | `atlas/net.py` | `wsm/net.py` |
| change-detection hashing | — | `atlas/core/jsonio.py` | `comparable_json` |
| `verify/` that must not import the package | yes, AST-tested | yes, AST-tested | wanted (WSM-E1) |
| `SourceRef` / `Provenance` | partial | banner-split portable/project | "portable Athena core" |
| `world.json` | — | canonical (1:10m since 2026-09-12) | not identical as of 2026-09-12: sibling 1:110m, atlas 1:50m then 1:10m — see BACKLOG |

Two facts carry the argument. The hashing implementations solve one problem and
**the sibling's found a bug this repo's shares in principle** — stripping
`accessed_at` from `meta` while every `SourceRef` carries its own copy re-admits
what you excluded. And ASI disables TLS verification process-wide, a defect it
tracks itself, and precisely what a shared reviewed fetcher stops being
reinvented badly.

| | Task | Effort |
|---|---|---|
| P2.1 | New repo `athena-core`. Fetcher, `SourceRef`/`Provenance`, change-detection hashing, the `verify/` harness and its AST independence test, the venv bootstrap | L |
| P2.2 | Consume as a **pinned git dependency** (`pip install git+…@v0.1.0`), not a submodule and not a monorepo — pinning is already this family's house style | S |
| P2.3 | Migrate CEA first (it is the reference implementation), then WSM, then ASI | M |
| P2.4 | ASI's TLS monkey-patch dies in the migration. Fix the underlying cause with `REQUESTS_CA_BUNDLE` if it resurfaces | S |
| P2.5 | Record explicitly what must **never** enter the package: the record shapes | S |

**Repos stay separate.** Three reasons, recorded so the decision does not get
relitigated: the primitives genuinely differ (`country ↔ country` versus
`country → value`, which is why neither sibling's record shape transferred);
verify-independence is a per-package rule that gets muddier in a monorepo; and
this repo's zero-line-diff guarantee is per-repo, so a monorepo makes *"did my
change touch the other project's committed data"* a live question every commit.

Revisit only if you find yourself editing two repos in one change more than
occasionally.

---

# M8 · The launcher

### PLAT-P6 · The static hub first · **S**

One page on `oscarsb2004.github.io` linking whichever projects are deployed,
with a line on what each is. Nearly free, and it answers "view all the projects"
for the deployed case — leaving the launcher to solve only the local one, which
is a much smaller problem than the two together.

### PLAT-P4 · `athena.toml` · **S**

One file per repo root. Name, kind, one-line description, entry command, port,
health path, docs path, and where the data vintage can be read. **Keep it dumb** —
the manifest is the entire interface between a project and the launcher, and its
dumbness is what stops the launcher needing to know anything about any project.

### PLAT-P5 · The launcher · **L**

Python + FastAPI on a fixed port. Python because it is the one common
denominator across all three, subprocess supervision is the whole job, and it
keeps the launcher out of the frontend build systems it supervises.

| | Task |
|---|---|
| P5.1 | Discover: scan a projects root for `athena.toml` |
| P5.2 | Report: per project, git branch, dirty state, last run, data vintage, whether it is up |
| P5.3 | Supervise: start, stop, restart on the declared port; stream logs |
| P5.4 | Port conflicts are reported, never silently reassigned — a project on an unexpected port is worse than a project that did not start |
| P5.5 | Survive a launcher restart without orphaning children, and adopt what is already running |
| P5.6 | One page listing everything, each row linking to its localhost |

---

# M9 · The structure proves itself

**The only test of G4 that means anything.** One event and a generic loader are
indistinguishable until there are two.

- **CEA-F1** · Choose the second event. **Needs you**, and it constrains
  everything below it.
- **CEA-F2** · Ship it: one `events.yaml` entry, one `atlas/sources/` module,
  **nothing in `web/`**. If `web/` has to change, the structure claim is false
  and the fix belongs in the loader, not in the event.
- **CEA-F3** · Announcement scraping — `PLAN.md` §3.6, specified and never
  built. The only way a new project gets noticed automatically.
- **CEA-F4** · A second *country*, if ever. Not before F2: a second country
  whose event structure is still untested is two unproven abstractions at once.

---

## What blocks what

```
CEA-B1 ─┐
CEA-B2 ─┼─► CEA-B3/B4 ─► CEA-C1 ─► CEA-C4 ─► CEA-D1..D5 ─► CEA-F1 ─► CEA-F2
        │              CEA-C2 ─► CEA-C3 ─┘
        └─► CEA-B5

PLAT-P8 ─► WSM-C3 ─► WSM-D1
WSM-C5 ──┬─► PLAT-P7 (M6)
CEA-C4 ──┘

CEA-C4 + WSM-C1 ─► PLAT-P2 (M7) ─► PLAT-P4 ─► PLAT-P5 (M8)
PLAT-P6 — blocked by nothing; do it any time
```

Only three edges are hard: **C1 before C4** (no crosswalk, no joined view),
**B2 before D2/D5** (no tables, no productivity or gross-output views), and
**P8 before WSM-C3** (or they re-debug three problems already solved here).
Everything else is preference.

---

## Decisions you owe, batched by when they are needed

Every one of these is marked `Human?` in a queue. They are gathered here because
batching them is worth more than answering them one at a time.

**Before M1 ends**
- H1 · GitHub Pages: public or stay private? Everything technical is committed
  and CI is green; Pages needs a public repo on the Free plan.
- B2.6 · National-only pulls first, or provincial too?

**Before M3 starts**
- C1 · The MPO→NAICS crosswalk's contested calls, notably whether "Transport"
  means the construction activity or the transport asset.
- C2 · Confirm the six MPI matches by hand before they carry dollar figures.
- H4 · The dead `status` field: wait for the MPO to publish transitions, or drop
  the tag?

**Before M7**
- P1 · Confirm "share the spine, keep the repos" — or overrule it.

**Whenever**
- H2 · Delete `C:/Code/atlas-backup-pre-rewrite.git` (32 MB). It is the only
  copy of the pre-rewrite SHAs.
- H3 · `data/raw/` snapshot policy. Today the hash proves *that* a federal page
  changed; nothing reproduces *what* it said.
- WSM-H1 · SIPRI and GPR — build or fence. Limbo is the one option their
  doctrine forbids.

---

## What would make this plan wrong

Worth writing down, because the sibling repo has already spent three sessions
building the wrong thing and the cure was noticing the premise had moved.

- **If the MPO starts publishing structured data.** M3's whole shape exists
  because capital figures live in prose and the portfolio has no lifecycle
  field. A machine-readable MPO feed makes C2 and H4 obsolete overnight and is
  worth checking for before starting M3.
- **If the second event does not fit** (M9). That is not a failure of the event;
  it is the structure claim being false, and the response is to fix the loader,
  never to special-case the event in `web/`.
- **If the launcher is never used.** P5 is the most speculative item here — it
  is worth building only if P6's static hub proves insufficient in practice.
  Build the hub, live with it, and let the friction argue for the launcher.
- **If `DERIVED` stops being visible.** Everything after M2 adds inference where
  v1 had only reproduction. The moment a crosswalk, a location quotient or a
  multiplier estimate renders like a StatCan figure, the project has lost the
  thing that makes it worth trusting — and no milestone is worth that.
