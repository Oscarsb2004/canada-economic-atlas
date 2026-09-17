#!/usr/bin/env python3
"""
verify/golden.py — the golden master for the restructure (docs/REBUILD.md §3).

    python verify/golden.py record --ref legacy-v1 --name legacy-v1
    python verify/golden.py replay --name legacy-v1            # the working tree
    python verify/golden.py replay --name legacy-v1 --ref HEAD
    python verify/golden.py dist   --ref legacy-v1 --out verify/golden/legacy-v1/dist.json
    python verify/golden.py dist   --ref main --out build/site.json --base /canada-economic-atlas/
    python verify/golden.py live   --manifest build/site.json --url https://oscarsb2004.github.io/canada-economic-atlas
    python verify/golden.py compare A.json B.json

WHY THIS EXISTS

The restructure promises that the site does not change. That is a claim about
bytes, so it is checked on bytes:

  record   runs a revision's whole pipeline once, in a scratch copy, through a
           recorder that stores every HTTP exchange and on a frozen clock. The
           raw files the pipeline reads from disk are captured too. What the run
           wrote is the golden master.
  replay   runs another revision in a fresh scratch copy on exactly those inputs.
           A request the recorded run never made fails the run. Its outputs must
           equal the golden master byte for byte.
  dist     builds the site from a revision and hashes web/dist, so two
           revisions can be shown to serve the same site. With --base it builds
           what the runner builds, which is what `live` can be compared with.
  live     hashes what the deployed site actually serves, file by file, and
           compares it with such a build.
  compare  the comparison both use, runnable on any two manifests.

Nothing here imports `atlas` (CLAUDE.md §4). The scratch copies and the stored
inputs live under data/raw/golden/, which git ignores. What is committed is the
manifests under verify/golden/<name>/: small, reviewable, and enough to say
exactly which inputs and outputs a claim of identity rests on.

WHAT COUNTS AS OUTPUT

Every file under data/ except data/raw/, and every file under web/public/. A
replay must start from the same committed outputs the recording started from,
because a stage rewrites a file only when its content changed; two runs that
start from different files are not comparable, and the harness refuses them.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(__file__).resolve().parent / "golden_site"
#: Where recordings and scratch copies live. ATLAS_GOLDEN_HOME points a second
#: checkout (a worktree) at the recordings the first one made.
GOLDEN_ROOT = Path(os.environ.get("ATLAS_GOLDEN_HOME") or ROOT / "data" / "raw" / "golden")
MANIFESTS = ROOT / "verify" / "golden"

#: Raw folders the pipeline reads from disk rather than fetching every run.
#: data/raw/cache is deliberately absent: every exchange goes through the recorder.
#: data/raw/geo is absent because no Python stage reads it (scripts/build_geo.mjs does).
SEEDED_RAW = ("statcan", "media", "transport-canada", "budgets", "nrcan")

#: The instant every run sees. Changing it changes every timestamp a run writes.
DEFAULT_CLOCK = "2026-09-17T12:00:00+00:00"

WORKTREE = "WORKTREE"


# ── Files ────────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_tree(root: Path, include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> dict[str, dict]:
    """relative path → {sha256, bytes} for every file under the included folders."""
    found: dict[str, dict] = {}
    for top in include:
        base = root / top
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and not any(rel == e or rel.startswith(e + "/") for e in exclude):
                found[rel] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    return found


def output_manifest(tree: Path) -> dict[str, dict]:
    return hash_tree(tree, ("data", "web/public"), exclude=("data/raw",))


def compare_manifests(expected: dict[str, dict], actual: dict[str, dict]) -> dict[str, list[str]]:
    """Every difference between two manifests, named. Empty lists mean identical."""
    return {
        "missing": sorted(set(expected) - set(actual)),
        "extra": sorted(set(actual) - set(expected)),
        "changed": sorted(p for p in set(expected) & set(actual) if expected[p]["sha256"] != actual[p]["sha256"]),
    }


def identical(diff: dict[str, list[str]]) -> bool:
    return not any(diff.values())


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


# ── Revisions ────────────────────────────────────────────────────────────────

def export(ref: str, dest: Path, *, eol: str = "native") -> str:
    """Materialise a revision (or the working tree) in `dest`; return what was exported.

    `eol="lf"` exports the bytes a Linux checkout would have. `.gitattributes`
    says `* text=auto`, so on Windows `git archive` writes CRLF into every text
    file — which is right for a replay (the recording was exported the same way)
    and wrong for a build meant to be compared with the deployed site, whose
    runner is ubuntu-latest. core.eol defaults to native, so both it and
    core.autocrlf have to be overridden to get the runner's bytes.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    label = None
    if ref == WORKTREE:
        # Exported through git, never copied off disk: the working copy's bytes can
        # differ from git's (line-ending normalisation rewrote three geometry files
        # on this machine), and the recording was exported through git too.
        untracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        if untracked:
            raise SystemExit("untracked files would be left out of the replay; add them first: " + ", ".join(untracked))
        snapshot = subprocess.run(["git", "-C", str(ROOT), "stash", "create"], capture_output=True, text=True, check=True).stdout.strip()
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        label = f"working tree on {head}" + (f" (uncommitted changes as {snapshot[:12]})" if snapshot else "")
        ref = snapshot or head
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{ref}^{{commit}}"], capture_output=True, text=True, check=True).stdout.strip()
    settings = ["-c", "core.autocrlf=false", "-c", "core.eol=lf"] if eol == "lf" else []
    proc = subprocess.Popen(["git", "-C", str(ROOT), *settings, "archive", "--format=tar", commit], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
        archive.extractall(dest, filter="data")
    if proc.wait() != 0:
        raise SystemExit(f"git archive {ref} failed")
    return label or commit


def stages_of(tree: Path) -> dict[str, str]:
    """The STAGES mapping from a revision's run.py, read without importing it."""
    module = ast.parse((tree / "run.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "STAGES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("run.py has no STAGES mapping")


def run_pipeline(tree: Path, mode: str, store: Path, clock: str, log_dir: Path) -> list[dict]:
    env = dict(os.environ)
    env.update({
        "GOLDEN_MODE": mode,
        "GOLDEN_STORE": str(store),
        "GOLDEN_CLOCK": clock,
        "PYTHONPATH": os.pathsep.join(filter(None, [str(SITE), env.get("PYTHONPATH", "")])),
        "PYTHONHASHSEED": "0",
        "PYTHONUTF8": "1",
    })
    log_dir.mkdir(parents=True, exist_ok=True)
    steps = [(key, shlex.split(step)) for key, step in sorted(stages_of(tree).items())] + [("verify", ["-m", "verify.run"])]
    results = []
    for key, args in steps:
        started = time.monotonic()
        with (log_dir / f"{key}.log").open("w", encoding="utf-8") as log:
            code = subprocess.run([sys.executable, *args], cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        results.append({"step": key, "exit": code, "seconds": round(time.monotonic() - started)})
        print(f"  {key:>6}  exit {code}  {results[-1]['seconds']}s", flush=True)
        if code != 0:
            print(f"  step {key} failed; its log is {log_dir / f'{key}.log'}", flush=True)
            break
    return results


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_record(args) -> int:
    work = GOLDEN_ROOT / args.name
    store, tree = work / "store", work / "record-tree"
    if store.exists():
        raise SystemExit(f"{store} already exists; a recording is never overwritten. Choose another --name.")
    exported = export(args.ref, tree)
    print(f"recording {args.ref} ({exported}) in {tree}", flush=True)
    start = output_manifest(tree)

    files = {}
    for folder in SEEDED_RAW:
        src = ROOT / "data" / "raw" / folder
        if not src.exists():
            continue
        for path in sorted(p for p in src.rglob("*") if p.is_file()):
            rel = path.relative_to(ROOT / "data" / "raw").as_posix()
            sha = sha256_file(path)
            blob = store / "files" / sha
            if not blob.exists():
                blob.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, blob)
            target = tree / "data" / "raw" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            files[rel] = sha

    steps = run_pipeline(tree, "record", store, args.clock, work / "record-logs")
    outputs = output_manifest(tree)
    http = []
    for line in (store / "http.jsonl").read_text(encoding="utf-8").splitlines() if (store / "http.jsonl").exists() else []:
        http.append(json.loads(line))

    out = MANIFESTS / args.name
    write_json(out / "inputs.json", {
        "ref": args.ref, "exported": exported, "clock": args.clock,
        "raw_files": files, "http": http,
    })
    write_json(out / "start.json", start)
    write_json(out / "outputs.json", outputs)
    write_json(out / "run.json", {"mode": "record", "steps": steps})
    diff = compare_manifests(start, outputs)
    write_json(out / "committed-vs-recorded.json", diff)
    failed = any(step["exit"] != 0 for step in steps)
    print(f"recorded {len(http)} HTTP exchanges and {len(files)} raw files; {len(outputs)} output files")
    print(f"the run changed {len(diff['changed'])} committed files, added {len(diff['extra'])}, removed {len(diff['missing'])}")
    return 1 if failed else 0


def cmd_replay(args) -> int:
    work = GOLDEN_ROOT / args.name
    store, recorded = work / "store", MANIFESTS / args.name
    inputs = json.loads((recorded / "inputs.json").read_text(encoding="utf-8"))
    tree = work / "replay-tree"
    exported = export(args.ref, tree)
    print(f"replaying {args.name} on {exported} in {tree}", flush=True)

    start = output_manifest(tree)
    start_diff = compare_manifests(json.loads((recorded / "start.json").read_text(encoding="utf-8")), start)
    if not identical(start_diff):
        print("refused: this revision starts from different committed outputs than the recording did")
        print(json.dumps(start_diff, indent=2))
        return 2

    for rel, sha in inputs["raw_files"].items():
        target = tree / "data" / "raw" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(store / "files" / sha, target)

    steps = run_pipeline(tree, "replay", store, inputs["clock"], work / "replay-logs")
    expected = json.loads((recorded / "outputs.json").read_text(encoding="utf-8"))
    diff = compare_manifests(expected, output_manifest(tree))
    report = {"ref": args.ref, "exported": exported, "steps": steps, "diff": diff, "identical": identical(diff)}
    write_json(work / "replay-report.json", report)
    failed = any(step["exit"] != 0 for step in steps)
    for kind, paths in diff.items():
        for path in paths:
            print(f"  {kind}: {path}")
    print("IDENTICAL to the golden master" if identical(diff) and not failed else "NOT identical to the golden master")
    return 0 if identical(diff) and not failed else 1


def cmd_dist(args) -> int:
    deployed = args.base is not None
    name = args.ref.replace("/", "_") + ("-deployed" if deployed else "")
    tree = GOLDEN_ROOT / "dist" / name
    # --base reproduces the runner: .github/workflows/deploy.yml passes the repo
    # name as VITE_BASE, because a project site is served from /<repo>/ and that
    # prefix is compiled into the entry chunk. Without it the bytes differ from
    # the deployed ones for a reason that has nothing to do with this project.
    exported = export(args.ref, tree, eol="lf" if deployed else "native")
    web = tree / "web"
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise SystemExit("npm is not on PATH")
    env = {**os.environ, "VITE_BASE": args.base} if deployed else None
    for command in ([npm, "ci", "--no-audit", "--no-fund"], [npm, "run", "build"]):
        code = subprocess.run(command, cwd=web, env=env).returncode
        if code != 0:
            return code
    manifest = {"ref": args.ref, "exported": exported, "files": hash_tree(web, ("dist",))}
    if deployed:
        manifest["base"] = args.base
    write_json(Path(args.out), manifest)
    print(f"{len(manifest['files'])} files in web/dist, written to {args.out}")
    return 0


def cmd_live(args) -> int:
    """Compare what a deployed site serves with a manifest of a build.

    The published site is the only thing a reader ever sees, so the restructure's
    last claim is about it: the deployed bytes are the bytes this repository
    builds. Each file is streamed and hashed, never kept.
    """
    import requests  # not a module-level import: every other command runs offline

    files = json.loads(Path(args.manifest).read_text(encoding="utf-8"))["files"]
    base = args.url.rstrip("/")
    same, different, missing, fetched = 0, [], [], 0
    with requests.Session() as session:
        for path in sorted(files):
            rel = path[len("dist/"):] if path.startswith("dist/") else path
            digest, size = hashlib.sha256(), 0
            with session.get(f"{base}/{rel}", stream=True, timeout=120) as response:
                if response.status_code != 200:
                    missing.append((rel, response.status_code))
                    continue
                for chunk in response.iter_content(65536):
                    digest.update(chunk)
                    size += len(chunk)
            fetched += size
            if digest.hexdigest() == files[path]["sha256"]:
                same += 1
            else:
                different.append((rel, files[path]["bytes"], size))
    for rel, expected, got in different:
        print(f"  different: {rel} (built {expected} bytes, live {got})")
    for rel, code in missing:
        print(f"  not served: {rel} (HTTP {code})")
    print(f"{same} of {len(files)} files identical, {fetched / 1e6:.1f} MB fetched")
    print("identical" if same == len(files) else "different")
    return 0 if same == len(files) else 1


def cmd_compare(args) -> int:
    def load(path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data["files"] if "files" in data and isinstance(data["files"], dict) else data

    diff = compare_manifests(load(args.expected), load(args.actual))
    for kind, paths in diff.items():
        for path in paths:
            print(f"  {kind}: {path}")
    print("identical" if identical(diff) else "different")
    return 0 if identical(diff) else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Golden master for the restructure (docs/REBUILD.md §3).")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="run a revision once and keep its inputs and outputs")
    rec.add_argument("--ref", required=True)
    rec.add_argument("--name", required=True)
    rec.add_argument("--clock", default=DEFAULT_CLOCK)
    rec.set_defaults(func=cmd_record)

    rep = sub.add_parser("replay", help="run a revision on recorded inputs and compare with the golden master")
    rep.add_argument("--name", required=True)
    rep.add_argument("--ref", default=WORKTREE)
    rep.set_defaults(func=cmd_replay)

    dist = sub.add_parser("dist", help="build the site from a revision and hash web/dist")
    dist.add_argument("--ref", required=True)
    dist.add_argument("--out", required=True)
    dist.add_argument("--base", help="build it as the runner does: this VITE_BASE, and a Linux checkout's LF")
    dist.set_defaults(func=cmd_dist)

    live = sub.add_parser("live", help="compare a deployed site with a manifest from `dist --base`")
    live.add_argument("--manifest", required=True)
    live.add_argument("--url", required=True)
    live.set_defaults(func=cmd_live)

    cmp_ = sub.add_parser("compare", help="compare two manifests")
    cmp_.add_argument("expected")
    cmp_.add_argument("actual")
    cmp_.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
