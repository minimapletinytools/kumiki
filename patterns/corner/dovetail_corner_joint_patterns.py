"""
Dovetail Corner Joint Patterns
"""

from kumiki import *
from kumiki.example_shavings import create_canonical_example_right_angle_corner_joint_timbers
from kumiki.patternbook import Pattern


def _make_dovetail_corner_joint_example(position: V3, depth=None) -> list[CutTimber]:
    """
    Create a dovetail corner joint on the canonical right-angle corner timbers.

    The canonical timbers are 4x5, laid out across the 4" axis and reaching 5" into
    timber2, so a 1:8 flare opens each dovetail by 0.625 a side over a through cut.
    Two dovetails centered 1" and 3" in from the front face fit that with room to spare.
    """
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position=position)
    joint = cut_dovetail_corner_joint(
        arrangement,
        distances=[inches(1), inches(2)],
        dovetails=[
            SingleDovetailSizeParameter(angle=atan(scalar(1, 8)), small_width=inches(scalar(1, 2)), depth=depth)
            for _ in range(2)
        ],
    )
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_through_dovetail_corner_joint_example(position: V3) -> list[CutTimber]:
    """Through dovetails: they run the full thickness of timber2 and show on its far face."""
    return _make_dovetail_corner_joint_example(position)


def make_half_blind_dovetail_corner_joint_example(position: V3) -> list[CutTimber]:
    """Half blind dovetails: they stop short, so timber2's far face stays unbroken."""
    return _make_dovetail_corner_joint_example(position, depth=inches(scalar(5, 2)))


patterns = [
    Pattern(path="corner_joints/dovetail_corner_joint/cut_dovetail_corner_joint", lambda_=lambda center: Frame(cut_timbers=make_through_dovetail_corner_joint_example(center), name="Through Dovetail Corner Joint"), pattern_type='frame'),
    Pattern(path="corner_joints/dovetail_corner_joint/cut_dovetail_corner_joint_half_blind", lambda_=lambda center: Frame(cut_timbers=make_half_blind_dovetail_corner_joint_example(center), name="Half Blind Dovetail Corner Joint"), pattern_type='frame'),
]
