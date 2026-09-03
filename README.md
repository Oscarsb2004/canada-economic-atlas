# Canada Economic Atlas

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

Early. The Python spine is built and live-verified; the pipeline stages and the
web app are not yet written. **See [STATUS.md](STATUS.md)** for exactly what
exists, what is next, and the parsing findings that should not be rediscovered.

Full design: [docs/PLAN.md](docs/PLAN.md).

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

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
