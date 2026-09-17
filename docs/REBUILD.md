# REBUILD — the same atlas, restructured

_Written 2026-09-17. Status: **plan, for the owner's review.**_

## 1. The goal, in one sentence

**Restructure the code behind the live site into a rigorous, Athena-inspired
layout, while every file the site serves stays byte-for-byte the same.**

- **Nothing visual changes.** `web/src/` is not touched. The site at
  <https://oscarsb2004.github.io/canada-economic-atlas/> must look and behave
  exactly as it does today.
- **Nothing is dropped.** Every dataset, layer, panel and the daily vessel
  snapshot stays.
- **Only the backend's shape changes:** `atlas/`, `pipeline/`, `registry/`,
  `verify/`, `tests/`, `run.py`, and the documents.
- **Athena Data is inspiration, not a dependency.** Pieces are shaped like
  Athena shells and cards so they can be adapted later. That adaptation will
  need its own edits and is out of scope here.

The legacy code is frozen as the tag **`legacy-v1`** (`ecf6ca9`).

---

## 2. Why restructure: the sprawl, measured at `legacy-v1`

| Symptom | Evidence |
| --- | --- |
| **Stages are features, not steps** | 9 stages (`01_projects` … `08_provinces`, `99_bundle`). Each fetches, parses, checks, shapes and writes. `08_provinces` reads four publishers. |
| **Hidden dependencies** | `06_industries` reads `01`'s `projects.json`; `99_bundle` reads everything. Order is kept only by file numbering. |
| **The same job, several times** | Stages 02, 03 and 08 each download Statistics Canada tables themselves. |
| **Half-validated configuration** | 10 files in `registry/`; `registry.py` loads five. The rest are read directly by whichever script uses them. |
| **Mixed responsibilities** | `atlas/sources/` holds connectors (`statcan`), page parsers (`mpo`), text checks (`budget_text.check`) and classification rules (`naics`). `industries.py` and `media.py` sit at the package root. |
| **Big, bespoke files** | `schema.py` has 22 record classes; `verify/run.py` is 1,152 lines; the tests for the whole pipeline share one file. |
| **Planning outweighs checking** | 5,275 lines of documents against 10,783 lines of backend Python; five documents each answer "what next?". |

---

## 3. How "the same" is proven: a golden master

"Nothing changed" is a claim, so it gets a program.

1. **Freeze the inputs.** `legacy-v1`'s pipeline is run once through a
   *recording* fetcher. Every HTTP response and every raw file it reads is stored,
   content-addressed, under `data/raw/frozen/<run-id>/`. The frozen files are not
   committed; a manifest with their hashes is.
2. **Freeze the clock.** Timestamps the pipeline writes come from one declared
   instant, so two runs can be compared byte for byte.
3. **Record the golden master.** The outputs of that legacy run are the answer
   key: every file under `data/`, `web/public/data/`, `web/public/media/` and
   `web/public/geo/`.
4. **Every restructuring step replays the same inputs** through a *replaying*
   fetcher. The fetcher refuses anything the legacy run did not fetch, so new
   code cannot quietly read something different. Its outputs must be
   **byte-identical** to the golden master. One differing byte fails the step.
5. **The site build is compared too.** `npm run build` on the restructured code
   must produce the same `web/dist/` as on `legacy-v1`, which proves nothing on
   screen can differ.

**The compare tool has a negative control:** a deliberately changed value in a
scratch copy must be reported as a difference.

**Publishers may have released new data since 2026-09-13**, so the recorded
legacy run may differ from what is committed today. That difference is written
down as a finding and **not** committed during the restructure: the site keeps
serving what it serves now. Refreshing the data is a separate decision afterwards.

---

## 4. The target structure

The Athena ideas, applied inside this repository:

| Athena idea | Here |
| --- | --- |
| **Source cards** (access, terms read and dated, gotchas) | `registry/sources/<source>.yaml`, one per publisher, replacing the single `sources.yaml` |
| **Dataset cards** (source, chain of steps, release rule, profile, consumer) | `registry/datasets/<dataset>.yaml`, one per output file the site uses |
| **Shells** (one operation, a written card, invariants, a benchmark) | `atlas/shells/`, one module per card in `registry/shells/` |
| **Record types and provenance** | `atlas/core/records.py`: place, observation, asset, event, passage, media |
| **Frames** (body + manifest with column roles) | Each step also writes a frame with its manifest to `build/frames/` (gitignored). The published files keep their current layout, written by `atlas/export/`. |
| **Receipts** | Each run writes the named values it produced to `build/receipts/` |
| **One validator** | `atlas/core/registry.py` loads and validates every registry file and refuses unknown files and fields |

```
registry/
  sources/      one card per publisher (from sources.yaml)
  datasets/     one card per published dataset
  shells/       one card per shell
  crosswalks/   mpo_naics.yaml, the IOIC → NAICS table
  …             events, strategies, provinces, sectors, corridors, budgets, palette, checks (unchanged content)
atlas/
  core/         records, provenance, frame envelope, registry validator, jsonio, clock
  shells/
    acquire/    fetcher (with record and replay), file_download, statcan_table, arcgis_layer,
                html_sections, document_passage, workbook_edition, valet_series, media_capture, ais_stream
    transform/  pair_bilingual, pair_rows, crosswalk, join_by_id, assign_place, anchors, resolve_absent
    check/      additivity, parent_sum, verbatim_at_locator
  project/      atlas-only code: the MPO page parser, the province page assembly, the NAICS evidence reader
  export/       writes each published file in exactly its current layout; meta, country, palette
  run.py        runs a dataset card: acquire → conform → link → check → frame → export, and writes its receipt
run.py          the same commands as today (`--stage`, `--verify`, `--test`, `--live`, `--web`), now dispatching to dataset cards
verify/         unchanged gates, reorganised by dataset, plus the golden-master comparison
tests/          one file per shell and per dataset, each test naming the failure it prevents
live/           the AIS collector, unchanged in behaviour
web/            UNCHANGED
```

### Where each legacy stage goes

| Legacy stage | Dataset cards | Shells |
| --- | --- | --- |
| `01_projects` | MPO projects, MPO strategies | arcgis_layer, project MPO parser, document_passage, media_capture, anchors |
| `02_sectors` | National monthly (both bases), provincial annual, nominal, gross output, capex, employment, policy rate | statcan_table, pair_bilingual, crosswalk (IOIC), additivity, valet_series |
| `03_business_counts` | Business counts | statcan_table, pair_bilingual, resolve_absent |
| `04_trade` | Trade corridors | html_sections (Transport Canada's corridor pages), pair_bilingual, anchors |
| `05_municipalities` | Census subdivisions | statcan_table, pair_bilingual, parent_sum |
| `06_industries` | Industry assignments | file_download (StatCan NAICS classification files), crosswalk, verbatim_at_locator, arcgis_layer (NRCan), join_by_id |
| `07_vessels` | Vessel register | file_download (Transport Canada's register, both languages), pair_rows |
| `08_provinces` | Province profiles | workbook_edition, pair_rows, statcan_table, html_sections (Canadian Heritage), document_passage, media_capture, project province assembly |
| `99_bundle` | — | export |
| `live/collect_ais.py` | Vessel positions (live) | ais_stream |

Datasets that no screen reads (nominal GDP, capex, employment, gross output,
municipalities, the vessel register) are kept, because the goal is the same
project. Their cards say so, with `consumed_by: none` and the reason.

---

## 5. Order of work

Each step is one pull request. **Each must pass the golden master byte for byte**
before the next begins.

| Step | Content |
| --- | --- |
| **S0 Golden master** | The recording and replaying fetcher, the frozen clock, one recorded legacy run, the compare tool with its negative control, and the `web/dist/` comparison. No behaviour changes. |
| **S1 Core** | The one registry validator over every registry file, with a JSON Schema per file and `python run.py --check`; source cards split out of `sources.yaml` into `registry/sources/` and `registry/licences.yaml`; one clock for every stage. *(Records and the frame envelope move to S4, where the first dataset card uses them — nothing is built before its first user.)* |
| **S2 Acquire shells** | Network reading moved into `atlas/shells/acquire/`, each shell with a card in `registry/shells/` that the validator ties to real code: `fetcher` (was `atlas/net.py`), `statcan_table`, `arcgis_layer`, `site_crawl`, `valet_series`, `document_text`, `workbook_edition`, `commons_media`. *Left for later steps: the live AIS stream (S7), and reading downloaded files (census and vessel workbooks, NAICS files), which is extraction and moves with its datasets (S4–S7).* |
| **S3 Transform and check shells** | Transforms `image_derive` (was `atlas/media.py`), `geo_distance`, `absent_cells`, `crosswalk_sum`; checks `join_distance`, `partition_drift`, `verbatim_quotes`, `paired_values`; each with a card and tests that fail under a planted fault. *Not built, because nothing in the pipeline does them: parent sums (only `verify/` checks them, and it must stay independent) and place assignment. Row pairing and label pairing stay inside their readers, whose messages are dataset-specific, and move with them in S4–S7.* |
| **S4 StatCan datasets** | `atlas/core/records.py` (observation, place) and `atlas/core/frames.py` (the envelope and its profiles); 11 dataset cards in `registry/datasets/`; builders in `atlas/datasets/`; `atlas/run.py`, the one writer of outputs, frames (`build/frames/`) and receipts (`build/receipts/`). Stages 02, 03 and 05 are replaced by the runner groups `economy`, `business-counts` and `municipalities`. The validator ties every card to the repository and requires every declared StatCan pull to have a card. |
| **S5 Province profiles** | Stage 08 becomes the `province-profiles` card and the `provinces` group: finances, sector shares, budget passages, mottos and symbols. Brings the passage record and the `passages` frame profile, and `media_outputs` on a card for the images the builder writes itself. |
| **S6 Projects, corridors, industries** | Stages 01, 04 and 06, with the MPO parser moved into `atlas/project/`. |
| **S7 Vessels** | Stage 07 and the live collector's wiring. |
| **S8 Export and clean-up** | The exporters replace `99_bundle`; the old stage scripts and `atlas/sources/` are removed; `verify/` and `tests/` are reorganised; `CLAUDE.md` is updated; the five planning documents become history, with this file as the only queue. |
| **S9 Deploy** | `web/dist/` identical to `legacy-v1`; the workflow re-enabled; the live site checked. |

---

## 6. What does not change

- `web/src/`, `web/public/` contents, the palette, the geometry files, the media.
- The published JSON layouts and `meta.schema_version`.
- The invariants in `CLAUDE.md`: reproduce, never create; verify never imports
  the code it checks; re-runs leave a zero-line diff; terms read before use;
  numbers in prose come from command output.
- `python run.py` and its options still work the same way.

---

## 7. Decisions

All four taken by the owner on 2026-09-17, each as leaned.

| # | Question | Decision |
| --- | --- | --- |
| **Q1** | Must `data/` also be byte-identical, or only what the site serves? | **Both.** `data/` feeds `verify/` and the history, and a stricter test costs nothing. |
| **Q2** | Re-enable the workflow now, so the daily vessel snapshot keeps the site current during the restructure? | **Yes.** Re-enabled 2026-09-17. |
| **Q3** | The frontend (`web/src/`, including the 1,310-line `Globe.tsx`) stays untouched in this rebuild. Restructure it later as a separate step? | **Later**, with the same `web/dist/` identity test. |
| **Q4** | The uncommitted `docs/TESTS.md` notes in the main checkout: keep or drop? | **Dropped** 2026-09-17. |
