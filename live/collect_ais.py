#!/usr/bin/env python3
"""
live/collect_ais.py — listen to aisstream.io and keep a snapshot of where
Canadian-flagged vessels were last heard (BACKLOG S2).

    python run.py --live
        Localhost. Listens until stopped, and serves the current snapshot at
        http://127.0.0.1:8765/ships, which the dev server proxies at
        /api/live/ships. Also keeps data/raw/live/positions.json, so the next
        session starts from what this one heard.

    python live/collect_ais.py --seconds 900 --previous previous.json --out positions.json
        What the daily GitHub Action runs: listen for a fixed window, merge into
        the previous snapshot, write, stop.

NOT A PIPELINE STAGE

Live positions change every run, so they can never satisfy the zero-line
re-run rule (CLAUDE.md §6) and are never written under data/ outside
data/raw/. The published snapshot lives on the repository's `vessel-positions`
branch and reaches the site at build time (.github/workflows/deploy.yml).

THE API KEY

Read from the AISSTREAM_API_KEY environment variable, or from a `.env` file at
the repository root (gitignored). Never a command-line argument, which would
land in shell history, and never sent to the browser: aisstream.io forbids
browser connections, which is why this process exists at all.

WHOLE WORLD, FILTERED HERE

aisstream.io filters by bounding box and by an explicit MMSI list, not by MMSI
prefix, so the collector subscribes to the whole world and keeps only Canadian
vessels. Whether a world-sized box is accepted, and how many messages a second
it brings, is logged on every run — neither was measured before this was built.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atlas.core import registry as R  # noqa: E402
from atlas.sources import aisstream as A  # noqa: E402

log = logging.getLogger("collect_ais")

WORLD = [[[-90, -180], [90, 180]]]
LIVE_DIR = R.DATA_DIR / "raw" / "live"
REGISTER = R.DATA_DIR / "vessels" / "large-vessel-register.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def api_key() -> str:
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if key:
        return key
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "AISSTREAM_API_KEY" and value.strip():
                return value.strip().strip('"').strip("'")
    raise SystemExit(
        "AISSTREAM_API_KEY is not set. Create a free key at https://aisstream.io, then put the "
        "line AISSTREAM_API_KEY=... in .env at the repository root (docs/AIS.md)."
    )


def _load(path: Path | None) -> dict[str, Any] | None:
    if path and path.exists() and path.stat().st_size:
        return json.loads(path.read_text(encoding="utf-8"))
    return None


class Collector:
    def __init__(self, previous: dict[str, Any] | None) -> None:
        src = R.source("aisstream")
        self.stream_url = src["stream"]
        self.mids = tuple(src["canadian_mids"])
        self.feed = {"title": src["title"], "url": src["documentation"], "provenance": "third_party",
                     "licence": src["licence"]}
        reg_src = R.source("tc_large_vessel_register")
        self.register_source = {"title": reg_src["title"], "url": reg_src["dataset_record"],
                                "provenance": "official_dataset", "licence": reg_src["licence"]}
        self.register = A.register_index(json.loads(REGISTER.read_text(encoding="utf-8")))
        self.previous = previous
        self.tracker = A.Tracker()
        self.started = _now()
        self.lock = threading.Lock()

    def ingest(self, message: dict[str, Any]) -> None:
        with self.lock:
            self.tracker.ingest(message, _now())

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            doc = A.build_snapshot(self.tracker, self.previous, self.register,
                                   window_from=self.started, window_to=_now(), feed=self.feed,
                                   register_source=self.register_source, mids=self.mids)
        A.validate_snapshot(doc)
        return doc

    async def listen(self, key: str, until: float | None) -> None:
        import websockets

        subscription = json.dumps({"APIKey": key, "BoundingBoxes": WORLD,
                                   "FilterMessageTypes": list(A.MESSAGE_TYPES)})
        backoff = 1.0
        while until is None or time.monotonic() < until:
            try:
                # aisstream.io's own client enables deflate: it "requires" it
                # to serve full message bandwidth.
                async with websockets.connect(self.stream_url, compression="deflate",
                                              max_size=2 ** 22, open_timeout=20) as ws:
                    await ws.send(subscription)
                    log.info("subscribed to the whole world")
                    backoff = 1.0
                    last_report, last_count = time.monotonic(), self.tracker.messages
                    while until is None or time.monotonic() < until:
                        timeout = None if until is None else max(0.1, until - time.monotonic())
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        except asyncio.TimeoutError:
                            return
                        message = json.loads(raw)
                        if isinstance(message, dict) and "error" in message:
                            raise SystemExit(f"aisstream.io refused the subscription: {message['error']}")
                        self.ingest(message)
                        if time.monotonic() - last_report >= 60:
                            rate = (self.tracker.messages - last_count) / (time.monotonic() - last_report)
                            log.info("%.0f messages/s · %d vessels heard", rate, len(self.tracker.heard))
                            last_report, last_count = time.monotonic(), self.tracker.messages
            except SystemExit:
                raise
            except Exception as exc:  # the stream drops; reconnect rather than lose the window
                log.warning("stream closed (%s); reconnecting in %.0f s", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)


def _write(doc: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def serve(collector: Collector, port: int) -> None:
    state: dict[str, bytes] = {"body": b'{"vessels":[]}'}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — the stdlib's name
            if self.path.split("?")[0] != "/ships":
                self.send_error(404)
                return
            body = state["body"]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("serving http://127.0.0.1:%d/ships — the dev server proxies it at /api/live/ships", port)

    async def refresh() -> None:
        while True:
            await asyncio.sleep(15)
            doc = collector.snapshot()
            state["body"] = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            _write(doc, LIVE_DIR / "positions.json")

    async def main() -> None:
        await asyncio.gather(collector.listen(api_key(), None), refresh())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        doc = collector.snapshot()
        _write(doc, LIVE_DIR / "positions.json")
        log.info("stopped · %d Canadian vessels kept in data/raw/live/positions.json", len(doc["vessels"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serve", action="store_true", help="listen until stopped and serve /ships on localhost")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--seconds", type=int, help="listen for this long, write --out, and stop")
    ap.add_argument("--previous", type=Path, help="the last published snapshot, merged into")
    ap.add_argument("--out", type=Path, help="where to write the snapshot")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    if args.serve:
        serve(Collector(_load(LIVE_DIR / "positions.json")), args.port)
        return 0
    if not (args.seconds and args.out):
        ap.error("use --serve, or --seconds with --out")

    collector = Collector(_load(args.previous))
    asyncio.run(collector.listen(api_key(), time.monotonic() + args.seconds))
    doc = collector.snapshot()
    _write(doc, args.out)
    w = doc["window"]
    log.info("%d messages · %d vessels heard worldwide · %d Canadian heard this window · %d published",
             w["messages"], w["vessels_heard_worldwide"], w["canadian_heard_this_window"], len(doc["vessels"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
