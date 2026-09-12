#!/usr/bin/env python3
"""
run.py — the only command this project needs.

    python run.py                 run the whole pipeline, then verify
    python run.py --stage 01      run one stage (see --help for the list)
    python run.py --verify        independent verification only
    python run.py --test          pytest only
    python run.py --live          the atlas in your browser, with live Canadian vessel positions
                                  on the globe (needs `npm install` in web/, and AISSTREAM_API_KEY
                                  in .env for the ships; without it the published snapshot shows)
    python run.py --web           the same
    python run.py --refresh       bypass the HTTP cache when pulling

On first use it creates `.venv`, installs `requirements.txt` into it, and
re-executes itself inside it. There is nothing to activate by hand.

The bootstrap is cached on a hash of the requirements file, so it reinstalls
only when the pins actually change — following African-Stability-Index's
`run_asi.py`, which is the one piece of that project this repo copies almost
verbatim because it solves the problem completely.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
STAMP = VENV / ".atlas-requirements"

#: Stage number -> script. A full run executes these in SORTED KEY ORDER, so the
#: number is the run order and the bundle must sort last.
#:
#: That is why the bundle is 99 rather than the next free number. It reads what
#: the other stages wrote,
#: so a stage numbered above it would have its output bundled a run late: the
#: first run would ship nothing and the second would ship the first run's data.
#: Silent, and it would read as a caching bug. Numbering the bundle last leaves
#: every future stage room in between. `test_the_bundle_is_the_last_stage` makes
#: the rule mechanical rather than a comment.
STAGES = {
    "01": "pipeline/01_projects.py",
    "02": "pipeline/02_sectors.py",
    "03": "pipeline/03_business_counts.py",
    "04": "pipeline/04_trade.py",
    "05": "pipeline/05_municipalities.py",
    "06": "pipeline/06_industries.py",
    "07": "pipeline/07_vessels.py",
    "99": "pipeline/99_bundle.py",
}


def _requirements_digest() -> str:
    return hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()


def bootstrap() -> None:
    """Create and populate .venv, then re-exec inside it."""
    if not PY.exists():
        print("creating .venv ...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

    digest = _requirements_digest()
    if not STAMP.exists() or STAMP.read_text(encoding="utf-8").strip() != digest:
        print("installing requirements ...")
        subprocess.run(
            [str(PY), "-m", "pip", "install", "--quiet", "-r", str(ROOT / "requirements.txt")],
            check=True,
        )
        STAMP.write_text(digest, encoding="utf-8")

    os.execv(str(PY), [str(PY), str(Path(__file__).resolve()), *sys.argv[1:]])


def inside_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == PY.resolve()
    except OSError:
        return False


def run(*args: str) -> int:
    return subprocess.run([sys.executable, *args], cwd=ROOT).returncode


def app() -> int:
    """
    The atlas in the browser, with live Canadian vessel positions on its globe.

    One command starts both halves. They were two once — `--live` ran only the
    collector, which answers with raw JSON, and `--web` only the app — so on
    2026-09-12 the feed was opened in a browser tab and read as a page of text
    while the globe that draws it was never started.

    The collector is a child process, not a stage: live positions never satisfy
    a zero-line re-run, so they stay out of the pipeline and out of data/
    (docs/AIS.md). Without an aisstream.io key it prints why and exits, and the
    atlas runs on the published snapshot.
    """
    web = ROOT / "web"
    vite = web / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if not (vite.exists() and node):
        print("the app needs Node.js and `npm install` in web/ first", file=sys.stderr)
        return 1

    collector = subprocess.Popen([sys.executable, "live/collect_ais.py", "--serve"], cwd=ROOT)
    try:
        # Vite directly rather than `npm run dev`: npm is a .cmd on Windows, and
        # Ctrl+C in a .cmd stops at "Terminate batch job (Y/N)?".
        return subprocess.run([node, str(vite), "--open"], cwd=web).returncode
    except KeyboardInterrupt:
        return 0
    finally:
        # Ctrl+C reaches the collector through the console too, and it writes
        # data/raw/live/positions.json on the way out; give it time to.
        try:
            collector.wait(timeout=10)
        except subprocess.TimeoutExpired:
            collector.terminate()


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=sorted(STAGES))
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--web", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if args.test:
        return run("-m", "pytest", "tests/", "-q")

    if args.verify:
        return run("-m", "verify.run")

    if args.live or args.web:
        return app()

    extra = ["--refresh"] if args.refresh else []

    if args.stage:
        return run(STAGES[args.stage], *extra)

    # Full run: stages in order, then verification. Any stage failing stops the
    # run — a later stage reading a half-written earlier output is how a bad
    # bundle gets committed.
    for key in sorted(STAGES):
        print(f"\n=== stage {key} ===")
        code = run(STAGES[key], *extra)
        if code != 0:
            print(f"stage {key} failed", file=sys.stderr)
            return code

    print("\n=== verify ===")
    return run("-m", "verify.run")


if __name__ == "__main__":
    if not inside_venv():
        bootstrap()
    raise SystemExit(main())
