"""
Decorative Joints Patterns
"""

from kumiki import *
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

    The timber's actual (nominal/rough-stock) dimensions are 1 inch more than
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
        nominal_half_sizes=(
            create_v2(inches(2 + 1), inches(2)),  # width: right_half (+1"), left_half (perfect)
            create_v2(inches(2 + 1), inches(2)),  # height: front_half (+1"), back_half (perfect)
        ),
    )
    return cut_practice_roundover_decoration(
        timber=timber,
        edges=[TimberEdge.RIGHT_FRONT],
        radius=inches(1, 2),
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
]
