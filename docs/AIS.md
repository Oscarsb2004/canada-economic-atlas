# AIS — Canadian-flagged vessels: live on localhost, daily on the site

_Planned 2026-09-11. The register (S1, stage 07), the collector and the layer
(S2, S3) were built 2026-09-12; they wait on an aisstream.io key. The queue is `BACKLOG.md` Stage S; this file carries the
reasoning, the sources as they were read, and the limits that must reach the
screen._

## What was asked

Show where every **Canadian-flagged vessel** is — ideally anywhere in the
world — preferring government sources unless they are less current. When the
atlas runs on localhost, poll live. Keep the published github.io site current
too: daily, and automatically if GitHub can do it (it can — see Architecture).
The register is used alongside the feed only for what it adds. Foreign-flagged
vessels that trade with Canada are the **next** stage, not this one.

_Originally (2026-09-11) this was local-only with no scheduled job; revised
2026-09-12 on request._

## The source problem, stated first

**No Canadian government body publishes live vessel positions as open data.**
The Coast Guard receives AIS for its own traffic services, and the Government
of Canada buys satellite AIS from a commercial supplier (ORBCOMM, via Maerospace)
— neither is published. What `open.canada.ca` carries is historical: vessel
density maps built from past AIS, not positions.

So this stage cannot meet "government data only" for the positions themselves.
It can meet it for **identity** — which vessels are Canadian — and that split is
the design:

| Question | Answered by | Government? |
|---|---|---|
| Which vessels are Canadian? | **Transport Canada, Canadian Register of Large Vessels** (OGL, EN + FR XLSX, JSON/XML API, updated continually) | Yes |
| Where is each one now? | A live AIS feed — see S0 | **No** |
| Which MMSI prefix is Canada's? | ITU Maritime Identification Digits: **316** (confirmed 2026-09-12; the Coast Guard's Radio Aids to Marine Navigation uses 316010115 as its example) | Intergovernmental (UN agency) |

The positions are the atlas's one exception to "government", and are labelled
that way: whose data it is, and what it is not.

### Live feed candidates (S0 — your decision)

| Option | Cost | Coverage | Notes |
|---|---|---|---|
| **aisstream.io** | Free, API key | Terrestrial receivers only — **no mid-ocean positions** | WebSocket push. Server-side only: its documentation says direct browser connections are not permitted. Bounding boxes are required; an MMSI list filter is capped (the documentation read on 2026-09-11 says 200). 3 connections per account, subscription changes at most once a second, no SLA, no replay. **No published terms of use or licence were found** — read and record them before building. |
| AISHub | Free only in exchange for feeding it your own AIS receiver | Terrestrial | Requires hardware. |
| Satellite AIS (Spire, ORBCOMM, …) | Paid contract | Global, including open ocean | The only way to see a Canadian ship mid-Atlantic. |

**Chosen 2026-09-12: aisstream.io**, with the coverage limit said on screen.

## Identity: what "Canadian-flagged" means here

A ship's flag is its **state of registry**, so the authority is the register,
not the radio. Two signals, never merged silently:

1. **Register match (strong).** AIS static messages (type 5) carry an IMO
   number. The Transport Canada register carries `Imo Vessel Number`. A match is
   `flag_basis: register_imo`.
2. **MMSI prefix (weak).** The first three digits of an MMSI are the Maritime
   Identification Digits of the administration that assigned it. 316 is
   `flag_basis: mmsi_mid`. Misconfigured transponders, and vessels that changed
   flag without changing MMSI, make this wrong in both directions.

**What the register does not carry, read from its data dictionary:** no MMSI and
no radio call sign. Its fields are Official Number, Vessel Name, IMO number, Hull
Number, Year of Build and Latest Rebuild, Port of Registry, Registration Date,
Vessel Descriptor, Gross and Net Tonnage, Construction Type and Material, Length,
Breadth, Depth, Engine Type and Number, Propulsion Type, Method and Power, Speed,
Unit/Brake Power. So:

- a vessel with no IMO number (much of the domestic fleet) can only be recognised
  by its MMSI prefix — the weak signal — and is shown as such;
- **never match on name.** Vessel names repeat; the same rule as MPI's join.
- Small commercial vessels are a second Transport Canada register (Small
  Commercial Vessel Registry, OGL, CSV). Whether it carries IMO numbers must be
  read from its dictionary before it is joined.

**Built 2026-09-12 as stage 07 (BACKLOG S1).** Of the register's 26,907
entries, 1,161 carry an IMO number and are committed; one of those fails the
IMO check digit. Two Official Numbers are listed twice, so a vessel here is its
number and its row. STATUS.md has the measurements.

**Flag is not ownership.** A Canadian-owned ship registered abroad is *not*
Canadian-flagged and does not appear. The panel says so, because it is the first
thing a reader who knows Canadian shipping will ask.

## Architecture — built 2026-09-12

```
aisstream.io ──wss──▶ live/collect_ais.py ──▶ snapshot: Canadian vessels, last heard position each
                         (whole world; keeps MMSI 316… ship stations, and IMO numbers in the register)

  on localhost   python run.py --live   → http://127.0.0.1:8765/ships ──(Vite proxy /api/live)──▶ dev app, polled every 15 s
  once a day     GitHub Action, 15 min  → commit positions.json to branch `vessel-positions` ──▶ every build copies it in ──▶ github.io
```

- **The published site updates itself daily.** GitHub Actions can listen to the
  feed on a schedule, so no local run is needed for github.io. The job merges
  what it heard into the previous snapshot — a vessel out of range keeps its
  last position and time — and commits to its own branch. Main never receives a
  live-data commit, so its zero-line re-run rule (CLAUDE.md §6) is untouched.
- **Localhost is live.** `python run.py --live` listens until stopped; the globe
  polls it and the layer row says "live on this computer". It also keeps
  `data/raw/live/positions.json` (gitignored) so the next session starts warm.
- **The key never reaches the browser**, which aisstream.io forbids anyway.
- **Whole world, filtered here.** aisstream.io filters by bounding box or an
  explicit MMSI list, not by prefix. The first run (75 s, 2026-09-12) had the
  world-sized box accepted and measured 168 messages a second, 11,767 vessels
  heard worldwide and 346 Canadian.
- **Scheduled workflows stop after 60 days without repository activity** on a
  public repository (GitHub's rule). The daily commit to `vessel-positions` is a
  push to the repository; if GitHub does not count it, the schedule needs
  re-enabling in the Actions tab.

### Setting it up — only you can do these

1. Create a free account and API key at <https://aisstream.io>.
2. Locally: create `.env` at the repository root containing
   `AISSTREAM_API_KEY=` followed by the key. It is gitignored.
3. For github.io: in the repository's Settings → Secrets and variables →
   Actions, add a secret named `AISSTREAM_API_KEY` with the same key. Until it
   exists the daily job logs a notice and collects nothing.

## Incoming and outgoing — two definitions, both labelled

AIS publishes no "inbound/outbound" field. Two defensible readings, each shown
as what it is:

1. **As reported.** The `Destination` and `ETA` a crew types into the
   transponder, reproduced verbatim. Free text, often stale or blank. Matched to
   Canadian port codes (UN/LOCODE) only where the text *is* a code — never fuzzy.
2. **By geometry — `DERIVED`, formula stated.** Inside or outside Canada's
   maritime zone boundary (a government polygon — source to be confirmed in S4),
   and whether course over ground points toward or away from it, over the
   positions this session has seen. One ping never classifies a vessel.

Where the two disagree, both are shown. Neither is a claim about cargo or trade.

## What must be on screen

- Whose data: the AIS provider named as not-government, the register as
  Transport Canada, OGL.
- Coverage: terrestrial only; a vessel's **last seen** time, and that a gap means
  "out of range of receivers", not "stopped".
- The flag basis per vessel (register match vs MMSI prefix).
- Flag is not ownership.

## The next stage (not planned in detail)

Foreign-flagged vessels calling at Canadian ports: Canadian port areas as
bounding boxes, no flag filter, the same collector. It multiplies volume and adds
a new question — which vessels are trading rather than transiting — that needs
its own sources. Plan it when Stage S has measured what a Canadian-only stream
costs.

## Sources read on 2026-09-11

- aisstream.io documentation — <https://aisstream.io/documentation>
- Transport Canada, Canadian Register of Large Vessels — <https://open.canada.ca/data/en/dataset/bf00b7f4-e370-46b7-94e4-0bdedc98531b> (data dictionary PDF read)
- Transport Canada, Small Commercial Vessel Registry — <https://open.canada.ca/data/en/dataset/5cb32773-e7b1-4681-b82a-43cc39778c1a>
- ITU, Table of Maritime Identification Digits — <https://www.itu.int/en/ITU-R/terrestrial/fmd/pages/mid.aspx>
- Canadian Coast Guard, maritime identification systems — <https://www.ccg-gcc.gc.ca/maritime-security-surete-maritime/systeme-identification-system-eng.html>
- WorkBoat, federal AIS data contract — <https://www.workboat.com/government/canadian-government-signs-option-with-ais-data-provider>
