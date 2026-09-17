"""
The one registry validator (atlas/core/registry.py, docs/REBUILD.md step S1).

Each negative control is an edit to a copy of registry/ that the old loaders
would have accepted without a word.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from atlas.core import registry as R


@pytest.fixture
def registry_copy(tmp_path, monkeypatch):
    """A scratch copy of registry/ that the validator reads instead of the real one."""
    root = tmp_path / "registry"
    shutil.copytree(R.REGISTRY_DIR, root)
    monkeypatch.setattr(R, "REGISTRY_DIR", root)
    for loader in (R.sources, R.events, R.strategies, R.project_naics, R.corridor_nodes, R.corridors):
        loader.cache_clear()
    yield root
    for loader in (R.sources, R.events, R.strategies, R.project_naics, R.corridor_nodes, R.corridors):
        loader.cache_clear()


def _edit(path: Path, change) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_the_real_registry_is_valid():
    assert R.validate_all() == []


def test_the_copy_is_valid_before_any_edit(registry_copy):
    # Without this, a negative control below could pass because the copy itself was broken.
    assert R.validate_all() == []


def test_sources_assemble_to_the_shape_callers_read():
    """meta.json and five stages read sources() as {licences, sources}; the cards must not change that."""
    srcs = R.sources()
    assert set(srcs) == {"licences", "sources"}
    assert srcs["sources"]["boc_valet"]["licence"] in srcs["licences"]
    assert R.source("statcan_municipal_population")["expected"]["census_subdivisions"] == 5161


def test_an_undeclared_registry_file_is_refused(registry_copy):
    (registry_copy / "notes.yaml").write_text("anything: true\n", encoding="utf-8")
    assert any("notes.yaml: not a declared registry file" in e for e in R.validate_all())


def test_a_card_folder_holds_only_yaml(registry_copy):
    (registry_copy / "sources" / "README.md").write_text("x\n", encoding="utf-8")
    assert any("card folders hold only .yaml files" in e for e in R.validate_all())


def test_a_misspelled_field_is_refused(registry_copy):
    """`licence_url` instead of a declared field used to load silently and be ignored."""
    _edit(registry_copy / "provinces.yaml", lambda d: d["provinces"]["ON"].update(fiscal_tabel=6))
    assert any("fiscal_tabel" in e for e in R.validate_all())


def test_a_wrong_type_is_refused(registry_copy):
    _edit(registry_copy / "sectors.yaml", lambda d: d["pulls"]["national_monthly"].update(partition_check="yes"))
    assert any("partition_check" in e for e in R.validate_all())


def test_an_unknown_province_key_is_refused(registry_copy):
    _edit(registry_copy / "budgets.yaml", lambda d: d["budgets"].update(XX=d["budgets"]["ON"]))
    assert any("'XX'" in e for e in R.validate_all())


def test_a_budget_quote_of_an_undeclared_kind_is_refused(registry_copy):
    """A quote framed as something the budget did not call it would be our reading, not theirs."""
    _edit(registry_copy / "budgets.yaml", lambda d: d["budgets"]["ON"]["quotes"][0].update(kind="warning"))
    assert any("warning" in e for e in R.validate_all())


def test_a_source_card_naming_an_undefined_licence_is_refused(registry_copy):
    _edit(registry_copy / "sources" / "boc_valet.yaml", lambda d: d.update(licence="made-up"))
    assert any("claims licence 'made-up'" in e for e in R.validate_all())


def test_a_source_card_without_a_publisher_is_refused(registry_copy):
    _edit(registry_copy / "sources" / "boc_valet.yaml", lambda d: d.pop("publisher"))
    assert any("publisher" in e for e in R.validate_all())


def test_the_per_file_rules_still_run_after_the_schemas(registry_copy):
    """A schema cannot see that a corridor names a port nobody placed; the file's own loader can."""
    _edit(registry_copy / "corridors.yaml", lambda d: d["corridors"][0]["ports"].append("atlantis"))
    assert any("atlantis" in e for e in R.validate_all())


def test_an_event_naming_an_unknown_source_card_is_refused(registry_copy):
    _edit(registry_copy / "events.yaml", lambda d: d["events"][0]["sources"].append("no_such_source"))
    assert any("no_such_source" in e for e in R.validate_all())


# ── Shell cards (docs/REBUILD.md step S2) ────────────────────────────────────

def test_a_shell_module_without_a_card_is_refused(registry_copy):
    (registry_copy / "shells" / "valet_series.yaml").unlink()
    assert any("valet_series.py: a shell module with no card" in e for e in R.validate_all())


def test_a_card_naming_a_function_its_module_lacks_is_refused(registry_copy):
    _edit(registry_copy / "shells" / "valet_series.yaml", lambda d: d["functions"].append("oldest"))
    assert any("defines no oldest" in e for e in R.validate_all())


def test_a_card_citing_a_test_that_does_not_exist_is_refused(registry_copy):
    _edit(registry_copy / "shells" / "valet_series.yaml",
          lambda d: d["tests"].append("tests/test_shells_acquire.py::test_nothing_like_this"))
    assert any("test_nothing_like_this does not exist" in e for e in R.validate_all())


def test_a_card_claiming_a_user_that_never_mentions_it_is_refused(registry_copy):
    _edit(registry_copy / "shells" / "valet_series.yaml", lambda d: d["used_by"].append("pipeline/99_bundle.py"))
    assert any("99_bundle.py never mentions valet_series" in e for e in R.validate_all())


def test_a_card_whose_module_path_disagrees_with_its_kind_is_refused(registry_copy):
    _edit(registry_copy / "shells" / "valet_series.yaml", lambda d: d.update(kind="transform"))
    assert any("module must be atlas.shells.transform.valet_series" in e for e in R.validate_all())
