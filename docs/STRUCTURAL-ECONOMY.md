# The structural economy — verification, strategic sectors, and the producers map

_Written 2026-09-08._

Three things: what the sector-size audit actually found, how a "strategic
sectors" view can be built without this project inventing the list, and a design
for the geolocated producers map — the staples of existence rather than the
stock market.

---

## 1. The sector audit: the numbers are right

**Verified, not assumed.** Three independent checks:

| Check | Result |
|---|---|
| Published values vs the raw cube bytes | **Identical** for every sector at 2026-06 |
| The 20 two-digit sectors summed against T001 | **+0.0000%** on the constant basis |
| National monthly (36100434) vs sum of provinces (36100711) — two separately published cubes | **No sector diverges by more than 1.7%** |

The largest divergence between the two cubes is Agriculture at −1.62%, then
Goods-producing at −1.32%; everything else is under 1%. Two StatCan publications
built from different source data agreeing that closely is about as strong as
external validation gets without a third statistical agency.

So the pipeline is faithful. Which leaves the more interesting question: why do
the sector sizes *look* wrong?

### The two things that make a correct number look wrong

**Management of companies and enterprises [55] is $542M — 0.02% of GDP.**
This is real. Both cubes agree ($542M monthly national, $706M summed
provincially). It looks like a parsing failure and is not: NAICS 55 is head
offices, and StatCan's value-added measure for it is genuinely tiny relative to
the employment people associate with it. A bar that renders as nothing beside
Real estate's 13.2% is the source being honest, and **the UI should say so
rather than leaving the reader to conclude the chart is broken.**

**Mining, quarrying and oil and gas [21] is 5.22% — and most published figures
say ~8%.** This is the one worth acting on, and the discrepancy is almost
certainly *real versus nominal*:

- The app shows **chained 2017 dollars** — volume, with 2017 prices held fixed.
- Almost every "share of the economy" figure in circulation is **nominal** —
  current dollars, current prices.

For a sector whose output prices have moved far from their 2017 base, those two
are different numbers about different things, and oil and gas is the extreme
case in the Canadian economy. A reader comparing our 5.2% against a news article's
8% is comparing a volume share to a value share.

> **This is a hypothesis with a stated test, not a finding.** Nominal annual GDP
> is StatCan `36100710` — one of the four declared-but-unpulled tables in
> `BACKLOG.md` B2. Pulling it settles the question in one run: if nominal mining
> lands near 8% while real stays at 5.2%, the explanation holds and the fix is a
> basis toggle plus a label, not a data correction.

### What was added so this stays checked

`registry/checks.yaml` gains a **cross-source agreement** check: national monthly
against the sum of provinces, per sector, per year, failing past a declared
tolerance. It is the check that would have caught a genuine ingestion error, and
it is the one that just proved there isn't one. Declarative like the rest — a
second event with two overlapping sources declares its own pair and threshold.

---

## 2. Strategic sectors — without authoring the list

The instinct is to write down "Carney's priority sectors" and build a tab from
it. That would be this project making the exact kind of claim invariant §1
forbids: a list nobody published, rendered with the authority of one that was.

Three sourced alternatives, in increasing order of what they cost:

### 2a. Revealed preference — free, and already in the data

**The MPO portfolio IS the answer to "what is being pushed".** Eighteen projects
and nine transformative strategies, each carrying the government's own sector
label, each with a date of referral. That is not our opinion about priorities;
it is where the federal government actually pointed its major-projects machinery.

The tab writes itself once `BACKLOG.md` C1 lands: MPO sector → NAICS crosswalk,
then **projects and capital by sector, beside that sector's GDP and its growth**.
The strategic-sectors view is not a new feature — it is the payoff of C1 and C4,
and building it separately would duplicate them.

### 2b. The statutory criteria — verbatim, five of them

The Building Canada Act does not define "national interest" except by listing
what a designated project must do: strengthen Canada's autonomy, resilience and
security; provide economic benefits; have a high likelihood of successful
execution; advance the interests of Indigenous peoples; and contribute to clean
growth and climate objectives.

Five criteria, published, quotable. They belong in the UI as the **frame** for
the portfolio — the government's own statement of what it is selecting for —
scraped verbatim from `canada.ca/en/one-canadian-economy/...` exactly as the
project pages already are. No inference at all.

### 2c. Designated vs referred — a status axis that is currently dead

`BACKLOG.md` H4 notes that all 18 projects read `Referred to MPO for
consideration`, so the status tag never varies and carries no information.

But **designation under the Building Canada Act is a further legal status than
referral**, and a first tranche of five was named in September 2025 — LNG Canada
Phase 2, Darlington, Contrecœur, McIlvenna Bay and Red Chris. Four of those five
are already in our portfolio.

This is where the 404 the section crawl found becomes important:
`advancing-nation-building-projects/projects-designated-under-building-canada-act.html`
is linked from canada.ca and does not resolve. **When that page goes live it is
the designation list**, and the crawl's broken-link report is what will notice.
Until then, designation status can only be sourced from news releases —
`PLAN.md` §3.6 announcement scraping, which is `BACKLOG.md` F3.

### Recommended shape

One tab, three bands, each labelled by provenance:

1. **What the government is selecting for** — the five statutory criteria,
   verbatim. `PAGE_VERBATIM`.
2. **Where it has actually pointed** — portfolio count and capital by NAICS,
   beside sector GDP, growth and (after B2) employment and capex intentions.
   `OFFICIAL_DATASET`, with the crosswalk `DERIVED` and visibly so.
3. **How far along** — referred / designated, once F3 or the designations page
   makes that sourceable. Explicitly `ABSENT` until then, rather than an empty
   column that reads as "none".

---

## 3. The producers map — staples of existence

> *"Rather than looking at all of the stock market capital, this project is
> focusing on the 'real' businesses. Looking at infrastructure, heavy industry."*

This is the strongest idea in the brief and it is a different object from the
MPO portfolio. Major projects are **what is being built**; producers are **what
already exists and would be missed if it stopped**. A map of the second is the
better answer to "what is this economy actually made of", and it is the natural
home for the XIC company panel's caveat — index weight is not output, but a
nuclear station's nameplate capacity is.

### Why this fits the existing architecture almost exactly

It is an **event** in the `events.yaml` sense — a curated collection of records
with geometry, verbatim text and a source — which means it is the second event
that `BACKLOG.md` F2 wants in order to test G4. If a producers layer ships
without touching `web/`, the structure claim is proven; if it can't, the loader
is wrong and the fix belongs there. **This is the best available F1 candidate.**

### Sources that actually exist, ranked by how cheap they are

| Layer | Source | Licence | Notes |
|---|---|---|---|
| **Power stations** | NRCan / CER open data; OpenStreetMap `power=plant` | OGL / ODbL | Best coverage of any layer. Fuel type and capacity are published fields. |
| **Nuclear** | CNSC licensed facilities | OGL | Eight sites. Small, stable, exact. |
| **Mines** | NRCan Principal Mineral Areas — **already a declared source pattern in this repo** | OGL | Producing mines by commodity, with coordinates. |
| **Grid** | OSM `power=line` (transmission) | ODbL | Large; would need aggressive filtering to trunk lines only. |
| **Ports** | Already committed — `registry/corridors.yaml` | DERIVED coords, real places | Extend rather than duplicate. |
| **Grain / food** | Canadian Grain Commission licensed elevators | OGL | Terminal and primary elevators, with locations. |
| **Refineries / upgraders** | CER | OGL | ~15 facilities. Small and high-signal. |

⚠ **OpenStreetMap is ODbL, not OGL.** Share-alike, with attribution
requirements this repo has not had to handle before. That is a licensing
decision, not a technical one — worth taking the NRCan/CER route first and
treating OSM as the fallback where federal coverage is thin.

### The rule this layer needs before it is built

The MPO portfolio is 18 hand-published projects. Producers are thousands.
"Top producing regions" is a ranking, and **a ranking we compute is a claim we
are making.** So:

> Show producers with a **published capacity or production figure** attached, at
> a threshold declared in the registry. Never a top-N this project chose. If
> NRCan publishes a mine's annual production, that number ranks it; if nothing
> publishes a figure, the facility appears unranked or not at all, and the
> registry says which.

That keeps it on the reproduction side of the line the whole repo is built on,
and it also solves the density problem honestly — the map thins out because the
data thins out, not because we picked favourites.

---

## 4. What is out there — and what is worth borrowing

Surveyed rather than assumed. The useful split is between *complexity* work
(what an economy is capable of) and *physical* work (what it is made of).

**Economic complexity — the mature, well-tooled tradition.**
Harvard Growth Lab's [`py-ecomplexity`](https://github.com/cid-harvard/py-ecomplexity)
computes ECI, PCI, density and proximity from a trade matrix; the
[Atlas of Economic Complexity](https://atlas.hks.harvard.edu/) and the
[OEC](https://github.com/alexandersimoes/oec) are the reference visualisations.

- **Worth borrowing:** the *product space* idea — that what a country can make
  next is a function of what it already makes. Applied to Canadian sectors with
  the NAICS data already pulled, "which sectors are adjacent to what we do well"
  is a genuinely new view and uses a published method rather than an invented
  one.
- **Worth refusing:** ECI as a headline number. It is a ranking of countries
  built on a specific trade classification, and rendering it beside StatCan GDP
  would put a modelled index in the same visual grammar as a measured figure —
  the exact failure `ROADMAP.md` §A6 fences against.

**Input-output analysis — the closest fit to this project's actual question.**
StatCan publishes the **36-10-01xx multiplier family**: the government's own
instrument for "what does $1B of construction in this industry do to output,
GDP and jobs". `ROADMAP.md` §A6 already reasoned this through and reached the
right answer — applying a published multiplier is using a government tool, not
inventing economics, provided every output is labelled an estimate, cites the
table and vintage, and never renders like measured GDP.

The recent literature applies I-O jointly with complexity to ask about
*vulnerability* — which industries a country cannot substitute domestically.
That is a structural-forces question this project's data could actually answer,
and it is the most promising direction after C1.

**Industrial ecology — the physical-stock tradition.** The
[IndEcol Dashboard](https://github.com/IndEcol/Dashboard) catalogues open tools
for material and energy flow analysis. This is the tradition the producers map
belongs to: economies as physical stocks and flows rather than as prices.

**The gap worth occupying.** Complexity work is global, trade-based and
country-ranked. I-O work is national and aspatial. Almost nothing puts the
*physical* economy — the specific stations, mines, terminals and elevators —
on a map next to the sector accounts, with provenance on every figure. That
combination is what this repo is already structured to do, and it is a more
defensible niche than competing with the Atlas on complexity metrics.

---

## 5. What this adds to the backlog

Ordered by value per session, and all of it depends on B2 and C1 landing first.

| | Item | Depends on | Effort |
|---|---|---|---|
| **B2a** | Pull nominal `36100710` and add a **real / nominal basis toggle**, with the difference explained where the reader is. Settles the mining question and fixes the single most likely cause of "the sector sizes look wrong". | B2 | S |
| **B8** | Annotate `[55]` and any sector under 0.1% with what the measure is, so a correct near-zero bar stops reading as a broken chart. | — | S |
| **C6** | **Strategic sectors tab** — the three-band design in §2. | C1, C4 | M |
| **C7** | Scrape the Building Canada Act criteria verbatim; watch the 404 designations page via the crawl's broken-link report. | — | S |
| **F1a** | **Producers as the second event.** Power stations first (best coverage, published capacity), then nuclear, mines, refineries, elevators. Proves G4 and builds the physical map. | F2 loader work | L |
| **D6** | **Sector adjacency** from the product-space method, applied to NAICS. `DERIVED`, heavily labelled. | B2, D1–D5 | L |
| **D7** | **I-O multipliers** — only the published-instrument path, only as labelled estimates. | D6 | L |

**Sources:** [PM — strategic industries](https://www.pm.gc.ca/en/news/news-releases/2025/09/05/prime-minister-carney-launches-new-measures-protect-building) · [PM — Defence Industrial Strategy](https://www.pm.gc.ca/en/news/news-releases/2026/02/17/prime-minister-carney-launches-canadas-first-defence-industrial) · [Building Canada Act — projects of national interest](https://www.canada.ca/en/one-canadian-economy/services/building-canada-act-projects-national-interest.html) · [py-ecomplexity](https://github.com/cid-harvard/py-ecomplexity) · [OEC](https://github.com/alexandersimoes/oec) · [IndEcol Dashboard](https://github.com/IndEcol/Dashboard)
