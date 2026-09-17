"""
Tests for the golden-master harness (verify/golden.py, docs/REBUILD.md §3).

The harness is what lets the restructure claim "nothing changed", so each test
names the way that claim could become false without anyone noticing.
None of these touch the network.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
from pathlib import Path

import pytest
import requests

from verify import golden

sys.path.insert(0, str(golden.SITE))
import golden_io  # noqa: E402


# ── The comparison ───────────────────────────────────────────────────────────

def _tree(tmp_path: Path, files: dict[str, bytes]) -> Path:
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return tmp_path


def test_identical_trees_compare_equal(tmp_path):
    a = _tree(tmp_path / "a", {"data/x.json": b"{}", "web/public/data/y.json": b"[]"})
    b = _tree(tmp_path / "b", {"data/x.json": b"{}", "web/public/data/y.json": b"[]"})
    assert golden.identical(golden.compare_manifests(golden.output_manifest(a), golden.output_manifest(b)))


def test_one_changed_byte_is_reported(tmp_path):
    """Negative control: without it, a comparison that always said "identical" would pass the restructure."""
    a = _tree(tmp_path / "a", {"data/x.json": b'{"v": 1}'})
    b = _tree(tmp_path / "b", {"data/x.json": b'{"v": 2}'})
    diff = golden.compare_manifests(golden.output_manifest(a), golden.output_manifest(b))
    assert diff["changed"] == ["data/x.json"]


def test_a_missing_and_an_extra_file_are_both_reported(tmp_path):
    """A stage that stops writing a file, or starts writing a new one, is a change to the site."""
    a = _tree(tmp_path / "a", {"data/old.json": b"{}"})
    b = _tree(tmp_path / "b", {"data/new.json": b"{}"})
    diff = golden.compare_manifests(golden.output_manifest(a), golden.output_manifest(b))
    assert diff == {"missing": ["data/old.json"], "extra": ["data/new.json"], "changed": []}


def test_raw_inputs_are_not_counted_as_outputs(tmp_path):
    """data/raw holds inputs and caches; counting it would make every replay differ for no reason."""
    tree = _tree(tmp_path, {"data/raw/cache/abc.bin": b"x", "data/out.json": b"{}"})
    assert list(golden.output_manifest(tree)) == ["data/out.json"]


def test_every_folder_the_site_serves_is_an_output(tmp_path):
    tree = _tree(tmp_path, {
        "web/public/data/meta.json": b"{}",
        "web/public/media/thumb/a.png": b"p",
        "web/public/geo/world.json": b"{}",
    })
    assert sorted(golden.output_manifest(tree)) == [
        "web/public/data/meta.json", "web/public/geo/world.json", "web/public/media/thumb/a.png",
    ]


# ── Recording and replay ─────────────────────────────────────────────────────

class _Answer:
    """A fake network: returns a fixed response and counts how often it was asked."""

    def __init__(self, status=200, body=b"hello", content_type="text/plain"):
        self.calls = 0
        self.status, self.body, self.content_type = status, body, content_type

    def __call__(self, session, method, url, **kwargs):
        self.calls += 1
        resp = requests.models.Response()
        resp.status_code = self.status
        resp._content = self.body
        resp.headers["Content-Type"] = self.content_type
        resp.encoding = "utf-8"
        return resp


def _no_network(session, method, url, **kwargs):
    raise AssertionError("a replay reached the network")


def test_a_replay_returns_what_was_recorded_without_the_network(tmp_path):
    store = golden_io.Store(tmp_path)
    network = _Answer(status=200, body=b"cube bytes")
    golden_io.Recorder(store, "record", network).request(None, "GET", "https://example.test/a")
    assert network.calls == 1

    resp = golden_io.Recorder(store, "replay", _no_network).request(None, "GET", "https://example.test/a")
    assert (resp.status_code, resp.content, resp.headers["Content-Type"]) == (200, b"cube bytes", "text/plain")


def test_a_replay_refuses_a_request_the_recording_never_made(tmp_path):
    """Negative control: new code must not be able to read something the legacy run did not."""
    store = golden_io.Store(tmp_path)
    golden_io.Recorder(store, "record", _Answer()).request(None, "GET", "https://example.test/a")
    with pytest.raises(golden_io.GoldenMiss):
        golden_io.Recorder(store, "replay", _no_network).request(None, "GET", "https://example.test/b")


def test_a_post_with_a_different_body_is_a_different_request(tmp_path):
    """StatCan's metadata calls share one URL; answering one table's POST with another's is a wrong number."""
    store = golden_io.Store(tmp_path)
    golden_io.Recorder(store, "record", _Answer(body=b"table 1")).request(None, "POST", "https://x.test/meta", json=[{"productId": 1}])
    replay = golden_io.Recorder(store, "replay", _no_network)
    assert replay.request(None, "POST", "https://x.test/meta", json=[{"productId": 1}]).content == b"table 1"
    with pytest.raises(golden_io.GoldenMiss):
        replay.request(None, "POST", "https://x.test/meta", json=[{"productId": 2}])


def test_a_refused_request_replays_as_refused(tmp_path):
    """Yukon's site answers 403, and stage 08 falls back to a saved copy; the replay must take the same path."""
    store = golden_io.Store(tmp_path)
    golden_io.Recorder(store, "record", _Answer(status=403, body=b"")).request(None, "GET", "https://yukon.test/budget.pdf")
    assert golden_io.Recorder(store, "replay", _no_network).request(None, "GET", "https://yukon.test/budget.pdf").status_code == 403


def test_a_connection_failure_replays_as_the_same_failure(tmp_path):
    store = golden_io.Store(tmp_path)

    def down(session, method, url, **kwargs):
        raise requests.ConnectionError("host unreachable")

    with pytest.raises(requests.ConnectionError):
        golden_io.Recorder(store, "record", down).request(None, "GET", "https://down.test/")
    with pytest.raises(requests.ConnectionError):
        golden_io.Recorder(store, "replay", _no_network).request(None, "GET", "https://down.test/")


def test_the_last_exchange_for_a_url_is_the_one_replayed(tmp_path):
    """A retried request ends with its final answer; that answer is what the run acted on."""
    store = golden_io.Store(tmp_path)
    golden_io.Recorder(store, "record", _Answer(status=502, body=b"")).request(None, "GET", "https://x.test/")
    golden_io.Recorder(store, "record", _Answer(status=200, body=b"ok")).request(None, "GET", "https://x.test/")
    assert golden_io.Recorder(store, "replay", _no_network).request(None, "GET", "https://x.test/").content == b"ok"


def test_query_parameters_are_part_of_the_request():
    assert golden_io.request_key("GET", "https://x.test/q", params={"f": "json"}) != golden_io.request_key("GET", "https://x.test/q")


def test_the_stage_list_is_read_without_importing_run_py(tmp_path):
    """Importing run.py would bootstrap a virtual environment inside the scratch copy."""
    (tmp_path / "run.py").write_text('import sys\nsys.exit("imported")\nSTAGES = {"02": "b.py", "01": "a.py"}\n', encoding="utf-8")
    assert golden.stages_of(tmp_path) == {"02": "b.py", "01": "a.py"}


# ── The deployed site ────────────────────────────────────────────────────────

class _Served:
    """A stand-in for the deployed site: paths it serves, and everything else 404s."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.asked: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kwargs):
        rel = url.split("/canada-economic-atlas/", 1)[1]
        self.asked.append(rel)
        body = self.files.get(rel)
        answer = _Answer(status=200 if body is not None else 404, body=body or b"")
        response = answer(None, "GET", url)
        # `with session.get(...)` closes the response, and a 404 is closed
        # without its body ever being read, which reaches raw.
        response.raw = io.BytesIO(body or b"")
        response.iter_content = lambda size: iter([response.content] if response.content else [])
        return response


def _live(monkeypatch, files, manifest_path):
    served = _Served(files)
    monkeypatch.setattr(requests, "Session", lambda: served)
    code = golden.cmd_live(argparse.Namespace(
        manifest=str(manifest_path), url="https://x.test/canada-economic-atlas"))
    return code, served


def _manifest(tmp_path: Path, files: dict[str, bytes]) -> Path:
    path = tmp_path / "site.json"
    golden.write_json(path, {"files": {
        "dist/" + rel: {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
        for rel, body in files.items()}})
    return path


def test_a_site_serving_the_build_is_identical(tmp_path, monkeypatch):
    files = {"index.html": b"<!doctype html>", "data/meta.json": b'{"app": "atlas"}'}
    code, served = _live(monkeypatch, files, _manifest(tmp_path, files))
    assert code == 0
    assert sorted(served.asked) == ["data/meta.json", "index.html"]


def test_a_site_serving_one_different_byte_is_not_identical(tmp_path, monkeypatch):
    built = {"index.html": b"<!doctype html>", "data/meta.json": b'{"app": "atlas"}'}
    serving = {**built, "data/meta.json": b'{"app": "atlaS"}'}
    code, _ = _live(monkeypatch, serving, _manifest(tmp_path, built))
    assert code == 1


def test_a_file_the_site_does_not_serve_is_not_identical(tmp_path, monkeypatch):
    built = {"index.html": b"<!doctype html>", "assets/index-abc.js": b"console.log(1)"}
    code, _ = _live(monkeypatch, {"index.html": built["index.html"]}, _manifest(tmp_path, built))
    assert code == 1


def test_a_linux_export_writes_lf_where_a_native_one_writes_the_platform_ending(tmp_path):
    """The runner builds on ubuntu-latest, so a build compared with it must be LF."""
    lf = golden.export("HEAD", tmp_path / "lf", eol="lf")
    native = golden.export("HEAD", tmp_path / "native")
    assert lf == native
    body = (tmp_path / "lf" / "web" / "index.html").read_bytes()
    assert b"\r\n" not in body
    if os.linesep == "\r\n":
        assert b"\r\n" in (tmp_path / "native" / "web" / "index.html").read_bytes()
