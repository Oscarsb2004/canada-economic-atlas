# The test suite, case by case

_67 tests (61 functions, two parametrized), `python run.py --test`. Written
2026-09-10, alongside a logic scan of the suite and of the code it covers._

Every test here exists to stop one specific failure. Most of those failures are
**silent**: the output looks plausible and nothing raises. That is why a test
states its failure in its docstring. A test whose failure cannot be named is
not worth its maintenance.

Each entry below gives three things:

- **Asserts:** what the test checks.
- **Prevents:** the failure it exists for, and why that failure would go
  unnoticed.
- **Construction:** how the input is built so that the test can actually fail.
  This is the part most often got wrong; see the logic scan at the end.

⚑ marks the **12 tests that fail against the previous commit's code**. They
were checked by running the new suite in a worktree at `2c19f8c` with only the
new modules copied in. Each one fails on the defect it names, which shows it
catches a real bug rather than passing whatever the code does.

---

## `tests/test_checks.py` — the verification layer

These import `verify` and never `atlas`. That keeps them honest about the rule
`test_verify_does_not_import_atlas` enforces: the verifier must not share code
with the thing it verifies.

### The path language

**`test_path_fans_out_over_arrays`**
- **Asserts:** `sites[].geometry.n` over two sites returns `[1, 2]`.
- **Prevents:** without `[]` fan-out, `checks.yaml` would need one path per
  site. It would then describe instances, not a shape, and a project gaining a
  site would silently escape every geometry check.
- **Construction:** two sites with different values, so returning only the
  first element would fail.

**`test_path_selects_an_array_element_by_field`**
- **Asserts:** `events[slug=b].expected.n` returns the value from the element
  whose slug is `b`.
- **Prevents:** `expect_from` references like
  `events.yaml:events[slug=major-projects-office].expected.projects` would break,
  or worse point at the wrong event, whenever someone reordered `events.yaml`.
- **Construction:** the wanted element is second, so an index-0 bug fails.

**`test_unresolvable_path_returns_empty_rather_than_raising`**
- **Asserts:** a missing path, an empty path and `resolve_one` on a miss return
  `[]`, `[]` and `None`.
- **Prevents:** datasets that genuinely lack a shape could not be declared. The
  strategies have no geometry; if an absent path raised, every geometry check
  would need a guard at its call site.
- **Pairs with:** `test_a_renamed_records_key_fails…` below. Tolerance belongs
  *inside* a record. The records array itself must exist.

**`test_path_does_not_fan_out_over_a_missing_array`**
- **Asserts:** `[]` on a key holding a dict yields nothing and does not crash.

### Geometry

**`test_point_in_polygon_respects_holes`**
- **Asserts:** inside the ring → in; inside the hole → out; far away → out.
- **Prevents:** a coordinate in a large lake reading as on land. That is exactly
  the kind of bad coordinate the containment gate exists to surface.

**`test_distance_is_zero_inside_and_positive_outside`**
- **Asserts:** distance is 0 inside, and `0 < near < far` outside.
- **Prevents:** a 30 km tolerance means nothing if distance is not monotone.

**`test_longitude_is_scaled_by_latitude`**
- **Asserts:** the same one-degree east-west gap is under 0.6× as long at 60°N as
  at the equator.
- **Prevents:** most of Canada lies north of 55°. Unscaled degrees roughly
  double every east-west distance, so "30 km" would really mean about 15.

**`test_a_point_inside_a_hole_measures_to_the_hole_edge`** — *rewritten*
- **Asserts:** from (5, 5) inside a 4–6 hole, the distance is one degree of
  longitude at 5°N (≈110.8 km, within 1%).
- **Prevents:** a point in a lake being measured to the lake's far shore (≈553
  km) instead of its near one.
- **Logic error fixed:** the old version compared against
  `distance((5,5), exterior-only square) + 200`. (5, 5) is inside that square,
  so the distance is 0, and the test was really `d < 200` dressed up as a
  second measurement. It happened to separate 111 from 553, but it read as a
  comparison it wasn't. It now states the expected value.

### Check kinds

**⚑ `test_zero_is_present_and_blank_is_not`**
- **Asserts:** a record with `population: 0`, `flag: False` and a real name
  passes `fields_present`. Records with `None`, a whitespace-only string, or an
  absent key each fail, and each is named.
- **Prevents:** the old check tested truthiness (`not resolve_one(...)`). A
  presence gate on population would have failed all 268 subdivisions with no
  usual residents, each of them correct.
- **Construction:** one record per kind of absence, so a fix that caught `None`
  but still missed blank strings would fail.

**⚑ `test_unique_ids_names_duplicates_and_records_with_no_id`**
- **Asserts:** `[a, a, b, {}, None]` fails, naming `['a']` and "2 records have
  no id". Distinct ids pass.
- **Prevents two defects:**
  - A record with no id is not a duplicate, so it passed.
  - With two missing ids, `sorted({None, "a"})` raised `TypeError`. The runner
    then reported that the check had *crashed*, not which records were wrong.
- **Also fixed, not asserted:** the old `ids.count(i)` loop was quadratic,
  about 27 million comparisons at 5,161 municipalities. It now uses `Counter`.

**⚑ `test_components_sum_to_the_published_totals`**
- **Asserts:** NL (10 + 20 + None) = 30 and PE (0 + 5) = 5 pass. The label
  counts both groups.
- **Prevents:** an unpublished value crashing the sum or failing the check.
- **Construction:** a `None` and a published `0` sit in the same fixture, so
  both paths run.

**⚑ `test_a_misfiled_record_fails_the_sum_though_the_count_is_right`**
- **Asserts:** moving record `b` from NL to PE fails with "NL: components sum
  to 10 against a published 30" and "PE: … 25 against … 5".
- **Prevents:** this is the case the new kind exists for. A subdivision filed
  under the wrong province changes no record count and no field value.
  `record_count` cannot see it; two provincial sums can.

**⚑ `test_a_group_on_one_side_only_fails_the_sum`**
- **Asserts:** records in `XX` with no total, and a total for `NU` with no
  records, are both reported.
- **Prevents:** comparing only the groups both sides share would pass a
  broken join, such as a province code that changed spelling on one side.

### The runner

**⚑ `test_a_renamed_records_key_fails_instead_of_passing_every_check`**
- **Asserts:** a document with `itmes` where the registry says `items` gives
  exactly one gate, a failure. The failure names `'items'`, says "missing",
  and lists the real keys.
- **Prevents:** the most serious defect in the scan. The runner read
  `document.get(records_key, [])`. A renamed array became zero records, and
  every "is anything wrong with these records" check passes on an empty list.
  Verify would report green over a file it had not read.
- **Construction:** a real registry and data file in `tmp_path`, with
  `checks.ROOT` and `checks.REGISTRY` monkeypatched. This tests the runner's
  actual file handling, not a stub. `_Report` records gates and notes the way
  `verify.run.Report` does.

**⚑ `test_an_empty_dataset_fails_unless_declared_legitimate`**
- **Asserts:** `{"items": []}` fails, and passes only with `allow_empty: true`.
- **Prevents:** the same vacuous pass as a missing key. Declaring an empty
  dataset legitimate is now an explicit registry decision.

**⚑ `test_every_declared_check_is_implemented_and_every_reference_resolves`**
- **Asserts:** against the real `registry/checks.yaml`:
  - every `kind` exists in `KINDS`;
  - every `expect_from` resolves to a positive int;
  - every `allowed` entry is a string.
- **Prevents:** three typo classes that otherwise surface only when verify runs
  against real data:
  - a misspelt kind;
  - a dead reference, which makes `record_count` compare against `None`;
  - a bare `ON` in an `allowed` list, which YAML reads as `True`.
- **Why it failed on old code:** the kind `sums_to_published_totals` did not
  exist yet.

---

## `tests/test_pipeline.py` — parsers, schema, registry, structure

### canada.ca markup

**`test_desktop_mobile_twins_are_deduped`**
- **Asserts:** the description sentence appears once, and the proponent is
  "Acme".
- **Prevents:** canada.ca emits feature cards and descriptions twice, in
  `visible-md visible-lg` and `visible-xs visible-sm` wrappers. `get_text()`
  concatenates both and raises nothing.

**`test_quick_facts_are_not_deduped_away`**
- **Asserts:** exactly one quick fact, with its label, and "$5 billion" still
  inside its sentence.
- **Prevents:** the opposite trap. Quick facts are *not* doubled, so
  deduplicating by repeated text would delete real content. The dollar check
  also pins CLAUDE.md §1: numbers in prose stay in prose.

**`test_benefits_are_bullets_not_one_flattened_paragraph`**
- **Asserts:** benefits come back as the two `<li>` strings, with the `<abbr>`
  flattened to "SMR" and no leading "Benefits".
- **Prevents:** `get_text(" ")` ran every bullet into one paragraph with the
  heading glued on. That shows prose the page never published as prose.

**`test_splitting_benefits_did_not_move_the_content_hash`**
- **Asserts:** `benefits_block_text` is still the flattened block, and it sits
  inside `verbatim_blob()`.
- **Prevents:** the history hash decides when `data/history/` appends. Hashing
  the new list shape would have logged a false "content changed" entry for all
  18 projects on a day nothing changed.

**`test_benefits_falls_back_when_the_list_markup_goes_away`**
- **Asserts:** `<ul>` replaced by `<p>` still gives one bullet.
- **Prevents:** an empty benefits list looks the same as a page with none, so a
  parser failure would read as a data problem.

**`test_mismatched_benefit_counts_lose_no_bullet`**
- **Asserts:** with 2 English and 3 French bullets, both lists survive whole,
  and no item claims both languages.
- **Prevents:** Taltson publishes 4 benefits in English and 5 in French.
  Pairing by position presents one sentence as another's translation. Dropping
  French deletes a federal sentence.

### Section crawl

**⚑ `test_crawl_follows_absolute_links_and_stays_inside_the_section`** — *new, replaces two dead-code tests*
- **Asserts:** on a five-page fake site:
  - groups are exactly `{projects: [national], projects/national: [alpha, beta]}`;
  - the broken link is recorded, not raised;
  - 5 pages are crawled, each requested once;
  - no request goes to the header link, the `-archive` sibling section or an
    off-site URL.
- **Prevents two defects in one filter:**
  - `href.startswith(section_path)` never matches an **absolute** link, so
    `beta`, linked as `https://www.canada.ca/…/beta.html?utm_source=x#top`,
    was never crawled or counted.
  - A bare prefix admits a **sibling section** such as
    `…/major-projects-office-archive/old.html`, which would be reported as an
    undeclared group inside the MPO section.
- **Construction:** `_FakeFetch` serves canned pages by URL, raises for
  anything else, and records every request. That makes "never requested"
  assertable. Both an alpha link and a back-link to the section page are
  duplicated, so the seen-set is exercised.
- **Why two tests were deleted:** `index_slugs` had no caller except its own
  tests. The crawl had replaced it. Tests on dead code report coverage the
  pipeline does not have.

**`test_crawl_is_bounded_by_max_pages`**
- **Asserts:** an endless chain of links stops at `max_pages=3`, after exactly
  three requests.
- **Prevents:** a template change that links endlessly walking canada.ca at one
  request a second.

### Registry lookups and geometry

**`test_strategy_french_slug_is_declared_not_assumed`**
- **Asserts:** `critical-minerals` uses `mineraux-critiques`, and every other
  strategy keys on its own slug.
- **Prevents:** a slug-equality join silently dropped that strategy's French
  name from the first run onward.

**`test_every_geometry_with_coordinates_has_an_anchor`**
- **Asserts:** a point anchors at itself, and a corridor has an anchor.
- **Prevents:** CLAUDE.md §2b. Four corridor projects rendered as dashed lines
  with no marker, so nothing could be clicked.

**`test_a_corridor_anchor_is_marked_as_ours`**
- **Asserts:** a corridor anchor is `DERIVED`; a point's is `OFFICIAL_DATASET`.
- **Prevents:** a computed midpoint rendering with a published coordinate's
  authority.

**`test_a_region_has_no_anchor_and_says_so`**
- **Asserts:** a region has no anchor, and its provenance is `ABSENT`.
- **Prevents:** a centroid nobody published standing in for "All of Canada".

**`test_a_placed_point_says_the_placement_is_ours`** — *new*
- **Asserts:** a point with `coordinate_provenance=DERIVED` reports a `DERIVED`
  anchor, and still does after `to_dict` → `from_dict`.
- **Prevents:** Transport Canada names ports and publishes no coordinates, so
  stage 04 places them itself. Without the override, those placements infer
  `OFFICIAL_DATASET`. The round trip matters because the app reads the dict.

**`test_corridor_anchor_walks_the_route_rather_than_averaging_ends`** — *rewritten*
- **Asserts:** on the route (0,0) → (0,1) → (10,1), the anchor is (4.5, 1.0)
  ± 0.05.
- **Logic error fixed:** the old route (0,0) → (0,10) → (10,10) has two equal
  legs, so halfway along it *is* the middle vertex. An implementation that
  just picked the middle coordinate passed. The lopsided route puts each
  shortcut somewhere different:
  - endpoint average: (5.0, 0.5)
  - bounding-box centre: (5.0, 0.5)
  - middle vertex: (0.0, 1.0)
  - walking the route: (4.5, 1.0)
- It passes on old code because the implementation was already right. Only the
  test was weak.

**`test_hero_image_is_read_from_data_bgimg_not_constructed`**
- **Asserts:** the hero path comes from `data-bgimg` (`/nouveau/…`), not from
  the page slug.
- **Prevents:** three project folders don't match their slugs, so a constructed
  path 404s.

### French

**`test_french_headings_are_present_and_not_guessed`**
- **Asserts:** "Faits saillants" and "Dernière mise à jour", with the same key
  set in both languages.
- **Prevents:** a guessed heading yields zero facts while every other field
  looks right.

**`test_normalise_respects_french_typography`** ×5
- **Asserts:** the extraction artefacts `2025 ,` and `( inner )` are repaired,
  while `90 %`, `Longévité :` and `? Oui !` are left alone.
- **Prevents:** French *requires* a space before `% : ? !`. A generic
  "no space before punctuation" rule would rewrite correct French and call it
  verbatim.

**`test_french_arcgis_uses_french_field_names`**
- **Asserts:** `Nom`/`Lien` and `Name`/`Link` resolve through `attr()`, and both
  links reduce to the same slug.
- **Prevents:** reading the French service with English field names returns
  empty values without an error.

### Schema

**`test_corridor_and_point_round_trip`** — two endpoints stay a route through
`to_dict` → `from_dict`, and a point stays a point.

**`test_series_rejects_ragged_periods`** — a series with 2 periods and 1 value
raises at construction rather than misaligning silently.

**`test_sourceref_survives_json`** — the provenance serialises as its value,
the `SourceRef` round-trips, and `PAGE_VERBATIM.is_reproduced`.

### StatCan and market data

**`test_industry_code_is_parsed_from_the_label`**
- **Asserts:** "Manufacturing [31-33]" gives code "31-33" and label
  "Manufacturing". No bracket gives "".
- **Prevents:** losing the join key the cube embeds, or treating an
  uncoded provincial member as a NAICS sector.

**`test_number_parsing_handles_thousands_separators`**
- **Asserts:** "3,047.11" gives 3047.11, and "-" and "" give `None`.
- **Prevents:** a bare `float()` raising on every large holding, which leaves a
  naive reader with only the small constituents.

**`test_holdings_preamble_and_junk_rows`**
- **Asserts:** the preamble date is read, cash and a stale zero-priced equity
  are dropped, and RY is kept as `MARKET_DATA`.

*Removed:* `test_vector_batch_cap_is_the_undocumented_300` asserted
`VECTOR_BATCH_MAX == 300`, the number the constant is defined as. It could only
fail if someone edited the constant, and then it would fail for the wrong
reason. Its docstring and the source comment both claimed "the incremental
refresh still uses it", but nothing in the repo calls that endpoint. The
comment now says so, and the finding is kept for BACKLOG E3.

### Registry integrity

**`test_yaml_does_not_coerce_ontario_to_a_boolean`** — *reduced*
- **Asserts:** `critical-minerals` really contains "ON".
- **Logic error fixed:** it used to loop "every loaded code is a string". That
  loop could never fail: the loader raises on a non-string code before any
  caller sees one.

**`test_an_unquoted_on_in_strategies_yaml_is_refused`** — *new*
- **Asserts:** a strategies document with bare `[ON, QC]` raises
  `RegistryError` mentioning "boolean".
- **Construction:**
  - First asserts the precondition, that PyYAML really does read `ON` as
    `True`. If that ever changes, the test fails loudly instead of passing for
    an unintended reason.
  - Then monkeypatches `R._load` for `strategies.yaml` only, and clears the
    `lru_cache` before and after, so no other test sees the probe.

**`test_sector_partition_actually_partitions`** — the 20 sectors' parents equal
the declared partition, and cross-cuts never overlap it.

**`test_every_source_declares_a_defined_licence`** — no source claims a licence
key that `licences:` doesn't define.

**`test_alto_is_not_drawn_as_a_region`** — a rail line is listed, not painted
across two provinces.

### Trade corridors — *new; these validators had no tests*

**`test_the_corridor_fixture_loads`**
- **Asserts:** the minimal `_corridor_doc()` loads four corridors, Central is
  ("ON", "QC"), and Northern carries its overlap note.
- **Why it exists:** it is the **control**. Without it, a fixture broken for
  some unrelated reason would make every refusal test below "pass" on the
  wrong error.

**`test_corridor_registry_refuses_each_silent_failure`** ×4
- **Asserts:** one knob per case, each raising `RegistryError` with its
  message:
  - unquoted `[ON, QC]` → "boolean"
  - a node id typo → "unknown nodes"
  - `overlaps_provinces` with no note → "unmapped_note"
  - NL in no corridor → "belong to no corridor"
- **Prevents:** each of the four edits would load, draw and be wrong. Ontario
  would leave the Central Corridor; a port would be listed and never placed; a
  latitude-defined corridor would read as exactly three territories; a province
  would vanish from every corridor view.
- **Construction:** `load_corridors` monkeypatches `_load` for
  `corridors.yaml` and clears both `corridor_nodes` and `corridors` caches on
  entry and exit. The document is YAML text rather than a dict, so the boolean
  coercion really happens.

**`test_corridors_are_matched_by_declared_name_not_by_shape`**
- **Asserts:** only "Atlantic Corridor" is returned. Its "Footnote 3" marker is
  removed with the comma re-attached, and Rail and Road keep their own bullets.
- **Prevents:** the real page's "Infrastructure That Supports Trade and Mobility
  Corridors" block has the same infrastructure box as a corridor, so a
  structural rule finds six corridors.
- **Construction:** the fixture includes that lookalike, plus a summary split
  across a line break.

**`test_a_declared_corridor_missing_from_the_page_raises`**
- **Asserts:** declaring Northern, which is absent, raises with its name.
- **Prevents:** five declared and four found, the failure this event was nearly
  built with.

**⚑ `test_unequal_corridor_lists_are_carried_unpaired_in_both_directions`**
- **Asserts:**
  - Rail's 2 English and 3 French bullets are carried whole and unpaired.
  - Road's equal lists still pair.
  - A third mode published only in French survives as a French-only mode.
- **Logic error fixed:** `_modes` walked the English modes only, so an extra
  French mode was dropped with no warning. That is the deletion the unpaired
  bullets exist to prevent, one level up.

### Structure and regressions

**`test_the_bundle_is_the_last_stage`**
- **Asserts:** "99" sorts last, and every stage script exists. Stage 05 is now
  covered.
- **Prevents:** a stage numbered above the bundle ships its output one run late.

**`test_verify_does_not_import_atlas`**
- **Asserts:** an AST scan finds no `atlas` import under `verify/`.
- **Also fixed:** the `verify/run.py` docstring named
  `tests/test_verify_independence.py`, which does not exist. It now names this
  test.

**`test_write_if_changed_ignores_only_volatile_keys`**
- **Asserts:** a first write happens, a timestamp-only change does not rewrite,
  and a real change does.
- **Prevents:** re-runs dirtying git (CLAUDE.md §6).

**`test_cube_filter_mismatch_raises_instead_of_yielding_nothing`**
- **Asserts:** a missing column and an unmatched value each raise with their
  own message.
- **Prevents:** an empty series surfacing three stages later as "the registry
  is missing sectors".

**`test_cache_entries_expire`**
- **Asserts:** a fresh entry is served, and a back-dated one is a miss counted
  in `expired`.
- **Prevents:** a permanent cache freezes content hashes, which silently turns
  off change detection.

### Census subdivisions — *new*

The fixture `_census_zip` builds table 98-10-0002 in miniature, as real zips in
`tmp_path`:
- **Files:** a data CSV and a `_MetaData.csv`. English is comma-separated and
  French semicolon-separated, both with a BOM.
- **Geographies:** Canada, NL, one census division and three subdivisions.
  Each subdivision covers a case the real table has:
  - a town whose 2016 count carries `r`;
  - an unorganized area with population 0 and `...` changes;
  - a reserve with `..` for 2021 and published 2016 and land-area values.
- **Metadata:** member rows, which the reader must skip, and numbered
  attributes.
- **Knobs:** `drop`, `population_of_beach` and `pr_code_of_beach` produce the
  failure cases.

**`test_census_values_keep_not_available_apart_from_zero`**
- **Asserts:**
  - `"0"` gives 0, and `"-28.1"` gives −28.1.
  - A blank with `..` or `...` gives `None`.
  - `"135"` flagged `r` and `"7"` flagged `r,E` stay values.
  - A blank with no symbol, an unknown symbol `Z`, and `"n/a"` each raise with
    their own message.
- **Prevents:** the table writes an unpublished value as a *blank* cell, with
  the reason in the next column. Treating blank as zero invents people.
  Treating any blank as `None` hides the table changing shape.

**`test_census_columns_are_found_by_member_number_not_header_text`**
- **Asserts:**
  - English and French headers map to the same 13 columns.
  - Dropping member 13 raises "members [13]".
  - Removing the Symbols columns raises "no symbol column".
- **Prevents:** English and French headers share only the `[n]` suffix.
  Separately, flags are read positionally from the next column, so that
  pairing has to be checked.

**⚑ `test_census_build_reads_every_subdivision_in_both_languages`**
- **Asserts:** the whole path.
  - Records come back sorted by DGUID.
  - Province and division are read from the identifier.
  - Legal type comes from each language's metadata as published ("Town" /
    "Town"; "Indian reserve" / "Réserve indienne").
  - `None` stays apart from 0, and every flag is kept in `symbols`.
  - `geo_key` is `csd:2021:1001186`.
  - `None` serialises as `null`.
  - Province and division names are bilingual, and Canada's rank is `None`.
- **Why it failed on old code:** `statcan.read_cube` could not read the
  metadata member.

**`test_census_english_and_french_must_describe_the_same_table`**
- **Asserts:** a geography missing from French raises "different geographies",
  and a population differing between the files raises "different values".
- **Prevents:** the French file is the only source of French names and a free
  second read of every value. On the real release, all 5,468 rows agree on
  every value and flag.

**⚑ `test_census_province_is_checked_against_the_metadata`**
- **Asserts:** metadata claiming province 11 for 1001186 raises, naming the
  subdivision.
- **Prevents:** a code and its metadata disagreeing means a join is wrong
  somewhere. Problems are collected, so a bad release names all of them.

---

## The logic scan

| # | Where | Defect | Consequence | Resolution |
|---|---|---|---|---|
| 1 | `verify/checks.py` runner | `document.get(records_key, [])` | A renamed or emptied array passed every check vacuously | Missing key and empty array fail; `allow_empty` opts in. Two tests |
| 2 | `check_fields_present` | Truthiness | 0, 0.0 and False read as missing, so 268 correct municipalities would fail | `_present()` presence semantics. Tested |
| 3 | `check_unique_ids` | Missing ids passed; `None` + `str` sort raised `TypeError`; O(n²) | Unnamed records; a crashed check instead of a finding | `Counter`; missing ids reported. Tested |
| 4 | `verify/run.py` `check_sectors` | One index over three series; eager `f"{drift:+.4f}"` on `None`; divide by a zero total | Misaligned months, `IndexError`, or the verifier crashing on the case the gate exists for | Aligned by period; guarded; detail built conditionally. **No unit test**, see gaps |
| 5 | `mpo.crawl_section` | `href.startswith(section_path)` | Absolute links never crawled; sibling sections crawled | `_section_href`. Tested |
| 6 | `mpo.index_slugs` | Dead code with two tests | Reported coverage of a path the pipeline doesn't take | Removed with its tests |
| 7 | `04_trade._modes` | Walked English modes only | A French-only mode silently dropped | Carried French-only, with a warning. Tested |
| 8 | `statcan.VECTOR_BATCH_MAX` | Tautological test; comment claimed a caller | False confidence; misleading comment | Test removed, comment corrected |
| 9 | Anchor test | Equal legs: halfway = middle vertex | A wrong implementation would pass | Lopsided route |
| 10 | YAML test | A loop that cannot fail | Covered nothing | Direct guard test with an asserted precondition |
| 11 | Hole-distance test | Constant 200 disguised as a measurement | Read as a comparison it wasn't | Expected value stated |
| 12 | `verify/run.py` docstring | Named a nonexistent test file | Misdirection | Corrected |
| 13 | `census.py` (caught before its first commit) | Symbols column ignored; short rows with a DGUID skipped; French type unvalidated | `r`/`E` flags lost; `..`/`...` conflated; a truncated row silently dropping a geography | `symbols` kept; unknown symbols and unexplained blanks raise; short rows raise |
| 14 | Corridor registry and page parser | Validators with no tests | Any of the four refusals could be deleted unnoticed | Control plus four refusals; parser tests |

One more, from this session's own analysis rather than the repo. A throwaway
check comparing the English and French census files filtered rows with
`len(row) > 30`, and every row has exactly 30 cells. It matched nothing and
printed "values identical: True". It was caught only because a zero-row
comparison looked too clean. It is the same class as defect 1, and it is why
the runner now refuses an empty dataset.

## Known gaps

- **`verify/run.py`'s bespoke checks** (sectors, companies, bundle, geometry
  gates) have no unit tests. Defect 4 was fixed by inspection. BACKLOG E0,
  porting them into `checks.yaml` kinds, would make them testable the way the
  declarative kinds are.
- **Stage `main()` functions** are exercised by running them, not by tests.
  Stage 05 was run twice for a zero-byte change (identical SHA-256) and
  verified. That is the project's acceptance test (CLAUDE.md §6), not a unit
  test.
- **No test touches the network,** deliberately. A live-source change is
  caught by stage validation and `verify/`, not by pytest.
- **`web/` is not covered here.** Type-checking and the browser are its tests
  today.
