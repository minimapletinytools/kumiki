"""Scratch: what each joint declares -- the CSG nodes it labels, and the features it names.

Raises every frame pattern in patterns/ (the joint examples), walks each cut timber's
tree, and reports per joint:

- the labels on the nodes it creates (tongue, shoulder, tenon_waste, ...) -- how a joint
  says what its geometry IS, whether or not it names features on it;
- the features it names, with their group and purpose -- which is what a pick, a
  measurement or a derived edge can refer to.

Run:  .venv/bin/python garbage/joint_feature_inventory.py
      .venv/bin/python garbage/joint_feature_inventory.py mortise   # filter by path
"""

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from kumiki.frame_decorators import module_patterns
from kumiki.csg.cutcsg import csg_children  # noqa: E402
from kumiki.patternbook import Pattern  # noqa: E402
from kumiki.rule import create_v3, scalar  # noqa: E402

PATTERNS_DIR = REPO / "patterns"
ORIGIN = create_v3(scalar(0), scalar(0), scalar(0))

#: A timber's own body, named by timber.py rather than by any joint.
BODY_PREFIXES = ("ptw.", "rough.", "side.", "cap.", "arris.", "corner.")

#: Everything not a timber body: unnamed primitives the joints build.
LABEL_NOISE = re.compile(r"timber \(|end_cut|_waste|_cut$|^NoLabel$")

TENON_WORDS = ("tenon", "tongue", "tusk", "dovetail", "pin", "tail", "spline", "stub")
SHOULDER_WORDS = ("shoulder", "housing", "seat")


def modules():
    for path in sorted(PATTERNS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        yield path


def load(path: Path, index: int):
    name = f"inventory_{index}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def walk(node):
    seen = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        stack.extend(csg_children(current))


def describe(frame):
    """(labels, named) for every cut timber of *frame*."""
    labels, named = set(), {}
    for cut in frame.cut_timbers:
        for node in walk(cut.render_timber_with_cuts_csg_local()):
            label = str(getattr(node, "label", ""))
            match = re.search(r"'([^']+)'", label)
            if match and not LABEL_NOISE.search(match.group(1)):
                labels.add(match.group(1))
            for feature in node.get_declared_features():
                if feature.name.startswith(BODY_PREFIXES):
                    continue
                named[feature.name] = (feature.group.name, feature.properties.purpose.name)
    return labels, named


def words_in(names, vocabulary):
    return sorted({name for name in names
                   if any(word in name.lower() for word in vocabulary)})


def main() -> int:
    wanted = sys.argv[1:]
    rows = []
    for index, path in enumerate(modules()):
        try:
            module = load(path, index)
        except Exception as exc:  # noqa: BLE001
            print(f"{path.relative_to(REPO)}: IMPORT FAILED {type(exc).__name__}: {exc}")
            continue
        for pattern in module_patterns(module)[0]:
            if not isinstance(pattern, Pattern) or pattern.pattern_type != "frame":
                continue
            if wanted and not any(term in pattern.path for term in wanted):
                continue
            try:
                frame = pattern.raise_at(ORIGIN)
            except Exception as exc:  # noqa: BLE001
                print(f"{pattern.path}: RAISE FAILED {type(exc).__name__}: {exc}")
                continue
            rows.append((pattern.path, *describe(frame)))

    print("=" * 100)
    for path, labels, named in rows:
        print(f"\n{path}")
        if labels:
            print(f"    labels:  {', '.join(sorted(labels))}")
        else:
            print("    labels:  (none -- nothing but the timber body)")
        if named:
            for name, (group, purpose) in sorted(named.items()):
                mark = "  <-- shoulder plane" if purpose == "SHOULDER" else ""
                print(f"    feature: {name:32} group={group:15} purpose={purpose}{mark}")
        else:
            print("    feature: (none -- every face is an anonymous default)")

    print("\n" + "=" * 100)
    print("SUMMARY")
    with_named = [path for path, _, named in rows if named]
    with_tenon_named = [path for path, _, named in rows if words_in(named, TENON_WORDS)]
    with_shoulder_named = [path for path, _, named in rows
                           if any(purpose == "SHOULDER" for _, purpose in named.values())]
    with_tenon_label = [path for path, labels, _ in rows if words_in(labels, TENON_WORDS)]
    with_shoulder_label = [path for path, labels, _ in rows if words_in(labels, SHOULDER_WORDS)]
    print(f"{len(rows)} joint examples")
    print(f"  names features at all:            {len(with_named)}")
    print(f"  names a tenon-ish feature:        {len(with_tenon_named)}")
    print(f"  names a SHOULDER-purpose plane:   {len(with_shoulder_named)}")
    print(f"  labels a tenon-ish node:          {len(with_tenon_label)}")
    print(f"  labels a shoulder-ish node:       {len(with_shoulder_label)}")
    print("\n  labelled a shoulder but named no SHOULDER-purpose plane:")
    for path, labels, named in rows:
        if words_in(labels, SHOULDER_WORDS) and not any(p == "SHOULDER" for _, p in named.values()):
            print(f"    {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
