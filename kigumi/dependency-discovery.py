#!/usr/bin/env python3
"""Discover kumiki/dependency pattern and example files from site-packages.

Outputs JSON on stdout with keys:
- kumikiPatterns
- kumikiPatternbooks
- kumikiExamples
- dependencyPatterns
- dependencyPatternbooks
- dependencyExamples
"""

from __future__ import annotations

import json
import os
import re
import site
import sys
import sysconfig
from typing import Any, Dict, List, Tuple

SKIP_DIRS = {"__pycache__", "node_modules", "dist", "build", ".git", ".hg", ".svn"}


def _might_contain_patternbook(src: str) -> bool:
    return bool(re.search(r"^\s*patterns\s*=", src, flags=re.M))


def _might_contain_example(src: str) -> bool:
    if re.search(r"^\s*example\s*=", src, flags=re.M):
        return True
    if re.search(r"^\s*def\s+build_frame\s*\(", src, flags=re.M):
        return True
    return False


def index_paths(folder: str) -> Tuple[List[str], List[str]]:
    if not folder or not os.path.isdir(folder):
        return [], []

    pattern_files: List[str] = []
    frame_example_files: List[str] = []

    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        for file_name in files:
            if not file_name.endswith(".py") or file_name == "__init__.py":
                continue

            file_path = os.path.join(root, file_name)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                    src = fh.read()
            except Exception:
                continue

            if _might_contain_patternbook(src):
                pattern_files.append(file_path)
            if _might_contain_example(src):
                frame_example_files.append(file_path)

    return pattern_files, frame_example_files


def _extract_pattern_names_from_source(file_path: str) -> List[str]:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except Exception:
        return []

    names: List[str] = []

    # PatternMetadata("name", [...], "frame")
    for m in re.finditer(r'PatternMetadata\(\s*[\'\"]([^\'\"]+)[\'\"]', src):
        names.append(m.group(1))

    # make_pattern_from_joint("name", ...)
    for m in re.finditer(r'make_pattern_from_joint\(\s*[\'\"]([^\'\"]+)[\'\"]', src):
        names.append(m.group(1))

    # Optional helper forms: add_pattern("name", ...)
    for m in re.finditer(r'(?:\.|\b)add_pattern\(\s*[\'\"]([^\'\"]+)[\'\"]', src):
        names.append(m.group(1))

    deduped: List[str] = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)

    return deduped


def _fallback_patternbook_records(file_paths: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for fp in sorted(set(file_paths)):
        base = os.path.splitext(os.path.basename(fp))[0]
        names = _extract_pattern_names_from_source(fp)
        if not names:
            names = [base]
        rows.append(
            {
                "sourceFile": fp,
                "patternbookName": base,
                "patternNames": names,
                "groupNames": [],
            }
        )

    return rows


def _scan_patternbook_records(file_paths: List[str]) -> List[Dict[str, Any]]:
    if not file_paths:
        return []

    files = sorted(set(file_paths))

    try:
        from kumiki.librarian import scan_specific_files_index
    except Exception:
        return _fallback_patternbook_records(files)

    try:
        root = os.path.commonpath(files)
    except Exception:
        root = os.path.dirname(files[0])

    if not root:
        root = os.path.dirname(files[0])
    if not os.path.isdir(root):
        root = os.path.dirname(root)

    try:
        index = scan_specific_files_index(files, root)
    except Exception:
        return _fallback_patternbook_records(files)

    rows: List[Dict[str, Any]] = []
    seen = set()

    for rec in index.get("patternbooks", []):
        fp = rec.get("file_path")
        if not fp or fp in seen:
            continue

        seen.add(fp)
        base = os.path.splitext(os.path.basename(fp))[0]
        pattern_names = sorted(set(rec.get("pattern_names") or []))
        if not pattern_names:
            pattern_names = _extract_pattern_names_from_source(fp)

        rows.append(
            {
                "sourceFile": fp,
                "patternbookName": base,
                "patternNames": pattern_names if pattern_names else [base],
                "groupNames": sorted(set(rec.get("group_names") or [])),
            }
        )

    # Keep files that static scan flagged but librarian could not load.
    for fp in files:
        if fp in seen:
            continue

        base = os.path.splitext(os.path.basename(fp))[0]
        pattern_names = _extract_pattern_names_from_source(fp)
        rows.append(
            {
                "sourceFile": fp,
                "patternbookName": base,
                "patternNames": pattern_names if pattern_names else [base],
                "groupNames": [],
            }
        )

    rows.sort(key=lambda row: row["sourceFile"])
    return rows


def _collect_site_roots() -> List[str]:
    site_roots = set()

    for key in ("purelib", "platlib"):
        p = sysconfig.get_paths().get(key)
        if p:
            site_roots.add(p)

    try:
        for candidate in site.getsitepackages():
            site_roots.add(candidate)
    except Exception:
        pass

    try:
        usersite = site.getusersitepackages()
        if usersite:
            site_roots.add(usersite)
    except Exception:
        pass

    return sorted(site_roots)


def _prioritize_site_packages(site_roots: List[str]) -> None:
    # Prevent cwd/workspace from shadowing installed kumiki package.
    cwd = os.getcwd()
    cleaned = [p for p in sys.path if p not in ("", cwd)]

    for sp in sorted(site_roots, key=len, reverse=True):
        if sp and os.path.isdir(sp) and sp not in cleaned:
            cleaned.insert(0, sp)

    sys.path[:] = cleaned


def main() -> None:
    site_roots = _collect_site_roots()
    _prioritize_site_packages(site_roots)

    kumiki_patterns = set()
    kumiki_examples = set()
    dependency_patterns = set()
    dependency_examples = set()

    for site_root in site_roots:
        if not os.path.isdir(site_root):
            continue

        try:
            entries = list(os.scandir(site_root))
        except Exception:
            continue

        for entry in entries:
            if not entry.is_dir():
                continue

            name = entry.name
            if name.endswith(".dist-info") or name.endswith(".egg-info"):
                continue

            if name == "kumiki":
                kp, ke = index_paths(os.path.join(entry.path, "patterns"))
                kumiki_patterns.update(kp)
                kumiki_examples.update(ke)

                kp, ke = index_paths(os.path.join(entry.path, "examples"))
                kumiki_patterns.update(kp)
                kumiki_examples.update(ke)

                kp, ke = index_paths(os.path.join(entry.path, "patterns", "examples"))
                kumiki_patterns.update(kp)
                kumiki_examples.update(ke)

                kp, ke = index_paths(os.path.join(entry.path, "patternbooks", "examples"))
                kumiki_patterns.update(kp)
                kumiki_examples.update(ke)
                continue

            if name.startswith("_"):
                continue

            kp, ke = index_paths(os.path.join(entry.path, "patterns"))
            dependency_patterns.update(kp)
            dependency_examples.update(ke)

            kp, ke = index_paths(os.path.join(entry.path, "examples"))
            dependency_patterns.update(kp)
            dependency_examples.update(ke)

    payload = {
        "kumikiPatterns": sorted(kumiki_patterns),
        "kumikiPatternbooks": _scan_patternbook_records(list(kumiki_patterns)),
        "kumikiExamples": sorted(kumiki_examples),
        "dependencyPatterns": sorted(dependency_patterns),
        "dependencyPatternbooks": _scan_patternbook_records(list(dependency_patterns)),
        "dependencyExamples": sorted(dependency_examples),
    }

    print(json.dumps(payload))


if __name__ == "__main__":
    main()
