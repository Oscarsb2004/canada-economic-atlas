"""
Records, frames, the runner and dataset cards (docs/REBUILD.md step S4).

The runner is now the only thing that writes a published file, so its tests
are about what it refuses: a file its card did not declare, a frame that does
not meet its profile, and a skipped dataset overwriting what is committed.
"""

from __future__ import annotations

import json
import shutil

import pytest
import yaml

import atlas.run as runner
from atlas.core import frames
from atlas.core import registry as R
from atlas.core.records import Observation, municipality_records, observations_from_series
from atlas.core.schema import Municipality, Provenance, Series, Text
from atlas.datasets import Built, Context, Skipped


# ── Records ──────────────────────────────────────────────────────────────────

def _series(**kw):
    base = dict(code="T001", label=Text(en="All industries", fr="Ensemble des industries"), geo="CA",
                measure="gdp_chained", unit="Dollars", scalar="millions", frequency="monthly",
                periods=("2026-05", "2026-06"), values=(1.0, None), source_table="36100434",
                release_time="2026-08-28T08:30")
    base.update(kw)
    return Series(**base)


def test_a_series_becomes_one_observation_per_period_and_keeps_blanks_blank():
    obs = observations_from_series([_series()], {"CA/T001": ("", "x")})
    assert [(o.period, o.value, o.status) for o in obs] == [("2026-05", 1.0, ""), ("2026-06", None, "x")]
    assert obs[1].release == "2026-08-28T08:30" and obs[1].provenance == Provenance.OFFICIAL_DATASET.value


def test_a_municipality_becomes_a_place_and_its_counts():
    m = Municipality(csd_uid="1001101", dguid="2021A00051001101", name=Text(en="Subd. V", fr="Subd. V"),
                     province="NL", census_division_uid="1001", census_division_name=Text(en="Div 1", fr="Div 1"),
                     csd_type_abbr="SNO", csd_type=Text(en="Subdivision of unorganized", fr="Subdivision non organisée"),
                     population_2021=55, symbols={"population_2016": "r"})
    places, obs = municipality_records([m])
    assert places[0].key == "csd:2021:1001101" and places[0].parent == "cd:2021:1001"
    by = {(o.measure, o.period): o for o in obs}
    assert by[("population", "2021")].value == 55
    assert by[("population", "2016")].value is None and by[("population", "2016")].status == "r"


# ── Frames ───────────────────────────────────────────────────────────────────

def _frame(rows, **kw):
    base = dict(dataset="probe", name="observations", profile="panel", record_type="observation",
                keys=frames.OBSERVATION_KEYS, columns=frames.OBSERVATION_COLUMNS, rows=rows)
    base.update(kw)
    return frames.Frame(**base)


def _row(**kw):
    return Observation(**{"entity": "CA", "category": "T001", "period": "2026-06", "measure": "m",
                          "value": 1.0, **kw}).row()


def test_a_frame_is_written_the_same_way_whatever_order_its_rows_came_in(tmp_path):
    rows = [_row(period="2026-06"), _row(period="2026-05", value=None)]
    body_a, man_a = frames.write(_frame(rows), tmp_path / "a")
    body_b, man_b = frames.write(_frame(list(reversed(rows))), tmp_path / "b")
    assert body_a.read_bytes() == body_b.read_bytes()
    assert man_a.read_bytes() == man_b.read_bytes()
    manifest = json.loads(man_a.read_text(encoding="utf-8"))
    assert manifest["rows"] == 2 and manifest["coverage"]["missing_values"] == 1
    assert {c["role"] for c in manifest["columns"]} >= frames.PROFILES["panel"]


def test_a_frame_with_a_duplicate_key_is_refused():
    with pytest.raises(frames.FrameError, match="duplicate key"):
        _frame([_row(), _row(value=2.0)]).validate()


def test_a_frame_missing_a_role_its_profile_needs_is_refused():
    columns = tuple(c for c in frames.OBSERVATION_COLUMNS if c.role != "time")
    rows = [{k: v for k, v in _row().items() if k != "period"}]
    with pytest.raises(frames.FrameError, match="needs roles \\['time'\\]"):
        _frame(rows, columns=columns, keys=("entity", "category", "measure", "slice")).validate()


def test_a_frame_value_of_the_wrong_type_is_refused():
    """A number published as text would sort and sum wrongly and look fine."""
    with pytest.raises(frames.FrameError, match="is not number"):
        _frame([_row(value="1.0")]).validate()


# ── The runner ───────────────────────────────────────────────────────────────

def build_probe(ctx, *, dataset, target, skip=False, stray=False):
    """A builder for the runner's tests: named by the cards below as tests.test_datasets:build_probe."""
    if skip:
        raise Skipped("the source had nothing new")
    path = R.ROOT / ("data/other.json" if stray else target)
    return Built(outputs=[(path, {"generated_at": "now", "value": 1})],
                 frames=[_frame([_row()], dataset=dataset)], receipt={"rows": 1})


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "BUILD_DIR", tmp_path / "build")
    (tmp_path / "data").mkdir()
    return tmp_path


def _card(**params):
    return {"title": "probe", "builder": "tests.test_datasets:build_probe", "outputs": ["data/probe.json"],
            "params": {"target": "data/probe.json", **params}}


def test_the_runner_writes_the_output_a_frame_and_a_receipt(sandbox):
    receipt = runner.run_card(Context(fetch=None), "probe", _card())
    assert json.loads((sandbox / "data/probe.json").read_text(encoding="utf-8"))["value"] == 1
    assert (sandbox / "build/frames/probe/observations.jsonl").exists()
    assert receipt["outputs"]["data/probe.json"]["changed"] is True
    assert json.loads((sandbox / "build/receipts/probe.json").read_text(encoding="utf-8"))["values"] == {"rows": 1}
    # A second run with the same content leaves the file alone (CLAUDE.md §6).
    assert runner.run_card(Context(fetch=None), "probe", _card())["outputs"]["data/probe.json"]["changed"] is False


def test_the_runner_refuses_a_file_the_card_does_not_declare(sandbox):
    with pytest.raises(RuntimeError, match="does not declare"):
        runner.run_card(Context(fetch=None), "probe", _card(stray=True))
    assert not (sandbox / "data/other.json").exists()


def test_a_skipped_dataset_leaves_the_committed_file_alone(sandbox):
    (sandbox / "data/probe.json").write_text('{"committed": true}', encoding="utf-8")
    receipt = runner.run_card(Context(fetch=None), "probe", _card(skip=True))
    assert receipt["skipped"] == "the source had nothing new"
    assert (sandbox / "data/probe.json").read_text(encoding="utf-8") == '{"committed": true}'


def test_every_card_in_a_group_runs_in_its_declared_order():
    economy = R.dataset_groups()["economy"]
    assert economy.index("gdp-national-annual-current") < economy.index("gross-output-annual")
    assert economy[-2:] == ["statcan-cube-hashes", "policy-rate"]


# ── Dataset cards (negative controls on a copy of registry/) ────────────────

@pytest.fixture
def registry_copy(tmp_path, monkeypatch):
    root = tmp_path / "registry"
    shutil.copytree(R.REGISTRY_DIR, root)
    monkeypatch.setattr(R, "REGISTRY_DIR", root)
    R.sources.cache_clear()
    yield root
    R.sources.cache_clear()


def _edit(path, change):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_the_real_dataset_cards_agree_with_the_repository():
    assert R.dataset_errors() == []


def test_a_card_whose_builder_is_not_defined_is_refused(registry_copy):
    _edit(registry_copy / "datasets/policy-rate.yaml", lambda d: d.update(builder="atlas.datasets.statcan_sectors:nothing"))
    assert any("defines no nothing" in e for e in R.dataset_errors())


def test_a_card_running_after_a_later_card_is_refused(registry_copy):
    _edit(registry_copy / "datasets/gdp-national-monthly.yaml", lambda d: d["after"].append("policy-rate"))
    assert any("not earlier in group economy" in e for e in R.dataset_errors())


def test_a_consumer_that_never_names_the_output_is_refused(registry_copy):
    """`consumed_by` is a claim that someone reads the file; the claimed reader must at least name it."""
    _edit(registry_copy / "datasets/capex-annual.yaml",
          lambda d: d["consumed_by"].append({"path": "run.py", "how": "it does not"}))
    assert any("consumer run.py names none of this card's outputs" in e for e in R.dataset_errors())


def test_an_output_no_consumer_names_is_refused(registry_copy):
    """A dataset nothing reads is the sprawl this restructure exists to stop."""
    _edit(registry_copy / "datasets/major-projects.yaml",
          lambda d: d.update(consumed_by=[c for c in d["consumed_by"] if c["path"] != "registry/checks.yaml"]))
    assert any("no consumer names coverage.json" in e for e in R.dataset_errors())


def test_a_group_no_run_step_makes_is_refused(registry_copy):
    _edit(registry_copy / "datasets/policy-rate.yaml", lambda d: d.update(group="orphans"))
    assert any("group orphans is not a step in run.py" in e for e in R.dataset_errors())


def test_a_declared_pull_without_a_card_is_refused(registry_copy):
    (registry_copy / "datasets/capex-annual.yaml").unlink()
    assert any("pull capex_annual has no dataset card" in e for e in R.dataset_errors())


def test_an_output_that_is_not_committed_is_refused(registry_copy):
    _edit(registry_copy / "datasets/policy-rate.yaml", lambda d: d["outputs"].append("data/sectors/nowhere.json"))
    assert any("nowhere.json is not in the repository" in e for e in R.dataset_errors())


# ── Passages (docs/REBUILD.md step S5) ───────────────────────────────────────

def test_a_passage_frame_carries_where_the_words_were_found():
    """A quote without its document and locator cannot be checked again, which is the point of quoting."""
    from atlas.core.records import Passage

    rows = [Passage(entity="ON", kind="budget_risk", text_en="Tariffs remain a risk.", text_fr="",
                    source_url="https://budget.example/plan.pdf", locator="page 12",
                    provenance="page_verbatim").row()]
    frame = frames.Frame(dataset="probe", name="passages", profile="passages", record_type="passage",
                         keys=frames.PASSAGE_KEYS, columns=frames.PASSAGE_COLUMNS, rows=rows)
    frame.validate()
    assert {c.role for c in frames.PASSAGE_COLUMNS} >= frames.PROFILES["passages"]

    without_source = tuple(c for c in frames.PASSAGE_COLUMNS if c.role != "source_ref")
    stripped = [{k: v for k, v in rows[0].items() if k not in ("source_url", "locator", "content_sha256")}]
    with pytest.raises(frames.FrameError, match="needs roles \['source_ref'\]"):
        frames.Frame(dataset="probe", name="passages", profile="passages", record_type="passage",
                     keys=("entity", "kind", "text_en"), columns=without_source, rows=stripped).validate()
