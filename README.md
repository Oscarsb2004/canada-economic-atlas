# Canada Economic Atlas

**→ <https://oscarsb2004.github.io/canada-economic-atlas/>**

An interactive read of the Canadian economy in two halves: a globe showing
**Canada in the world** with geolocated federal project pins, and an analytical
panel of **sector-level GDP time series** and the notable companies within each
sector.

The first curated **Event** is the **Major Projects Office** created under the
Building Canada Act. Its project announcements are captured **verbatim** from the
federal source — never paraphrased, never re-worded — with the official rendering
each project was announced with.

Part of the Athena platform family, alongside `African-Stability-Index`.

## Status

**v1 is complete and deployed.** The four pipeline stages run end to end, 29
tests and 47 verification gates pass, and a re-run against unchanged sources
produces a zero-line git diff — which is the acceptance test for every stage,
not a coincidence.

What is live: 18 Major Projects Office projects geolocated on a globe with their
verbatim text, nine chart forms over 23 national and 299 provincial GDP series,
a provincial choropleth, and pinnable views. Every record is captured in **both
official languages**; the interface currently renders English only, and the
language toggle is the next item in the backlog.

| | |
|---|---|
| What exists, and the findings that cost real work | [STATUS.md](STATUS.md) |
| What to do next, in order | [docs/BACKLOG.md](docs/BACKLOG.md) |
| The long-term plan across all three repos | [docs/PROGRAM.md](docs/PROGRAM.md) |
| What every file does | [docs/CODE-TOUR.md](docs/CODE-TOUR.md) |
| What is analytically defensible, and what is not | [docs/ROADMAP.md](docs/ROADMAP.md) |
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
python run.py --stage 01 # one stage (01 | 02 | 03 | 04)
python run.py --verify   # independent verification only
python run.py --test     # pytest only
python run.py --refresh  # bypass the HTTP cache when pulling
cd web && npm run dev    # the app, at http://localhost:5173
```

## Contributing safely

Do not work or push directly on `main`: it is the deployed branch. Create a
feature branch, push that branch, and merge a pull request after its build
passes. The one-time local guard and the exact workflow are in
[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).

## Layout

```
atlas/            importable package — the project's own code
  core/schema.py  canonical objects; "the frontend and the backend are the same object"
  core/registry.py  YAML loaders with validation on load
  net.py          the ONE way this project talks to the internet
  sources/mpo.py  Major Projects Office: ArcGIS backbone + verbatim page parser
registry/         configuration as YAML: sources, events, strategies
pipeline/         numbered stages (not yet written)
data/             pipeline outputs, committed for clone-and-run
web/              React + Vite + MapLibre (not yet written)
verify/           independent verification; must NOT import atlas/
```

## Principles

1. **Federal text is reproduced, never authored.** Every scraped string travels
   with the `SourceRef` that produced it. Numbers embedded in prose stay in prose.
2. **The frontend and the backend are the same object.** Identity travels with
   the value; the UI never re-derives a label, a total, or a rank.
3. **Configuration is YAML, code is Python.**
4. **Provenance is rendered, not hidden.** Anything this pipeline computes is
   marked `DERIVED` and is visibly ours.

## Attribution

Major Projects Office of Canada & Natural Resources Canada, under the
Open Government Licence – Canada. Statistics Canada data under the Statistics
Canada Open Licence. See `registry/sources.yaml` for the full list.
