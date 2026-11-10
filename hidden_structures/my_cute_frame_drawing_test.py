# Last checked on kumiki 0.9.0
"""my_cute_frame in rough stock, with generated drawings (kumiki.drawings.auto_drawings).

The Left Side timber is fixed: the plan is dimensioned from its reference faces and bottom end. Each
distinct piece gets a shop drawing; matching pieces (match_timbers) share one, named with how many to
make. The drawing tests load this frame.

Run directly to print what each drawing picked; load in Kigumi to see the drawings.
"""

import importlib.util as importlib_util
from pathlib import Path as FilePath

from kumiki import *
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.csg.symmetry import match_timbers
from kumiki.drawings.auto_drawings import solve_piece, solve_plan, with_auto_drawings


ROUGH_ALLOWANCE = inches(1)


def _rough(timber: Timber) -> Timber:
    """*timber*, its rough stock ROUGH_ALLOWANCE larger on each long face that is not a reference face."""
    referenced = {face for feature in timber.ticket.reference_features for face in feature.long_faces_it_rests_on()}
    (right, left), (front, back) = ((half[0], half[1]) for half in timber.get_rough_half_sizes())
    grow = lambda face, half: half if face in referenced else half + ROUGH_ALLOWANCE
    return Timber.from_perfect_timber_within(timber, rough_half_sizes=(
        create_v2(grow(TimberLongFace.RIGHT, right), grow(TimberLongFace.LEFT, left)),
        create_v2(grow(TimberLongFace.FRONT, front), grow(TimberLongFace.BACK, back))))


def _load_cute_frame():
    """my_cute_frame's frame, every timber of it rough on its two non-reference faces.

    my_cute_frame.py is the starter project's frame and stays as it is, so the rough stock goes in
    here, where its timbers are made.
    """
    path = FilePath(__file__).resolve().parent.parent / "patterns" / "structures" / "my_cute_frame.py"
    spec = importlib_util.spec_from_file_location("my_cute_frame_for_drawing_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.create_axis_aligned_timber = lambda *args, **kwargs: _rough(create_axis_aligned_timber(*args, **kwargs))
    return module.my_cute_frame


FIXED_TIMBER = "Left Side"


def build_frame_with_drawing() -> Frame:
    """The rough cute frame with its plan and a shop drawing per distinct piece, made now."""
    return with_auto_drawings(_load_cute_frame()(), FIXED_TIMBER).finish()


example = build_frame_with_drawing


def _name(handle: FeatureHandle) -> str:
    return f"{handle.timber.ticket.path}:{handle.feature.name}"


def _report(title: str, result) -> None:
    print(f"{title}: {len(result.picks)} dimensions, {result.left_before} unknowns before")
    for pick in result.picks:
        measure = pick.candidate.measure
        print(f"  [{pick.candidate.view:5}] {_name(measure.anchor_a)} -> {_name(measure.anchor_b)}"
              f"  {pick.candidate.length * 1000:.0f}mm")
    print(f"  unsolved: {[_name(handle) for handle in result.unsolved] or 'none'}")


if __name__ == "__main__":
    import time
    started = time.time()
    frame = _load_cute_frame()()
    _report("plan", solve_plan(frame.cut_timbers, FIXED_TIMBER))
    for group in match_timbers(frame.cut_timbers):
        _report(group.representative.timber.ticket.path, solve_piece(group.representative))
    print(f"took {time.time() - started:.1f}s")
