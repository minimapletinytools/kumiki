"""Scratch: what is pickable on a joint example's timbers, and how each feature is keyed.

Names a joint pattern and prints, per cut timber, every declared feature that is actually
on the finished surface -- the node label it lives on, its name, its feature key (which is
what a FeatureOverride addresses), its group and its purpose. Faces that never appear are
the ones a cut removed.

Run:  .venv/bin/python garbage/visible_features_probe.py tongue_and_fork/90
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from kumiki.csg.cutcsg import csg_children  # noqa: E402
from kumiki.csg.triangles import triangulate_cutcsg  # noqa: E402
from kumiki.patternbook import Pattern  # noqa: E402
from kumiki.rule import create_v3, scalar  # noqa: E402

PATTERNS_DIR = REPO / "patterns"
ORIGIN = create_v3(scalar(0), scalar(0), scalar(0))


def modules():
    for path in sorted(PATTERNS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        yield path


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


def pickable(rendered):
    """{(owner id, feature name): (label, feature)} for features seen on the surface."""
    found = {}
    for triangle in triangulate_cutcsg(rendered).mesh.triangles:
        points = [[(triangle[a][i] + triangle[b][i]) / 2 for i in range(3)]
                  for a, b in ((0, 1), (1, 2), (2, 0))]
        points.append([sum(v[i] for v in triangle) / 3 for i in range(3)])
        for point in points:
            for hit in rendered.find_all_features(create_v3(*point)):
                found[(id(hit.owner), hit.feature.name)] = hit.feature
    return found


def main() -> int:
    wanted = [term for term in sys.argv[1:] if not term.startswith("--")]
    check_only = "--check" in sys.argv
    failures = []
    for index, path in enumerate(modules()):
        name = f"visible_{index}_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        for pattern in getattr(module, "patterns", None) or []:
            if not isinstance(pattern, Pattern) or pattern.pattern_type != "frame":
                continue
            if wanted and not any(term in pattern.path for term in wanted):
                continue
            frame = pattern.raise_at(ORIGIN)
            if check_only:
                for cut in frame.cut_timbers:
                    try:
                        pickable(cut.render_timber_with_cuts_csg_local())
                    except Exception as exc:  # noqa: BLE001 - the point of the check
                        failures.append((pattern.path, cut.timber.ticket.path,
                                         f"{type(exc).__name__}: {exc}"))
                continue
            print(f"\n=== {pattern.path}")
            for cut in frame.cut_timbers:
                rendered = cut.render_timber_with_cuts_csg_local()
                seen = pickable(rendered)
                owners = {}
                for node in walk(rendered):
                    owners[id(node)] = str(getattr(node, "label", ""))
                print(f"  -- {cut.timber.ticket.path}")
                rows = []
                for (owner_id, feature_name), feature in seen.items():
                    key = feature.feature_key()
                    rows.append((feature_name, key, feature.group.name,
                                 feature.properties.purpose.name, owners.get(owner_id, "?")))
                for feature_name, key, group, purpose, label in sorted(rows):
                    print(f"     {feature_name:26} key={str(key):26} group={group:15}"
                          f" purpose={purpose:14} on {label}")
    if check_only:
        if failures:
            print(f"{len(failures)} surface scans failed:")
            for pattern_path, timber, error in failures:
                print(f"  {pattern_path} [{timber}]\n      {error}")
        else:
            print("all surfaces scanned clean")
        return len(failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
