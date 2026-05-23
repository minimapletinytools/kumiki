"""Stable JSON CLI for the librarian.

Used by the ``kigumi`` VS Code extension as the **only** scanning surface —
the JS side spawns this module and parses the result.  No scanning logic
should live outside Python.

Usage::

    python -m kumiki.librarian_cli scan-workspace <root>
    python -m kumiki.librarian_cli scan-files <root> < files.json
    python -m kumiki.librarian_cli scan-folder <folder>

Output is a single JSON object on stdout.  All progress / informational output
is routed to stderr so the stdout stream remains parseable.
"""

from __future__ import annotations

import contextlib
import json
import sys
import traceback
from typing import Any, Dict


def _emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def _run(action: str, argv: list[str]) -> Dict[str, Any]:
    from kumiki.librarian import (
        scan_library_index,
        scan_specific_files_index,
        scan_workspace_index,
    )
    from kumiki.librarian_index import (
        build_pattern_index,
        discover_search_roots,
        refresh_pattern_index,
        scan_all_roots,
    )

    if action == "scan-workspace":
        if not argv:
            raise SystemExit("scan-workspace requires <root>")
        return scan_workspace_index(argv[0])
    if action == "scan-folder":
        if not argv:
            raise SystemExit("scan-folder requires <folder>")
        return scan_library_index(argv[0])
    if action == "scan-files":
        if not argv:
            raise SystemExit("scan-files requires <root>")
        root = argv[0]
        try:
            data = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError as exc:
            raise SystemExit(f"scan-files: invalid JSON on stdin: {exc}")
        files = data.get("files") or []
        if not isinstance(files, list):
            raise SystemExit("scan-files: 'files' must be a list")
        return scan_specific_files_index([str(f) for f in files], root)
    if action == "build-index":
        if not argv:
            raise SystemExit("build-index requires <root>")
        return build_pattern_index(argv[0])
    if action == "refresh-index":
        if len(argv) < 2:
            raise SystemExit("refresh-index requires <root> <index_path>")
        return refresh_pattern_index(argv[0], argv[1])
    if action == "search-roots":
        if not argv:
            raise SystemExit("search-roots requires <workspace>")
        roots = discover_search_roots(argv[0])
        return {
            "roots": [
                {"name": r.name, "kind": r.kind, "root_path": str(r.root_path)}
                for r in roots
            ]
        }
    if action == "scan-all-roots":
        if not argv:
            raise SystemExit("scan-all-roots requires <workspace>")
        return scan_all_roots(argv[0])
    raise SystemExit(f"unknown action: {action}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        _emit({"ok": False, "error": "usage: librarian_cli <action> [args...]"})
        return 2
    action = argv[1]
    rest = argv[2:]
    try:
        # Capture any rogue stdout from imported modules so stdout stays clean.
        with contextlib.redirect_stdout(sys.stderr):
            result = _run(action, rest)
        _emit({"ok": True, "result": result})
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        _emit({
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        })
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
