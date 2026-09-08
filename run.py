#!/usr/bin/env python3
"""
run.py — the only command this project needs.

    python run.py                 run the whole pipeline, then verify
    python run.py --stage 01      run one stage (see --help for the list)
    python run.py --verify        independent verification only
    python run.py --test          pytest only
    python run.py --web           the dev server (needs `npm install` in web/)
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
#: That is why the bundle is 99 and not 05. It reads what the other stages wrote,
#: so a stage numbered above it would have its output bundled a run late: the
#: first run would ship nothing and the second would ship the first run's data.
#: Silent, and it would read as a caching bug. Numbering the bundle last leaves
#: every future stage room in between. `test_the_bundle_is_the_last_stage` makes
#: the rule mechanical rather than a comment.
STAGES = {
    "01": "pipeline/01_projects.py",
    "02": "pipeline/02_sectors.py",
    "03": "pipeline/03_companies.py",
    "04": "pipeline/04_trade.py",
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


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=sorted(STAGES))
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--web", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if args.test:
        return run("-m", "pytest", "tests/", "-q")

    if args.verify:
        return run("-m", "verify.run")

    if args.web:
        web = ROOT / "web"
        if not (web / "node_modules").exists():
            print("web/node_modules is missing — run `npm install` in web/ first", file=sys.stderr)
            return 1
        # npm is a .cmd on Windows and needs a shell there; nothing here takes
        # outside input, and the alternative is resolving the shim by hand.
        return subprocess.run("npm run dev", cwd=web, shell=True).returncode

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
