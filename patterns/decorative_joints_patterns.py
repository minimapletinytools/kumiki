"""
Decorative Joints Patterns
"""

from sympy import pi

from kumiki import *
from kumiki.pathcsg import LineSegment, ArcSegment
from kumiki.patternbook import Pattern, make_pattern_from_joint


def example_roundover_decoration() -> Joint:
    """A single timber with all 12 edges rounded over."""
    timber = Timber(
        length=feet(4),
        size=Matrix([inches(4), inches(6)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
    )
    return cut_practice_roundover_decoration(
        timber=timber,
        edges=list(TimberEdge),
        radius=inches(1, 2),
    )


def example_roundover_imperfect() -> Joint:
    """A single edge rounded over on an imperfect timber.

    The timber's actual (rough-stock) dimensions are 1 inch more than
    its perfect timber within on the RIGHT and FRONT sides -- exactly the two
    faces adjacent to the rounded-over RIGHT_FRONT edge -- demonstrating that
    the round-over cut reaches out to the actual, oversized corner rather
    than stopping at the idealized perfect corner.
    """
    timber = Timber(
        length=feet(3),
        size=Matrix([inches(4), inches(4)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
        rough_half_sizes=(
            create_v2(inches(2 + 1), inches(2)),  # width: right_half (+1"), left_half (perfect)
            create_v2(inches(2 + 1), inches(2)),  # height: front_half (+1"), back_half (perfect)
        ),
    )
    return cut_practice_roundover_decoration(
        timber=timber,
        edges=[TimberEdge.RIGHT_FRONT],
        radius=inches(1, 2),
    )


def example_rafter_tail_scallop_decoration() -> Joint:
    """A rafter tail with a scalloped decorative cut on its underside near the tail end."""
    timber = Timber(
        length=feet(4),
        size=Matrix([inches(4), inches(6)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
    )
    return cut_practice_rafter_tail_scallop_corner_end_decoration(
        timber=timber,
        short_edge=TimberShortEdge.TOP_BACK,
        scallop_height=inches(2),
        scallop_length=inches(4),
    )


def example_path_extrusion_corner_end_decoration() -> Joint:
    """
    A carved corner scoop at the bottom-right end of a timber, drawn as a
    path with both a convex bulge, a concave tuck, and a straight run --
    demonstrating that cut_practice_path_extrusion_corner_end_decoration's
    cut_path can freely mix curve directions and straight lines, not just a
    single arc like cut_practice_rafter_tail_scallop_corner_end_decoration.

    Path coordinates are local to cut_corner (x: distance from the end face
    into the timber, y: distance from the cut_side face into the timber):
      - a convex quarter-circle bulge from (0", 3") to (1", 2")
      - a concave quarter-circle tuck from (1", 2") to (2", 3")
      - a straight run from (2", 3") down to (4", 0"), reaching the bottom edge
    """
    timber = Timber(
        length=feet(4),
        size=Matrix([inches(6), inches(8)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
    )
    bulge = ArcSegment(
        center=create_v2(inches(1), inches(3)), radius=inches(1),
        start_angle=pi, sweep_angle=pi / 2,
    )
    tuck = ArcSegment(
        center=create_v2(inches(2), inches(2)), radius=inches(1),
        start_angle=pi, sweep_angle=-pi / 2,
    )
    run = LineSegment(tuck.end, create_v2(inches(4), scalar(0)))

    return cut_practice_path_extrusion_corner_end_decoration(
        timber=timber,
        cut_corner=TimberShortEdge.BOTTOM_RIGHT,
        cut_path=[bulge, tuck, run],
    )


patterns = [
    Pattern(
        path="decorative_joints/roundover",
        lambda_=make_pattern_from_joint(example_roundover_decoration),
        pattern_type='frame',
        tags=['main'],
    ),
    Pattern(
        path="decorative_joints/roundover_imperfect",
        lambda_=make_pattern_from_joint(example_roundover_imperfect),
        pattern_type='frame',
        tags=['main'],
    ),
    Pattern(
        path="decorative_joints/rafter_tail_scallop",
        lambda_=make_pattern_from_joint(example_rafter_tail_scallop_decoration),
        pattern_type='frame',
        tags=['main'],
    ),
    Pattern(
        path="decorative_joints/path_extrusion_corner_end",
        lambda_=make_pattern_from_joint(example_path_extrusion_corner_end_decoration),
        pattern_type='frame',
        tags=['main'],
    ),
]
