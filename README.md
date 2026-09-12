# Canada Economic Atlas

**→ <https://oscarsb2004.github.io/canada-economic-atlas/>**

An interactive read of the Canadian economy in two halves: a globe showing
**Canada in the world** with geolocated federal project pins, and an analytical
panel of **sector-level GDP time series**.

The first curated **Event** is the **Major Projects Office** created under the
Building Canada Act. Its project announcements are captured **verbatim** from the
federal source — never paraphrased, never re-worded — with the official rendering
each project was announced with.

Part of the Athena platform family, alongside `African-Stability-Index`.

## Where the data comes from

**This project reproduces other publishers' data. It does not create its own.**

Every figure in the atlas is published by a government source — Statistics
Canada, the Major Projects Office, Transport Canada, Natural Resources Canada, the
Bank of Canada — and travels with the reference to where it was published. The
one exception to *government* is live vessel positions, relayed by aisstream.io
and labelled as a third-party feed. A company panel built on BlackRock's fund
holdings was removed on 2026-09-12: BlackRock's terms do not allow public
republication.

Where the atlas shows a figure of its own, it is the output of a **stated formula
over published inputs** — a sum over a declared crosswalk, a ratio, a published
component subtracted from its aggregate — marked `DERIVED`, with the formula
beside it. Where two classifications meet — Major Projects Office projects and
NAICS — the crosswalk is declared in `registry/` and quotes the project page and
Statistics Canada for every entry.
Nothing is estimated or ranked by this project, and no number is typed in by hand. [`CLAUDE.md` §11](CLAUDE.md) records why that rule exists.

## Status

**v1 is complete and deployed, and the pipeline has grown past it.** Eight pipeline
stages run end to end — `01` projects, `02` sectors, `03` business counts, `04`
trade corridors, `05` municipalities, `06` project industries, `07` vessels, `99`
the bundle — with seven declared Statistics Canada pulls in stage 02. 114 tests
and 160 verification gates pass, and a re-run
against unchanged sources produces a zero-line git diff, which is the acceptance
test for every stage.

Every record is captured in **both official languages**, and the interface
renders either, from an EN / FR toggle in the map's layer panel.

| | |
|---|---|
| What exists, and the findings that cost real work | [STATUS.md](STATUS.md) |
| What to do next, in order | [docs/BACKLOG.md](docs/BACKLOG.md) |
| The long-term plan across all three repos | [docs/PROGRAM.md](docs/PROGRAM.md) |
| What every file does | [docs/CODE-TOUR.md](docs/CODE-TOUR.md) |
| What is analytically defensible, and what is not | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Municipalities, provinces and public finance | [docs/CIVIC-FISCAL.md](docs/CIVIC-FISCAL.md) |
| Rail layer source, coverage, and design decisions | [docs/RAIL.md](docs/RAIL.md) |
| Live Canadian-flagged vessels (planned): sources, limits, local-only design | [docs/AIS.md](docs/AIS.md) |
| How the site is published | [docs/HOSTING.md](docs/HOSTING.md) |
| The full design | [docs/PLAN.md](docs/PLAN.md) |

## Quick start

```bash
python run.py            # the whole pipeline, then verify
```

That is the only command needed. On first use it creates `.venv`, installs
`requirements.txt` into it, and re-executes itself inside — there is nothing to
activate by hand, and it reinstalls only when the pins actually change.

```bash
python run.py --stage 02 # one stage (01 | 02 | 03 | 04 | 05 | 06 | 07 | 99)
python run.py --verify   # independent verification only
python run.py --test     # pytest only
python run.py --refresh  # bypass the HTTP cache and re-fetch StatCan cubes
python run.py --live     # Canadian vessel positions on localhost (needs an aisstream.io key — docs/AIS.md)
cd web && npm run dev    # the app, at http://localhost:5173
```

## Contributing safely

Do not work or push directly on `main`: it is the deployed branch. Create a
feature branch, push that branch, and merge a pull request after its build
passes. The one-time local guard and the exact workflow are in
[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).

## Layout

```
atlas/              importable package — the project's own code
  core/schema.py    canonical objects; "the frontend and the backend are the same object"
  core/registry.py  YAML loaders with validation on load
  net.py            the ONE way this project talks to the internet
  sources/          one module per publisher: mpo, statcan, census, tc_corridors, naics, mpi, vessels, aisstream, business_counts
  industries.py     MPO projects placed in NAICS, checked against their quotes
registry/           configuration as YAML: sources, events, strategies, sectors and their pulls, crosswalks, checks
pipeline/           numbered stages 01–07, and 99 the bundle
data/               pipeline outputs, committed for clone-and-run
web/                React + Vite + MapLibre app
verify/             independent verification; must NOT import atlas/
```

## Principles

1. **Others' data, reproduced.** See *Where the data comes from* above.
2. **Federal text is reproduced, never authored.** Every scraped string travels
   with the `SourceRef` that produced it. Numbers embedded in prose stay in prose.
3. **The frontend and the backend are the same object.** Identity travels with
   the value; the UI never re-derives a label, a total, or a rank.
4. **Configuration is YAML, code is Python.**
5. **Provenance is rendered, not hidden.** Anything this pipeline computes is
   marked `DERIVED`, carries its formula, and is visibly ours.

## Attribution

Major Projects Office of Canada & Natural Resources Canada, and Transport Canada,
under the Open Government Licence – Canada. Statistics Canada data under the
Statistics Canada Open Licence. Bank of Canada data under the Bank of Canada Terms
of Use. See `registry/sources.yaml` for the full list.
