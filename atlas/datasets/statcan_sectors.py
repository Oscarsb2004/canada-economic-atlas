"""
atlas.datasets.statcan_sectors — the baseline economy: output, investment and employment by sector.

    python -m atlas.run economy                      every dataset below
    python -m atlas.run --dataset gdp-national-monthly   one of them

(Was pipeline/02_sectors.py until step S4 of docs/REBUILD.md; the code is carried
unchanged. Each output is now its own card in registry/datasets/, and the runner
writes it.)

Every pull is declared in `registry/sectors.yaml` — which cube, which slice, which
output file, and what `verify/` asserts about it. This file turns a declaration
into a payload and knows nothing about any one table.

Outputs (data/sectors/)
    national-monthly.json          real GDP, chained 2017, monthly         36100434
    national-constant.json         real GDP, 2017 constant prices          36100434
    provincial-annual.json         real GDP by province, annual            36100711
    national-annual-current.json   GDP at basic prices, current dollars    36100710
    capex-annual.json              capital expenditures, by province       34100035
    employment-monthly.json        employment (SEPH), unadjusted           14100201
    output-annual.json             gross output, IOIC summed to sectors    36100488
    rates.json                     Bank of Canada policy rate
    _cubes.json                    sha256 of every cube zip

The taxonomy comes from registry/sectors.yaml; the LABELS come from the cube
itself, in both languages, because the industry column embeds its own code
("Manufacturing [31-33]"). Carrying our own labels would let the UI drift from
the source, which the project's governing rule forbids.

WHAT THE NEWER CUBES NEED THAT THE FIRST THREE DID NOT (BACKLOG B2)

The backlog called these "registry entries, not new code". Reading the cubes
before writing the entries showed otherwise:

  SEPH (14100201) is 986 MB of English CSV and 1,075 MB of French — 5.3 million
  rows. Parsed whole, as `read_cube` does, that is several gigabytes to keep one
  row in sixty. It is streamed (`stream: true`), and the French file is read only
  until every wanted label has been seen.

  SEPH publishes three sectors under combined codes — Utilities [22,221] — which
  `code_aliases` maps onto the two-digit key. It does NOT cover agriculture: its
  "Forestry, logging and support [11N]" is forestry alone, and joining it to
  NAICS 11 would divide agriculture-plus-forestry GDP by forestry jobs. So 11 is
  declared absent, with the reason, and `verify/` gates that it stays absent.

  SEPH is unadjusted for seasonality and GDP is seasonally adjusted at annual
  rates. Comparing a month of one with a month of the other measures the season.
  The measure is named `employment_nsa` so nothing can mistake it.

  Capital expenditures (34100035) carry no column saying which years are actual.
  The cube's own note does: the most recent two are preliminary actuals and
  intentions. The payload labels every period (`period_basis`) and cites the
  note; the stage stops if the note stops saying so. An intention on the same
  line as spending is a plan presented as a measurement.

  Suppression and quality codes (x, .., A–F) share the STATUS column. Where a pull
  keeps them, the payload carries them beside the values: a figure graded E is
  published "use with caution", and dropping the grade publishes it without one.

  33100225, declared in the statcan_wds source card as revenue by industry, is NOT pulled: it is
  a balance-sheet table for non-financial corporations whose industry groups do
  not join the 20-sector key. Gross output comes instead from 36100488 (B2a),
  which is not classified by NAICS at all — see `_crosswalk_series`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import yaml

from atlas.core import clock
from atlas.core import frames
from atlas.core import registry as R
from atlas.core.records import observations_from_series
from atlas.core.schema import Provenance, Series, Text, to_jsonable
from atlas.datasets import Built, Context, Skipped
from atlas.shells.acquire import statcan_table, valet_series
from atlas.shells.acquire.fetcher import Fetcher
from atlas.shells.check import partition_drift
from atlas.readers import statcan

log = logging.getLogger(__name__)

#: Province and territory names as the cubes spell them, to our codes.
GEO_CODES = {
    "Newfoundland and Labrador": "NL", "Prince Edward Island": "PE",
    "Nova Scotia": "NS", "New Brunswick": "NB", "Quebec": "QC",
    "Ontario": "ON", "Manitoba": "MB", "Saskatchewan": "SK",
    "Alberta": "AB", "British Columbia": "BC", "Yukon": "YT",
    "Northwest Territories": "NT", "Nunavut": "NU", "Canada": "CA",
}

BOC_VALET = "https://www.bankofcanada.ca/valet/observations"

#: pid -> sha256 of the downloaded cube zip, filled by pull_cube().
#:
#: The hash is of the SOURCE PAYLOAD, not of our derived output. That is what
#: makes it a real change signal: StatCan revises cubes, and a new zip with the
#: same release stamp is a thing that happens. 99_bundle.py reads this so the
#: SourceRef it publishes carries a hash instead of an empty string.
CUBE_HASHES: dict[str, str] = {}


def _load_taxonomy() -> tuple[dict, set[str]]:
    """The sector registry, plus the flat allowlist of codes to keep."""
    with (R.REGISTRY_DIR / "sectors.yaml").open(encoding="utf-8") as fh:
        tax = yaml.safe_load(fh)

    codes = {tax["aggregates"]["total"], *tax["aggregates"]["partition"]}
    codes |= {s["code"] for s in tax["sectors"]}

    # Sanity: the partition must actually partition. 5 goods + 15 services = 20.
    parents = {s["parent"] for s in tax["sectors"]}
    if not parents <= set(tax["aggregates"]["partition"]):
        raise ValueError(f"sectors.yaml: sector parents {parents} are not partition members")
    return tax, codes


def _sha256(path: Path) -> str:
    """Chunked, because the SEPH zips are 129 MB and 141 MB."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class VintageUnknown(RuntimeError):
    """
    A cube whose zips cannot be dated, so they are not parsed and the output is
    left as committed.

    This replaces `_previous_release()`, which answered a failed getCubeMetadata
    by reusing the stamp already in the output file. That stamp describes the run
    that last WROTE the file, not the zip on disk — the same defect as the live
    stamp, pointed the other way. What it protected still holds: an empty fetch
    never blanks a known-good vintage, because now nothing is written at all.
    """


def _previous_hashes(out_dir: Path) -> dict[str, str]:
    """
    The cube hashes already recorded.

    `--pull` runs a subset. Writing only that subset's hashes would erase every
    other cube's change signal from `_cubes.json`, and show up as a diff that has
    nothing to do with what the run touched.
    """
    try:
        doc = json.loads((out_dir / "_cubes.json").read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in doc.get("cubes", {}).items()}
    except (OSError, json.JSONDecodeError):
        return {}


def _crosswalk_series(pull: dict, header_en: list[str], rows_en, header_fr: list[str], rows_fr,
                      release: str, status: dict | None) -> tuple[list[Series], dict]:
    """
    A pull whose cube is not classified by NAICS, summed into the twenty sectors.

    The sector NAMES are StatCan's own NAICS labels in both languages, read from
    the GDP cube's output (`labels_from`), which is why that pull runs first. The
    cube's total keeps its own label, and a one-member bucket with no NAICS name
    — `unallocated` — keeps its member's. The payload lists every member summed
    into every sector, in both languages, so the crosswalk is inspectable where
    the numbers are.
    """
    pid = pull["pid"]
    crosswalk = {str(s): [str(m) for m in ms] for s, ms in pull["crosswalk"].items()}
    total_code = str(pull["total"]["code"])
    wanted = {m for ms in crosswalk.values() for m in ms} | {total_code}
    en = statcan.member_labels(header_en, rows_en, column=pull["industry_column"]["en"],
                               codes=wanted, total_code=total_code)
    fr = statcan.member_labels(header_fr, rows_fr, column=pull["industry_column"]["fr"],
                               codes=wanted, total_code=total_code)

    source = R.DATA_DIR / "sectors" / pull["labels_from"]
    if not source.exists():
        raise SystemExit(f"{pid}: sector labels come from {source.name}; run its pull first")
    named = {s["code"]: Text.from_dict(s["label"])
             for s in json.loads(source.read_text(encoding="utf-8"))["series"]}

    labels = {total_code: Text(en=en.get(total_code, ""), fr=fr.get(total_code, ""))}
    for sector, members in crosswalk.items():
        if sector in named:
            labels[sector] = named[sector]
        elif len(members) == 1:
            labels[sector] = Text(en=en.get(members[0], ""), fr=fr.get(members[0], ""))
        else:
            raise SystemExit(f"{pid}: sector {sector} has no NAICS label and more than one member")

    series = statcan.build_crosswalk_series(
        header_en, rows_en,
        pid=pid,
        measure=pull["measure"],
        frequency=pull["frequency"],
        column=pull["industry_column"]["en"],
        crosswalk=crosswalk,
        total_member=pull["total"]["member"],
        total_code=total_code,
        labels=labels,
        geo_codes=GEO_CODES,
        release=release,
        status_out=status,
    )
    extra = {
        "crosswalk": {
            sector: [{"code": m, "label": {"en": en.get(m, ""), "fr": fr.get(m, "")}} for m in members]
            for sector, members in crosswalk.items()
        },
        "crosswalk_provenance": Provenance.DERIVED.value,
    }
    return series, extra


def pull_cube(fetch: Fetcher, key: str, pull: dict, codes: set[str], raw_dir: Path, *,
              refresh: bool = False) -> tuple[list[Series], dict]:
    """One declared pull, in both languages, as the series and the payload that holds them."""
    pid = pull["pid"]
    aliases = {str(k): str(v) for k, v in (pull.get("code_aliases") or {}).items()}
    keep = codes | {str(c) for c in pull.get("extra_codes", [])}
    log.info("%s: cube %s (%s, %s) → %s", key, pid, pull["frequency"], pull["measure"], pull["output"])

    # The live stamp decides whether the zips are current; the stamp PUBLISHED is
    # the one recorded for the zips actually parsed. Straight after a release the
    # two differ until the zips are replaced, and writing the live one over the
    # old zip's figures is how a file came to claim a vintage it did not contain.
    live = statcan_table.release_time(fetch, pid)
    zip_en, release = statcan_table.download_cube(fetch, pid, "eng", raw_dir, live_release=live, refresh=refresh)
    zip_fr, release_fr = statcan_table.download_cube(fetch, pid, "fra", raw_dir, live_release=live, refresh=refresh)
    if not (release and release_fr):
        raise VintageUnknown(f"{key}: cube {pid} has no recorded release and getCubeMetadata gave none")
    if release != release_fr:
        # Only reachable while the lookup is down — with a live stamp both zips
        # end on it. Figures from one release titled from another is not a mix
        # to publish.
        raise VintageUnknown(f"{key}: cube {pid} English zip is release {release}, French is {release_fr}")
    CUBE_HASHES[pid] = _sha256(zip_en)
    meta_en, meta_fr = statcan.cube_metadata(zip_en, pid), statcan.cube_metadata(zip_fr, pid)

    rows_en: Iterable[list[str]]
    rows_fr: Iterable[list[str]]
    if pull.get("stream"):
        stream_en, stream_fr = statcan.iter_cube(zip_en, pid), statcan.iter_cube(zip_fr, pid)
        header_en, rows_en = next(stream_en), stream_en
        header_fr, rows_fr = next(stream_fr), stream_fr
    else:
        header_en, rows_en = statcan.read_cube(zip_en, pid)
        header_fr, rows_fr = statcan.read_cube(zip_fr, pid)

    status: dict[str, tuple[str, ...]] = {}
    extra: dict = {}
    if pull.get("crosswalk"):
        if pull.get("stream"):
            raise SystemExit(f"{key}: a crosswalk pull reads its rows twice and cannot stream")
        series, extra = _crosswalk_series(pull, header_en, rows_en, header_fr, rows_fr, release,
                                          status if pull.get("keep_status") else None)
    else:
        series = statcan.build_series(
            header_en, rows_en,
            pid=pid,
            measure=pull["measure"],
            frequency=pull["frequency"],
            filters=pull.get("filters", {}),
            keep_codes=keep,
            geo_codes=GEO_CODES,
            release=release,
            code_aliases=aliases,
            status_out=status if pull.get("keep_status") else None,
        )
        # French labels AFTER the English build, so the French file is read only
        # until the codes the build actually kept have all been seen — for SEPH
        # that is a few thousand rows of a five-million-row file.
        labels_fr = statcan.french_labels(header_fr, rows_fr, code_aliases=aliases,
                                          want={s.code for s in series})
        series = [replace(s, label=Text(en=s.label.en, fr=labels_fr.get(s.code, ""))) for s in series]
    unlabelled = sorted({s.code for s in series if not s.label.fr})
    if unlabelled:
        log.warning("%s: no French label for %s", key, unlabelled)

    payload: dict = {
        "generated_at": clock.now_iso(),
        "count": len(series),
        # The cube's own title, reproduced in both languages, so a file names
        # what it is without anyone looking the product id up.
        "title": {"en": meta_en["title"], "fr": meta_fr["title"]},
        "series": to_jsonable(series),
    }
    if pull.get("keep_status"):
        payload["status"] = dict(sorted(status.items()))
    if pull.get("keep_status") or pull.get("period_basis"):
        payload["notes"] = {"en": meta_en["notes"], "fr": meta_fr["notes"]}
    if pull.get("period_basis"):
        spec = pull["period_basis"]
        periods = sorted({p for s in series for p in s.periods})
        basis, note_id = statcan.latest_periods_basis(
            periods, meta_en["notes"], contains=spec["note_contains"], labels=spec["latest"])
        payload["period_basis"] = basis
        payload["period_basis_note_id"] = note_id
        # Which label each period gets is OUR reading of the cube's note.
        payload["period_basis_provenance"] = Provenance.DERIVED.value

    payload.update(extra)
    log.info("  → %d series", len(series))
    return series, payload


def check_partition(series: list[Series], tax: dict) -> None:
    """
    Log T002 + T003 against T001 at the latest period all three publish.

    Aligned BY PERIOD, not by index — the same defect `verify/run.py` had, where
    one series a month longer than the others pairs every comparison with the
    wrong month. `verify/` gates the identity; this is the stage's own early look.
    """
    by_code = {s.code: s for s in series if s.geo == "CA"}
    total, goods, services = (by_code.get(tax["aggregates"]["total"]),
                              *(by_code.get(c) for c in tax["aggregates"]["partition"]))
    if not (total and goods and services):
        log.warning("partition check skipped: missing one of T001/T002/T003")
        return

    found = partition_drift.latest_drift(dict(zip(total.periods, total.values)),
                                         [dict(zip(x.periods, x.values)) for x in (goods, services)])
    if found:
        period, drift = found
        log.info("partition %s: goods+services vs all-industries = %+.4f%%", period, drift)
        if abs(drift) > 1.0:
            log.warning("partition drift exceeds 1%% — check the price basis")


def pull_policy_rate(fetch: Fetcher) -> dict:
    """
    Bank of Canada target for the overnight rate.

    Not a StatCan series and not a sector, so it is stored separately rather
    than forced into the sector schema. It exists here because the KPI row needs
    it and because the sibling repo's country record asks for it by name.

    No open licence: the Bank grants permission requiring attribution and that
    changes be indicated. See registry/licences.yaml.
    """
    src = R.source("boc_valet")
    sid = src["series"]["policy_rate"]
    body = valet_series.latest(fetch, BOC_VALET, sid)
    obs = body.get("observations", [])
    detail = body.get("seriesDetail", {}).get(sid, {})
    if not obs:
        log.warning("Bank of Canada returned no observations for %s", sid)
        return {}
    return {
        "series": sid,
        "label": detail.get("label", ""),
        "description": detail.get("description", ""),
        "period": obs[-1]["d"],
        "value": float(obs[-1][sid]["v"]),
        "unit": "percent",
        "provenance": Provenance.OFFICIAL_DATASET.value,
        "source_url": valet_series.series_url(BOC_VALET, sid),
        "licence": "boc-terms",
        "attribution": R.sources()["licences"]["boc-terms"]["attribution"],
    }


# ── Builders (one per dataset card) ────────────────────────────────────────────

SECTORS_DIR = R.DATA_DIR / "sectors"
RAW_DIR = R.DATA_DIR / "raw" / "statcan"


def pull(ctx: Context, *, dataset: str, pull: str) -> Built:
    """One declared pull from registry/sectors.yaml, as its payload and a panel frame."""
    tax, codes = _load_taxonomy()
    spec = tax["pulls"][pull]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        series, payload = pull_cube(ctx.fetch, pull, spec, codes, RAW_DIR, refresh=ctx.refresh)
    except VintageUnknown as exc:
        raise Skipped(f"{exc} — {spec['output']} left as committed") from exc
    checks = []
    if spec.get("partition_check"):
        check_partition(series, tax)
        checks.append("partition_drift")
    ctx.state.setdefault("cube_hashes", {}).update(CUBE_HASHES)
    observations = observations_from_series(series, payload.get("status"))
    frame = frames.Frame(
        dataset=dataset, name="observations", profile="panel", record_type="observation",
        keys=frames.OBSERVATION_KEYS, columns=frames.OBSERVATION_COLUMNS,
        rows=[o.row() for o in observations],
        published=(f"data/sectors/{spec['output']}",), checks=tuple(checks),
        notes={"cube": spec["pid"], "frequency": spec["frequency"]},
    )
    releases = sorted({s.release_time for s in series})
    return Built(outputs=[(SECTORS_DIR / spec["output"], payload)], frames=[frame],
                 receipt={"cube": spec["pid"], "series": len(series), "observations": len(observations),
                          "releases": releases})


def cube_hashes(ctx: Context, *, dataset: str) -> Built:
    """The sha256 of every cube zip this run read, merged into the ones already recorded."""
    hashes = _previous_hashes(SECTORS_DIR)
    hashes.update(ctx.state.get("cube_hashes", {}))
    return Built(outputs=[(SECTORS_DIR / "_cubes.json", {
        "generated_at": clock.now_iso(),
        "note": "sha256 of each downloaded StatCan cube zip; the change signal "
                "for figures published in the bundle.",
        "cubes": dict(sorted(hashes.items())),
    })], receipt={"cubes": sorted(hashes)})


def policy_rate(ctx: Context, *, dataset: str) -> Built:
    """The Bank of Canada policy rate, or nothing if the Bank returned no observation."""
    rate = pull_policy_rate(ctx.fetch)
    if not rate:
        raise Skipped("Bank of Canada returned no observation — rates.json left as committed")
    log.info("policy rate %s = %.2f%%", rate["period"], rate["value"])
    obs = [{"entity": "CA", "category": rate["series"], "period": rate["period"], "measure": "policy_rate",
            "value": rate["value"], "unit": rate["unit"], "scalar": "", "slice": "", "status": "",
            "release": "", "source_table": rate["series"], "provenance": rate["provenance"]}]
    frame = frames.Frame(dataset=dataset, name="observations", profile="panel", record_type="observation",
                         keys=frames.OBSERVATION_KEYS, columns=frames.OBSERVATION_COLUMNS, rows=obs,
                         published=("data/sectors/rates.json",))
    return Built(outputs=[(SECTORS_DIR / "rates.json", {"generated_at": clock.now_iso(), "policy_rate": rate})],
                 frames=[frame], receipt={"series": rate["series"], "period": rate["period"]})
