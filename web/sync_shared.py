#!/usr/bin/env python3
"""The pages every lab shares, from cooperross399/betting-lab-shared at a pinned tag.

Board, Results, Archive and Graphic (`*.dc.html`), `lib/live.js`, `lib/format.js`,
`lib/sports.js` and this lab's team logos are one set of files across the NHL, EPL
and CBB labs (and the hub, for `lib/sports.js` and `lib/format.js`). They live in
the shared repository; each lab pins one tag of it in `web/shared.lock.json`, with
the SHA-256 of every file it takes. A copy is committed here too, so the suite and
a local build need no network.

    python web/sync_shared.py --from DIR       # copy a checkout of the tag into web/
    python web/sync_shared.py --check          # the committed copies match the lock
    python web/sync_shared.py --lock DIR --tag vN   # re-pin web/shared.lock.json to DIR

The publish run clones the pinned tag and runs `--from`: a file whose bytes differ
from the lock fails the run, so the tag cannot move under a lab silently, and a
bump is a pull request that changes the lock. Standard library only; nothing here
fetches odds or spends a credit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent
LOCK = WEB / "shared.lock.json"
REPO = "cooperross399/betting-lab-shared"
PAGES = ("Board.dc.html", "Results.dc.html", "Archive.dc.html", "Graphic.dc.html",
         "lib/live.js", "lib/format.js", "lib/sports.js")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(shared: Path, name: str, sport: str) -> Path:
    """Where a lab's file sits in the shared repository: logos by sport."""
    if name.startswith("logos/"):
        return shared / "web" / "logos" / sport / name[len("logos/"):]
    return shared / "web" / name


def load_lock(lock: Path = LOCK) -> dict:
    return json.loads(lock.read_text(encoding="utf-8"))


def check(web: Path = WEB, lock: Path = LOCK) -> list[str]:
    """Every locked file present in `web` with the locked bytes."""
    bad = []
    for name, want in load_lock(lock)["files"].items():
        path = web / name
        if not path.is_file():
            bad.append(f"{name}: missing")
        elif digest(path) != want:
            bad.append(f"{name}: differs from the lock")
    return bad


def sync(shared: Path, web: Path = WEB, lock: Path = LOCK) -> list[str]:
    """Copy every locked file from a checkout of the tag into `web`, refusing
    any whose bytes are not the lock's. Nothing is copied unless all match."""
    pinned = load_lock(lock)
    bad, plan = [], []
    for name, want in pinned["files"].items():
        src = source(shared, name, pinned["sport"])
        if not src.is_file():
            bad.append(f"{name}: not in {pinned['tag']}")
        elif digest(src) != want:
            bad.append(f"{name}: {pinned['tag']} differs from the lock")
        else:
            plan.append((src, web / name))
    if bad:
        return bad
    for src, dst in plan:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return []


def write_lock(shared: Path, tag: str, sport: str, lock: Path = LOCK) -> dict:
    """Pin `tag`: the shared pages and libraries, and every logo of `sport`."""
    names = list(PAGES) + sorted(f"logos/{p.name}" for p in (shared / "web" / "logos" / sport).iterdir()
                                 if p.is_file())
    doc = {"repo": REPO, "tag": tag, "sport": sport,
           "files": {name: digest(source(shared, name, sport)) for name in names}}
    lock.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--from", dest="shared", type=Path, help="a checkout of the pinned tag")
    group.add_argument("--check", action="store_true", help="the committed copies match the lock")
    group.add_argument("--lock", type=Path, help="re-pin the lock to this checkout")
    ap.add_argument("--tag", help="with --lock: the tag the checkout is at")
    ap.add_argument("--sport", help="with --lock: this lab's sport (default: the lock's)")
    args = ap.parse_args(argv)
    if args.lock:
        if not args.tag:
            ap.error("--lock needs --tag")
        sport = args.sport or load_lock()["sport"]
        doc = write_lock(args.lock, args.tag, sport)
        print(f"pinned {REPO}@{args.tag}: {len(doc['files'])} files")
        return 0
    bad = check() if args.check else sync(args.shared)
    pinned = load_lock()
    for line in bad:
        print(f"::error::{line}")
    if bad:
        return 1
    print(f"{len(pinned['files'])} shared files match {REPO}@{pinned['tag']}"
          + ("" if args.check else ", copied into web/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
