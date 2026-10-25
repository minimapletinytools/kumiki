"""Build a frame file the way Kigumi's runner finds its frame, and say how it came out, as JSON:
whether it built (else the error and traceback), its warnings, each timber's box as cut, and the groups of
timbers that touch (more than one: some joint cuts into air). For the agent evals (run-evals.js)."""

import contextlib
import importlib.util
import io
import json
import os
import sys
import traceback
import warnings

KIGUMI = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIGUMI)

# Two timbers this close or closer touch, in metres.
TOUCHING = 0.001


def cut_box(runner, cut_timber, key):
    """The cut timber's world bounding box, from its mesh as a view draws it: a tenon reaches past
    the timber's end, so the uncut timber's box can fall short of the one it enters."""
    mesh = runner._cut_timber_to_triangle_mesh_payload(cut_timber, cut_timber.render_timber_with_cuts_csg_local(), key)
    vertices = mesh["vertices"]
    return ([min(vertices[i::3]) for i in range(3)], [max(vertices[i::3]) for i in range(3)])


def groups_of(boxes):
    """Indices of boxes that touch, transitively, as lists."""
    touch = lambda a, b: all(a[0][i] <= b[1][i] + TOUCHING and b[0][i] <= a[1][i] + TOUCHING for i in range(3))
    unseen, groups = set(range(len(boxes))), []
    while unseen:
        group, frontier = set(), [unseen.pop()]
        while frontier:
            i = frontier.pop()
            group.add(i)
            for j in [j for j in unseen if touch(boxes[i], boxes[j])]:
                unseen.discard(j)
                frontier.append(j)
        groups.append(sorted(group))
    return groups


def build(path):
    printed = io.StringIO()
    with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
        warnings.simplefilter("always")
        try:
            import runner
            spec = importlib.util.spec_from_file_location("eval_frame", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            frame = runner.resolve_frame_from_module(module)[0]
        except Exception as error:
            return {"ok": False, "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()[-3000:]}
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        boxes = [cut_box(runner, cut, f"{cut.timber.ticket.path}#{i}") for i, cut in enumerate(frame.cut_timbers)]
    names = [cut.timber.ticket.path for cut in frame.cut_timbers]
    return {
        "ok": True,
        "warnings": [str(w.message) for w in caught if not issubclass(w.category, (DeprecationWarning, SyntaxWarning))],
        "timbers": [{"name": n, "min": [round(v, 4) for v in b[0]], "max": [round(v, 4) for v in b[1]]} for n, b in zip(names, boxes)],
        "groups": [[names[i] for i in group] for group in groups_of(boxes)],
    }


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1])))
