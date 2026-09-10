# Municipalities, provinces and public finance

_Written 2026-09-10, when the `Municipality` record landed. The queue is
[`BACKLOG.md`](BACKLOG.md) Stage M; this file is the reasoning behind it, and
what should stop an item being done the wrong way._

## The ask

A record for every city, carrying its population and name, with room for a later
deep dive into each city's published budget. Provincial budgets and fiscal
outlooks evaluated alongside the cities. Key sectors legible throughout. All of
it groundwork: the project is meant to grow from the Major Projects portfolio
into a wider system for economic, social and demographic analysis, with the
projects becoming one element of it.

The direction is right. Four parts of the ask, taken literally, would build the
wrong thing, so each is pushed back on below before anything is built on it.

## What exists now

`pipeline/05_municipalities.py` writes `data/geography/municipalities.json`:
every one of Canada's **5,161 census subdivisions** from Statistics Canada table
98-10-0002, as `atlas.core.schema.Municipality` records.

| Field group | Contents |
|---|---|
| Identity | `csd_uid` (7 digits: province, division, subdivision), `dguid`, `census_vintage`, `geo_key` = `csd:2021:1001186` |
| Names | `name`, `census_division_name`, both languages, verbatim |
| Legal type | `csd_type_abbr`, `csd_type` — as each language's file publishes it |
| Counts | population, private dwellings and occupied dwellings for 2021 and 2016, with StatCan's percentage changes |
| Area | land area, density, national and provincial rank |
| Quality | `symbols`: StatCan's flag on any measure — `..` not available, `...` not applicable, `r` revised, `E` use with caution |

The payload also carries the published Canada and province totals, and the
bilingual names of all 13 provinces and territories and 293 census divisions.

`verify/` gates the record count, id uniqueness, presence of the names and types,
province codes, and that the 2021 population, private dwellings and occupied
dwellings of each province **sum exactly** to its published total.

Nothing in `web/` reads the file yet. It is the identity spine: the thing a
municipal finance table, a census profile or a project's location joins **to**.

## Pushback

### 1. The record is a municipality, not a city

"City" is a legal status that each province defines for itself. On the 2021
table:

- Only **165** subdivisions are typed *City*, and **229** *Ville*.
- **Halifax** (439,819) is a *Regional municipality*.
- **Oakville** (213,759) and **Richmond Hill** (202,022) are *Towns*.
- **Langley** (132,603) and **Saanich** (117,735) are *District municipalities*.
- **Greenwood, BC** is a *City* of 702 people, and **L'Île-Dorval** a *Ville* of 30.

A `City` class would drop Halifax and keep L'Île-Dorval. So every subdivision is
a record and its legal type is a field. "Cities" is a filter a view applies:
by type, by population, or by membership in a census metropolitan area. Which
filter is right depends on the question.

### 2. A census subdivision is not a government

StatCan draws census subdivisions to count people, not to show who governs:

- **992** are Indian reserves, whose governance and finances are not
  municipal.
- **160** are *Regional district electoral areas* and **138** are
  *Unorganized*. They have no municipal council and no municipal budget.
- **Two tiers.** Much of Ontario has an upper tier (a regional municipality or
  county) over its lower-tier municipalities. BC's regional districts overlay
  their member municipalities. Quebec has regional county municipalities (MRCs)
  and the agglomerations of Montréal and Québec. A resident of Mississauga pays
  for services in both the City of Mississauga's budget and the Region of
  Peel's.

So **budgets never attach to a `Municipality` record**. They attach to a
`LocalGovernment` (BACKLOG M5), which carries a tier and maps onto one or more
subdivisions. Summing municipal spending across a region without knowing the
tiers double-counts. Summing lower tiers alone undercounts.

### 3. Budgets, actuals and outlooks are three different claims

- A **budget** is a plan the council voted for.
- A **financial return** or audited statement is what actually happened.
- A provincial **fiscal outlook** is a projection, revised quarterly.

The three routinely differ by more than the changes an analysis looks for, and
each is published on its own schedule.

The rule, from the first fiscal record onward: every figure carries a required
`basis` of `actual`, `budget`, `outlook` or `estimate`. No view sums, averages
or differences figures across bases without saying so on the axis. This is the
fiscal version of CLAUDE.md §8 (chained dollars are not additive). The failure
is the same: a chart that looks right and compares two different things.

### 4. "Key sectors" means three different things

| Sense | Classification | Where it appears |
|---|---|---|
| **Industry** | NAICS, 20 sectors | The GDP charts. "Manufacturing produced $X of value added." |
| **Function of government** | COFOG / CCOFOG | Municipal and provincial spending. "The city spent $X on public order and safety." |
| **Institutional sector** | System of National Accounts | Government vs corporations vs households. "General government's share of GDP." |

"Transportation" is a NAICS sector (48–49, transportation and warehousing) and
also a spending function (part of *economic affairs*). The two are different
quantities: firms' value added in one case, government outlays in the other.
The UI should always name the classification. A COFOG ↔ NAICS crosswalk (M10)
is possible, but it is `DERIVED` and lossy, like `gics_naics.yaml`.

### 5. Build the identity before the money

The natural order is to start where the ask is most interesting, with budgets.
It is also the order that fails. Every fiscal source keys its rows differently:

- StatCan's municipal tables use **2016** subdivision codes.
- Ontario's Financial Information Return uses its own municipality codes.
- Budget PDFs use names.

Without a gated identity spine and the 2016 ↔ 2021 correspondence, each adapter
would invent its own join, and the joins would disagree without saying so.
Hence M0–M4 before M6.

## Limitations to design around

- **Coverage.** StatCan publishes government finance statistics for *individual*
  municipalities for about 110 of them, not all 5,161. The rest appear only
  inside provincial aggregates. A national per-municipality picture exists only
  for the largest places. For every place, it exists only where a province
  publishes returns (Ontario, BC).
- **Lag.** The individual-municipality tables run 2018–2020 (released
  2025-04-08). The provincial table runs to 2024. Any "latest" municipal figure
  is years older than the provincial one beside it, and the UI has to say so
  (G5).
- **Code drift.** Amalgamations and dissolutions change subdivision codes
  between censuses. Join through StatCan's published correspondence file, never
  by matching names: Greater Sudbury, Saguenay, Chatham-Kent and Clarington
  already defeat name matching in the place labels.
- **Fiscal years don't line up.** Provinces and the federal government run
  April–March. Municipalities run calendar years. Putting "2023" for both on one
  chart compares periods nine months apart.
- **Nominal dollars.** Fiscal data is nominal. Deflating it is a modelling
  choice (which deflator?), so it is `DERIVED`.
- **Per-capita denominators.** The census gives counts for census years only.
  Intercensal population estimates for subdivisions are a separate StatCan
  product. A per-capita figure must name which denominator, from which year.
- **Transfers double-count.** Provincial grants to municipalities are spending
  in the provincial accounts and revenue in the municipal ones. Adding the two
  counts the money twice. Totals across levels of government come from
  StatCan's *consolidated* tables, never from summing the unconsolidated ones.
- **2016 counts are not aggregable.** In 98-10-0002, the 2016 subdivision counts
  do not sum to the published 2016 province totals for NL, QC and ON. 597
  subdivisions' 2016 populations carry the `r` (revised) flag. The schema says
  never to aggregate them upward, and `verify/` gates only the 2021 identities.
- **Budget documents are documents.** Each municipality publishes its own format,
  usually PDF. A table in a budget can be reproduced with its page reference.
  Narrative claims ("a 3.9% increase") stay in their sentence, per CLAUDE.md §1.

## Sources verified

| Table | Title (from the table page) | What is known |
|---|---|---|
| [98-10-0002-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000201) | Population and dwelling counts: Canada, provinces and territories, census divisions and census subdivisions (municipalities) | **In use.** 5,468 geographies; EN comma-delimited, FR semicolon-delimited; values identical across languages |
| [10-10-0169-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1010016901) | Canadian government finance statistics for individual municipalities and other local public administrations, as reported by municipalities | 2018–2020, ~110 municipalities, 2016 geography codes, released 2025-04-08 |
| [10-10-0170-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1010017001) | Canadian classification of functions of government for individual municipalities and other local public administrations, as reported by municipalities | Same universe and years as 0169, spending by function |
| [10-10-0020-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1010002001) | Canadian government finance statistics for municipalities and other local public administrations | Local government in aggregate. Dimension members not yet read |
| [10-10-0017-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1010001701) | Canadian government finance statistics for the provincial and territorial governments | Annual 2007–2024, 3,432 series, released 2025-11-21, geography members on 2016 vintage. Full dimension list not yet read — the metadata call timed out |
| [Ontario FIR](https://data.ontario.ca/dataset/financial-information-return-fir-for-municipalities) | Financial Information Return for municipalities | Every Ontario municipality's standardized return, as data |
| [BC local government statistics](https://www2.gov.bc.ca/gov/content/governments/local-governments/facts-framework/statistics/statistics) | Local government statistics | BC municipalities' and regional districts' financial schedules |

Read each cube's metadata in full before designing its schema (M6, M7). The
municipal table shapes above were read from the cube metadata. The provincial
dimensions were not, and the order of work should reflect that.

## The fiscal record, as intent rather than code

Written down now so M6 starts from the constraints rather than rediscovering
them. **Do not build it before reading the cubes.**

- **Who:** `government_id` → a `LocalGovernment` or a province, never a
  `Municipality`.
- **When:** `fiscal_year` with an explicit start and end date, not a bare
  year.
- **Basis (required):** `actual`, `budget`, `outlook` or `estimate`.
- **Classification:** `CGFS`, `CCOFOG`, `ON-FIR` or `BC-LGS`, plus the
  publisher's own item code and label, verbatim, in both languages where
  published.
- **Value:** the value, unit, scalar and a nominal-dollar flag.
- **Consolidation:** `consolidated`, `unconsolidated` or `n/a`.
- **Source:** a `SourceRef`, with `Provenance.OFFICIAL_DATASET` for tables and
  `PAGE_VERBATIM` for a table reproduced from a document.

Three rules are enforced in `verify/`, not in the UI:

- No aggregate crosses a basis.
- No aggregate crosses a consolidation state.
- No aggregate sums an upper and a lower tier for the same territory.
