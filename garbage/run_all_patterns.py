"""Scratch: raise every pattern in the repo's patterns/ tree and report what breaks.

Walks ``patterns/**/*.py`` (skipping ``__pycache__`` and ``__init__.py``), imports each
file by path, and:

- if the module has a ``patterns`` list, raises every Pattern in it (``raise_at(origin)``),
- if the module has a zero-argument ``example`` callable (the structures), calls it.

Anything that raises is reported with the file, the pattern path and the exception. Exit
code is the number of failures, so it can be used as a crude gate.

Run:  .venv/bin/python garbage/run_all_patterns.py            # every file
      .venv/bin/python garbage/run_all_patterns.py relief     # only paths containing "relief"
"""

import importlib.util
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from kumiki.patternbook import Pattern  # noqa: E402
from kumiki.rule import create_v3, scalar  # noqa: E402

PATTERNS_DIR = REPO / "patterns"
ORIGIN = create_v3(scalar(0), scalar(0), scalar(0))


def modules():
    for path in sorted(PATTERNS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        yield path


def load(path: Path, index: int):
    name = f"pattern_probe_{index}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    wanted = sys.argv[1:]
    failures = []
    checked = 0
    skipped = []

    for index, path in enumerate(modules()):
        relative = str(path.relative_to(REPO))
        if wanted and not any(term in relative for term in wanted):
            continue
        try:
            module = load(path, index)
        except Exception as exc:  # noqa: BLE001 - a broken import is the finding
            failures.append((relative, "<import>", f"{type(exc).__name__}: {exc}"))
            continue

        patterns = getattr(module, "patterns", None)
        if isinstance(patterns, list) and patterns:
            for pattern in patterns:
                if not isinstance(pattern, Pattern):
                    continue
                checked += 1
                try:
                    pattern.raise_at(ORIGIN)
                except Exception as exc:  # noqa: BLE001 - the point of the probe
                    failures.append((relative, pattern.path, f"{type(exc).__name__}: {exc}"))
            continue

        example = getattr(module, "example", None)
        if callable(example):
            checked += 1
            try:
                example()
            except Exception as exc:  # noqa: BLE001
                failures.append((relative, "<example>", f"{type(exc).__name__}: {exc}"))
            continue

        skipped.append(relative)

    print(f"checked {checked} patterns in {len(list(modules()))} files")
    if skipped:
        print(f"no patterns or example (skipped): {len(skipped)}")
    if not failures:
        print("all good")
        return 0

    print(f"\n{len(failures)} FAILURES:\n")
    for relative, where, error in failures:
        print(f"  {relative}\n    {where}\n    {error}")
    return len(failures)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        traceback.print_exc()
        raise SystemExit(130)
