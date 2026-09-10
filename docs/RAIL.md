# Rail layer — source, decisions, and limits

## What the map shows

The Rail network control renders the **operational Track Segment** feature class
from Natural Resources Canada's (NRCan) **National Railway Network (NRWN)**.
It is an official, nationwide reference network, not an inferred route map,
not a carrier timetable, and not live train positions.

The output is [`web/public/geo/rail.json`](../web/public/geo/rail.json). It is
loaded only when the reader enables Rail network, because the authoritative
linework is much larger than the rest of the entry map. Turning the control off
hides the layer without discarding it from the map instance.

## Why NRWN

NRWN is the correct first rail source for this atlas because it is published by
Natural Resources Canada under the Open Government Licence – Canada and covers
the Canadian network across jurisdictions. Crucially, it supplies both geometry
and the attributes needed to make an honest layer:

- `TRACKCLASS` — Main, Siding, Spur, Yard, Connecting, Crossover, Wye, or Ferry
  Route;
- `STATUS` — used to retain only records the publisher calls `Operational`;
- `OWNERENA` and `OPERATOENA` — retained in the output for later inspection;
- `TRANSPTYPE`, `USETYPE`, `SUBDI1NAME`, and `ADMINAREAC` — retained context.

Those are publisher-defined values. The renderer makes `Main` tracks wider than
the other official classes, but does not use a colour per railway company and
does not throw away sidings, yards, spurs, or ferry routes. A project-made
definition of “important rail” would silently alter the network's meaning.

Source record: [NRCan National Railway Network — GeoBase Series](https://open.canada.ca/data/en/dataset/ac26807e-a1e8-49fa-87bf-451175a859b8).
The record links the exact regional English Shapefile archives used by the
build. Its catalogue metadata says the record was last modified on 2021-05-19
and maintained irregularly; therefore this layer must never be described as
live or current train operations.

## Coverage and deliberate omissions

NRCan delivers one regional archive for AB, BC, MB, NB, NL, NS, NT, ON, QC, SK,
and YT. Its official distribution directory has **no PE or NU archive**. The
build leaves those jurisdictions absent rather than filling the gap from a
provincial, commercial, crowd-sourced, or hand-drawn dataset. That keeps the
map's provenance uniform and makes the coverage limit visible in this record.

Only the Track Segment class is displayed. NRWN also distributes stations,
crossings, marker posts, junctions, and structures; those are intentionally not
rendered in the first rail layer. They would be a second map question with very
different decluttering, interaction, and attribution needs.

The source contains operational *track*, not evidence of service frequency,
capacity, passenger availability, ownership today, train location, freight
movement, or trade volume. None of those claims should be inferred from a line
on this map.

## Rebuilding

Run just the rail geometry during rail work:

```powershell
node scripts/build_geo.mjs --rail-only
```

The command downloads (or reuses) the eleven official archives in
`data/raw/geo/`, extracts only their `TRACK` Shapefile parts to
`data/raw/geo/nrwn-track/`, and uses the pinned local `mapshaper` dependency.
It merges fragments only when every retained official display attribute matches;
no geometric simplification is applied. Output coordinates are written to
roughly 11-metre precision, which preserves every merged operational feature in
the current source package.

For a full reproducible geometry rebuild use:

```powershell
npm run geo
```

`web/public/geo/SOURCES.json` records the source URLs, transform command, and
the PE/NU coverage limit beside the generated data.
