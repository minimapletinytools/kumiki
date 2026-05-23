"""Generate ``kumiki/_pattern_index.json`` from the repo's ``patterns/`` tree.

Run directly: ``python tools/build_pattern_index.py``.

Also invoked by the hatch build hook at wheel-build time so the JSON is
included in the published wheel.

Because ``patterns/`` is force-included into the wheel at ``kumiki/patterns``,
we re-key relative paths in the index with a ``patterns/`` prefix so that
runtime consumers can resolve them against the installed kumiki package
directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_repo_on_path() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def build(repo_root: Path | None = None) -> Path:
    repo_root = repo_root or _ensure_repo_on_path()
    from kumiki.librarian_index import (
        PACKAGE_INDEX_FILENAME,
        PATTERN_INDEX_SCHEMA_VERSION,
        build_pattern_index,
    )

    patterns_dir = repo_root / "patterns"
    out_path = repo_root / "kumiki" / PACKAGE_INDEX_FILENAME

    if not patterns_dir.exists():
        # Empty stub so the wheel still ships the file.
        index = {
            "schema_version": PATTERN_INDEX_SCHEMA_VERSION,
            "generated_at": None,
            "root_folder": "patterns",
            "entries": {},
        }
    else:
        raw = build_pattern_index(str(patterns_dir))
        # Re-key entries so they're relative to the installed kumiki package
        # (which contains a ``patterns/`` subfolder via force-include).
        rekeyed = {
            f"patterns/{rel}": entry for rel, entry in raw.get("entries", {}).items()
        }
        index = {
            "schema_version": PATTERN_INDEX_SCHEMA_VERSION,
            "generated_at": raw.get("generated_at"),
            "root_folder": "patterns",
            "entries": rekeyed,
        }

    out_path.write_text(json.dumps(index, indent=2, sort_keys=True))
    return out_path


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}", file=sys.stderr)
