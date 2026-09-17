"""
golden_io — record or replay every HTTP exchange a pipeline run makes, on a frozen clock.

Loaded only by the golden-master harness (`verify/golden.py`), through the
`sitecustomize.py` beside it, so a normal run never sees it.

WHY IT PATCHES `requests` AND NOT `atlas.net`

The restructure replaces `atlas.net`. A recorder hooked into the code under
test would move with that code, and a replay could then agree with a recording
because both sides changed together. `requests.Session.request` is the one
door every request in this project goes through, legacy or restructured, so
the recorder sits there and stays still while everything above it moves.

WHAT A REPLAY REFUSES

A request the recorded run never made raises `GoldenMiss`. New code therefore
cannot read anything the legacy run did not read, which is what makes
"identical output" mean "identical output from identical input".
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import requests
from requests.structures import CaseInsensitiveDict

#: The error classes a recorded failure may be replayed as. Anything else is
#: replayed as a plain RequestException, so an unknown name cannot be used to
#: construct an arbitrary object.
ERRORS = {
    "ConnectionError": requests.ConnectionError,
    "Timeout": requests.Timeout,
    "ConnectTimeout": requests.ConnectTimeout,
    "ReadTimeout": requests.ReadTimeout,
}


class GoldenMiss(RuntimeError):
    """A replayed run asked for something the recorded run never fetched."""


def request_key(method: str, url: str, params: Any = None, data: Any = None, json_body: Any = None) -> str:
    """One stable string per distinct request: method, full URL, and a hash of any body."""
    full = url
    if params:
        full += ("&" if "?" in url else "?") + urlencode(params, doseq=True)
    key = f"{method.upper()} {full}"
    if json_body is not None:
        body = json.dumps(json_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif data is not None:
        body = data if isinstance(data, bytes) else str(data).encode("utf-8")
    else:
        return key
    return f"{key} body:{hashlib.sha256(body).hexdigest()}"


class Store:
    """Response bodies addressed by content, and an append-only index of exchanges."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.bodies = self.root / "bodies"
        self.index_path = self.root / "http.jsonl"

    def load(self) -> dict[str, dict]:
        entries: dict[str, dict] = {}
        if self.index_path.exists():
            for line in self.index_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    entries[entry["key"]] = entry  # the last exchange for a key is what the run ended with
        return entries

    def body(self, sha: str) -> bytes:
        return (self.bodies / sha).read_bytes()

    def put_body(self, content: bytes) -> str:
        sha = hashlib.sha256(content).hexdigest()
        path = self.bodies / sha
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return sha

    def append(self, entry: dict) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


class Recorder:
    """Stands in for `requests.Session.request` in record or replay mode."""

    def __init__(self, store: Store, mode: str, real: Callable[..., requests.Response]):
        if mode not in ("record", "replay"):
            raise ValueError(f"mode must be record or replay, not {mode!r}")
        self.store = store
        self.mode = mode
        self.real = real
        self.entries = store.load() if mode == "replay" else {}

    def request(self, session, method, url, params=None, data=None, headers=None, json=None, **kwargs):
        key = request_key(method, url, params, data, json)
        if self.mode == "record":
            return self._record(session, key, method, url, params, data, headers, json, kwargs)
        return self._replay(key, method, url)

    def _record(self, session, key, method, url, params, data, headers, json_body, kwargs):
        try:
            resp = self.real(session, method, url, params=params, data=data, headers=headers, json=json_body, **kwargs)
        except requests.RequestException as exc:
            self.store.append({"key": key, "error": type(exc).__name__, "message": str(exc)})
            raise
        self.store.append({
            "key": key,
            "status": resp.status_code,
            "sha256": self.store.put_body(resp.content),
            "content_type": resp.headers.get("Content-Type"),
            "encoding": resp.encoding,
        })
        return resp

    def _replay(self, key, method, url):
        entry = self.entries.get(key)
        if entry is None:
            raise GoldenMiss(f"not in the recorded run: {key}")
        if "error" in entry:
            raise ERRORS.get(entry["error"], requests.RequestException)(entry["message"])
        resp = requests.models.Response()
        resp.status_code = entry["status"]
        resp._content = self.store.body(entry["sha256"])
        resp.headers = CaseInsensitiveDict({"Content-Type": entry["content_type"]} if entry["content_type"] else {})
        resp.encoding = entry["encoding"]
        resp.url = url
        resp.request = requests.Request(method, url).prepare()
        return resp


def install() -> None:
    """Patch this process from the GOLDEN_* environment variables. Called by sitecustomize."""
    mode = os.environ["GOLDEN_MODE"]
    recorder = Recorder(Store(Path(os.environ["GOLDEN_STORE"])), mode, requests.Session.request)

    def request(self, method, url, **kwargs):
        return recorder.request(self, method, url, **kwargs)

    requests.Session.request = request

    import time_machine

    time_machine.travel(os.environ["GOLDEN_CLOCK"], tick=False).start()
    if mode == "replay":
        # Every answer is already on disk; the fetcher's politeness delays and
        # retry backoff would only make a replay slower, never different.
        time.sleep = lambda seconds: None
