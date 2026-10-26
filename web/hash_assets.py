#!/usr/bin/env python3
"""Content-hash the site's scripts at publish so a long cache is safe.

GitHub Pages serves every file with `Cache-Control: max-age=600` and no way to
raise it, so a returning visitor re-checks `support.js` and `lib/*.js` every
ten minutes. Naming each copy by its content (`lib/sports.3f9a1c2b7d.js`) and
pointing the pages at those names means a cache in front of Pages (or a later
host that honours long caching) can keep a file for a year: a changed file is a
new name, never a stale copy under the old one.

    python web/hash_assets.py dist

In `dist` (the assembled site): each `lib/*.js` and `support.js` gets a hashed
copy, leaves first (`sports.js` imports `format.js`, so it is hashed after its
reference is rewritten), and every page's `./support.js` / `./lib/<name>.js`
reference is rewritten to the hashed copy. The plain names stay, for anything
outside the site that links them. Standard library only.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REF = re.compile(r"""(["'])(\./)?(support|lib/[A-Za-z0-9_-]+|[A-Za-z0-9_-]+)\.js\1""")


def _rewrite(text: str, names: dict[str, str], here: str) -> str:
    """Point quoted ./x.js references at their hashed names. `here` is the
    folder the file sits in ("" or "lib"), so lib's own "./format.js" resolves
    to lib/format.js."""
    def swap(m: re.Match) -> str:
        quote, dot, stem = m.group(1), m.group(2) or "", m.group(3)
        key = stem if "/" in stem or not here else f"{here}/{stem}"
        if key not in names:
            return m.group(0)
        new = names[key] if not here or "/" in stem else names[key].split("/", 1)[1]
        return f"{quote}{dot}{new}.js{quote}"
    return REF.sub(swap, text)


def hash_assets(dist: Path) -> dict[str, str]:
    lib = sorted((dist / "lib").glob("*.js")) if (dist / "lib").is_dir() else []
    lib = [p for p in lib if not re.search(r"\.[0-9a-f]{10}\.js$", p.name)]
    pending = {f"lib/{p.stem}": p for p in lib}
    if (dist / "support.js").is_file():
        pending["support"] = dist / "support.js"
    names: dict[str, str] = {}
    while pending:
        progressed = False
        for key, path in sorted(pending.items()):
            here = "lib" if key.startswith("lib/") else ""
            text = path.read_text(encoding="utf-8")
            deps = {(m.group(3) if "/" in m.group(3) or not here else f"{here}/{m.group(3)}")
                    for m in REF.finditer(text)} & set(pending) - {key}
            if deps:
                continue
            body = _rewrite(text, names, here).encode("utf-8")
            digest = hashlib.sha256(body).hexdigest()[:10]
            hashed = f"{key}.{digest}"
            (dist / f"{hashed}.js").write_bytes(body)
            names[key] = hashed
            del pending[key]
            progressed = True
        if not progressed:
            raise SystemExit(f"circular script imports: {sorted(pending)}")
    for page in sorted(dist.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        new = _rewrite(text, names, "")
        if new != text:
            page.write_text(new, encoding="utf-8")
    return names


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: hash_assets.py DIST", file=sys.stderr)
        return 2
    names = hash_assets(Path(args[0]))
    for key, hashed in sorted(names.items()):
        print(f"{key}.js -> {hashed}.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
