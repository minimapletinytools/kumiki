"""
Decorative Joints Patterns
"""

from kumiki import *
from kumiki.pathcsg import StraightSegment, ArcSegment
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
    """A single edge rounded over on an imperfect timber."""
    timber = Timber(
        length=feet(3),
        size=Matrix([inches(4), inches(4)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
        rough_half_sizes=(
            create_v2(inches(2 + 1), inches(2)),
            create_v2(inches(2 + 1), inches(2)),
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
    A carved corner scoop at the bottom-right end of a timber.
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
    run = StraightSegment(tuck.end, create_v2(inches(4), scalar(0)))

    return cut_practice_path_extrusion_corner_end_decoration(
        timber=timber,
        cut_corner=TimberShortEdge.BOTTOM_RIGHT,
        cut_path=[bulge, tuck, run],
    )


def example_straight_angled_end_cut_decoration() -> Joint:
    """A single timber with an angled cut decoration on its top end."""
    timber = Timber(
        length=feet(4),
        size=Matrix([inches(4), inches(6)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
    )
    return cut_practice_straight_angled_end_cut_decoration(
        timber=timber,
        front_face=TimberFace.FRONT,
        position_from_end=inches(3),
        angle=degrees(30),
        angle_towards_face=TimberFace.RIGHT,
        timber_end=TimberEnd.TOP,
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
    Pattern(
        path="decorative_joints/straight_angled_end_cut",
        lambda_=make_pattern_from_joint(example_straight_angled_end_cut_decoration),
        pattern_type='frame',
        tags=['main'],
    ),
]
