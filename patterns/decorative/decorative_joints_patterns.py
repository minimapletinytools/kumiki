# Last checked on kumiki 0.9.0
"""
Decorative Joints Patterns
"""

from kumiki import *
from kumiki.csg.pathcsg import StraightSegment, ArcSegment


EXAMPLE_ROUNDOVER_DECORATION_OPTIONS = kiwari(
    radius=kiwari.length(inches(1, 2), minimum=inches(1, 8)),
)


@pattern('decorative/roundover', tags=["main"], kiwari=EXAMPLE_ROUNDOVER_DECORATION_OPTIONS)
def example_roundover_decoration(k: Optional[Kiwari] = None) -> Joint:
    """A single timber with all 12 edges rounded over."""
    k = EXAMPLE_ROUNDOVER_DECORATION_OPTIONS.resolve(k)
    timber = Timber(
        length=feet(4),
        size=Matrix([inches(4), inches(6)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
    )
    return cut_practice_roundover_decoration(
        timber=timber,
        edges=list(TimberEdge),
        radius=k.length("radius"),
    )


EXAMPLE_ROUNDOVER_IMPERFECT_OPTIONS = kiwari(
    radius=kiwari.length(inches(1, 2), minimum=inches(1, 8)),
)


@pattern('decorative/roundover_imperfect', tags=["main"], kiwari=EXAMPLE_ROUNDOVER_IMPERFECT_OPTIONS)
def example_roundover_imperfect(k: Optional[Kiwari] = None) -> Joint:
    """A single edge rounded over on an imperfect timber."""
    k = EXAMPLE_ROUNDOVER_IMPERFECT_OPTIONS.resolve(k)
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
        radius=k.length("radius"),
    )


EXAMPLE_RAFTER_TAIL_SCALLOP_DECORATION_OPTIONS = kiwari(
    height=kiwari.length(inches(2)),
    length=kiwari.length(inches(4)),
)


@pattern('decorative/rafter_tail_scallop', tags=["main"], kiwari=EXAMPLE_RAFTER_TAIL_SCALLOP_DECORATION_OPTIONS)
def example_rafter_tail_scallop_decoration(k: Optional[Kiwari] = None) -> Joint:
    """A rafter tail with a scalloped decorative cut on its underside near the tail end."""
    k = EXAMPLE_RAFTER_TAIL_SCALLOP_DECORATION_OPTIONS.resolve(k)
    timber = Timber(
        length=feet(4),
        size=Matrix([inches(4), inches(6)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
    )
    return cut_practice_rafter_tail_scallop_corner_end_decoration(
        timber=timber,
        short_edge=TimberShortEdge.TOP_BACK,
        scallop_height=k.length("height"),
        scallop_length=k.length("length"),
    )


@pattern('decorative/path_extrusion_corner_end', tags=["main"])
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


EXAMPLE_STRAIGHT_ANGLED_END_CUT_DECORATION_OPTIONS = kiwari(
    distance=kiwari.length(inches(3)),
    angle=kiwari.angle(degrees(30)),
)


@pattern('decorative/straight_angled_end_cut', tags=["main"], kiwari=EXAMPLE_STRAIGHT_ANGLED_END_CUT_DECORATION_OPTIONS)
def example_straight_angled_end_cut_decoration(k: Optional[Kiwari] = None) -> Joint:
    """A single timber with an angled cut decoration on its top end."""
    k = EXAMPLE_STRAIGHT_ANGLED_END_CUT_DECORATION_OPTIONS.resolve(k)
    timber = Timber(
        length=feet(4),
        size=Matrix([inches(4), inches(6)]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
    )
    return cut_practice_straight_angled_end_cut_decoration(
        timber=timber,
        front_face=TimberFace.FRONT,
        position_from_end=k.length("distance"),
        angle=k.angle("angle"),
        angle_towards_face=TimberFace.RIGHT,
        timber_end=TimberEnd.TOP,
    )




ROUNDED_END = kiwari(radius=kiwari.length(inches(5)), distance=kiwari.length(inches(5)))


@pattern("decorative/rounded_end", kiwari=ROUNDED_END)
def rounded_end(k: Optional[Kiwari] = None) -> Joint:
    k = ROUNDED_END.resolve(k)
    timber = Timber(length=feet(4), size=create_v2(inches(4), inches(6)),
                    transform=Transform.identity(), ticket=TimberTicket(path="timber"))
    return cut_practice_rounded_end_decoration(
        timber, TimberFace.RIGHT, TimberFace.TOP, k.length("radius"), k.length("distance"))
