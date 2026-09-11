"""The vocabulary for pointing at part of a timber.

Enums only, and no timber: these name the parts a timber HAS -- its six faces,
its twelve arrises, its eight corners, its centerlines and its two center
planes -- without knowing where any particular timber is. Turning one of these
into a line or a plane in space is measuring.py's job.

They live here rather than in timber.py because ticket.py wants them too, for
TimberTicket.reference_features, and timber.py imports ticket.py. Nothing here
imports anything of kumiki's but rule.py, which is what lets it sit underneath
both. timber.py re-exports the lot, so `from kumiki.timber import
TimberLongFace` still reaches them.

TimberFeature is the whole vocabulary in one enum; the narrower ones --
TimberLongFace, TimberLongEdge, TimberCenterplane -- are subsets that SHARE ITS
VALUES, and every converter moves between the two by value alone. That is why
the numbering is not free: see TimberFeature's own docstring.
"""

from enum import Enum
from typing import Tuple, Union

from .rule import *


# ============================================================================
# Timber Feature Enums
# ============================================================================


class TimberFeature(Enum):
    """Everything a timber has that can be pointed at, in one enum.

    The values carry weight in two directions and so are not free to change:

    - the narrower enums below share them, and every converter moves between
      the two by value (`TimberFace(self.value)`), so a member and its
      counterpart must always agree;
    - 1..6 are pinned to cutcsg.PrismFace, and the ORDER of the face and edge
      members is pinned to a prism's default SIDE and ARRIS indices, so that
      "arris.5" and BOTTOM_FRONT_EDGE pick out the same line. cutcsg cannot
      say so itself (timber imports cutcsg), so TestDefaultOrderFollowsTimber-
      Feature pins it from the test side.

    That second constraint reads member NAMES -- a prism side is a member
    ending `_FACE`, an arris one ending `_EDGE` -- so a new member must not end
    in either unless it really is one. RIGHT_FACE_CENTERLINE is safe;
    RIGHT_CENTERLINE_FACE would quietly break it.
    """

    TOP_FACE = 1
    BOTTOM_FACE = 2
    RIGHT_FACE = 3
    FRONT_FACE = 4
    LEFT_FACE = 5
    BACK_FACE = 6
    # 7 is retired. It was CENTERLINE, which moved to 30 to sit with the other
    # centerlines. Left empty rather than handed to something else: a value is
    # how a narrow enum addresses a member, so reusing 7 would silently turn
    # anything still holding the old one into a different feature.
    # Long edges (edges running along the length of the timber)
    RIGHT_FRONT_EDGE = 8
    FRONT_LEFT_EDGE = 9
    LEFT_BACK_EDGE = 10
    BACK_RIGHT_EDGE = 11
    # Short edges (edges on the ends of the timber)
    BOTTOM_RIGHT_EDGE = 12
    BOTTOM_FRONT_EDGE = 13
    BOTTOM_LEFT_EDGE = 14
    BOTTOM_BACK_EDGE = 15
    TOP_RIGHT_EDGE = 16
    TOP_FRONT_EDGE = 17
    TOP_LEFT_EDGE = 18
    TOP_BACK_EDGE = 19
    # corners
    BOT_RIGHT_FRONT = 20
    BOT_FRONT_LEFT = 21
    BOT_LEFT_BACK = 22
    BOT_BACK_RIGHT = 23
    TOP_RIGHT_FRONT = 24
    TOP_FRONT_LEFT = 25
    TOP_LEFT_BACK = 26
    TOP_BACK_RIGHT = 27
    # Center planes: the two planes through the centerline that bisect the
    # timber lengthwise, each named for the pair of long faces it lies between.
    # There is deliberately no TOP/BOTTOM one -- it is not a LONG plane, and it
    # moves whenever an end cut changes the timber's effective length.
    RIGHT_LEFT_CENTER_PLANE = 28
    FRONT_BACK_CENTER_PLANE = 29
    # Centerlines, all running the length of the timber. The first is the
    # timber's own axis; the other four each run down the middle of one long
    # face, and are where a center plane meets that face -- note the pairing
    # crosses over, so the RIGHT face's centerline lies in the FRONT_BACK plane.
    CENTERLINE = 30
    RIGHT_FACE_CENTERLINE = 31
    FRONT_FACE_CENTERLINE = 32
    LEFT_FACE_CENTERLINE = 33
    BACK_FACE_CENTERLINE = 34

    @property
    def to(self) -> 'TimberFeature':
        """Convert to TimberFeature for further conversions. This is a no-op."""
        return self

    def feature(self) -> 'TimberFeature':
        """Convert to TimberFeature. This is a no-op."""
        return self
    
    def face(self) -> 'TimberFace':
        """Convert to TimberFace. Values 1-6 map to faces."""
        if self.value not in range(1, 7):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberFace. Only values 1-6 are valid faces.")
        return TimberFace(self.value)
    
    def end(self) -> 'TimberEnd':
        """Convert to TimberEnd. Values 1-2 map to ends."""
        if self.value not in range(1, 3):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberEnd. Only values 1-2 are valid ends.")
        return TimberEnd(self.value)
    
    def long_face(self) -> 'TimberLongFace':
        """Convert to TimberLongFace. Values 3-6 map to long faces."""
        if self.value not in range(3, 7):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberLongFace. Only values 3-6 are valid long faces.")
        return TimberLongFace(self.value)

    def edge(self) -> 'TimberEdge':
        """Convert to TimberEdge. Values 8-19 map to edges."""
        if self.value not in range(8, 20):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberEdge. Only values 8-19 are valid edges.")
        return TimberEdge(self.value)

    def centerline(self) -> 'TimberCenterline':
        """Convert to TimberCenterline. Value 30 maps to CENTERLINE.

        The timber's own axis only. A long face's centerline is a different
        enum -- see long_face_centerline and the note on TimberCenterline.
        """
        if self.value != 30:
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberCenterline. Only value 30 is valid.")
        return TimberCenterline(self.value)

    def long_face_centerline(self) -> 'TimberLongFaceCenterline':
        """Convert to TimberLongFaceCenterline. Values 31-34 map to long face centerlines."""
        if self.value not in range(31, 35):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberLongFaceCenterline. Only values 31-34 are valid long face centerlines.")
        return TimberLongFaceCenterline(self.value)

    def center_plane(self) -> 'TimberCenterplane':
        """Convert to TimberCenterplane. Values 28-29 map to center planes."""
        if self.value not in range(28, 30):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberCenterplane. Only values 28-29 are valid center planes.")
        return TimberCenterplane(self.value)

    def long_faces_it_rests_on(self) -> Tuple['TimberLongFace', ...]:
        """The long faces this feature is a surface of, or an edge of.

        A long face rests on itself; an arris on the two faces that meet at it.
        Everything else rests on none -- a centerline or a center plane is
        intrinsic to the perfect timber within and has no face to belong to,
        and a short feature is not a long one at all.

        What this is for: a face is the one kind of feature whose position
        depends on the ROUGH timber matching the perfect one. Asking a feature
        which faces it rests on is asking which of those agreements it needs.
        """
        if self.value in range(3, 7):
            return (self.long_face(),)
        if self.value in range(8, 12):
            return self.long_edge().long_faces
        return ()
    
    def long_edge(self) -> 'TimberLongEdge':
        """Convert to TimberLongEdge. Values 8-11 map to long edges."""
        if self.value not in range(8, 12):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberLongEdge. Only values 8-11 are valid long edges.")
        return TimberLongEdge(self.value)

    def short_edge(self) -> 'TimberShortEdge':
        """Convert to TimberShortEdge. Values 12-19 map to short edges."""
        if self.value not in range(12, 20):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberShortEdge. Only values 12-19 are valid short edges.")
        return TimberShortEdge(self.value)

    def corner(self) -> 'TimberCorner':
        """Convert to TimberCorner. Values 20-27 map to corners."""
        if self.value not in range(20, 28):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberCorner. Only values 20-27 are valid corners.")
        return TimberCorner(self.value)
    
class TimberFace(Enum):
    TOP = 1 # the face vector with normal vector in the +Z axis direction
    BOTTOM = 2 # the face vector with normal vector in the -Z axis direction
    RIGHT = 3 # the face vector with normal vector in the +X axis direction
    FRONT = 4 # the face vector with normal vector in the +Y axis direction
    LEFT = 5 # the face vector with normal vector in the -X axis direction
    BACK = 6 # the face vector with normal vector in the -Y axis direction
    
    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)
    
    def get_direction(self) -> Direction3D:
        """Get the direction vector for this face in world coordinates."""
        if self == TimberFace.TOP:
            return create_v3(scalar(0), scalar(0), scalar(1))
        elif self == TimberFace.BOTTOM:
            return create_v3(scalar(0), scalar(0), scalar(-1))
        elif self == TimberFace.RIGHT:
            return create_v3(scalar(1), scalar(0), scalar(0))
        elif self == TimberFace.LEFT:
            return create_v3(scalar(-1), scalar(0), scalar(0))
        elif self == TimberFace.FRONT:
            return create_v3(scalar(0), scalar(1), scalar(0))
        else:  # BACK
            return create_v3(scalar(0), scalar(-1), scalar(0))

    # TODO rename to is_orthogonal?
    def is_perpendicular(self, other: 'TimberFace') -> bool:
        """
        Check if two faces are perpendicular to each other.
        
        Perpendicular face pairs (orthogonal axes):
        - X-axis faces (RIGHT, LEFT) <-> Y-axis faces (FRONT, BACK)
        - X-axis faces (RIGHT, LEFT) <-> Z-axis faces (TOP, BOTTOM)
        - Y-axis faces (FRONT, BACK) <-> Z-axis faces (TOP, BOTTOM)
        """
        # Define axis groups
        x_faces = {TimberFace.RIGHT, TimberFace.LEFT}
        y_faces = {TimberFace.FRONT, TimberFace.BACK}
        z_faces = {TimberFace.TOP, TimberFace.BOTTOM}
        
        # Two faces are perpendicular if they are on different axes
        self_in_x = self in x_faces
        self_in_y = self in y_faces
        self_in_z = self in z_faces
        
        other_in_x = other in x_faces
        other_in_y = other in y_faces
        other_in_z = other in z_faces
        
        # Perpendicular if on different axes
        return (self_in_x and (other_in_y or other_in_z)) or \
               (self_in_y and (other_in_x or other_in_z)) or \
               (self_in_z and (other_in_x or other_in_y))
    
    def get_opposite_face(self) -> 'TimberFace':
        """
        Get the opposite face (the face on the opposite side of the timber).
        
        Opposite pairs:
        - TOP <-> BOTTOM
        - RIGHT <-> LEFT
        - FRONT <-> BACK
        """
        if self == TimberFace.TOP:
            return TimberFace.BOTTOM
        elif self == TimberFace.BOTTOM:
            return TimberFace.TOP
        elif self == TimberFace.RIGHT:
            return TimberFace.LEFT
        elif self == TimberFace.LEFT:
            return TimberFace.RIGHT
        elif self == TimberFace.FRONT:
            return TimberFace.BACK
        else:  # BACK
            return TimberFace.FRONT

    def rotate_about(self, face: 'TimberFace') -> 'TimberFace':
        """
        Rotate this face by 90 degrees about `face`'s outward-normal axis
        (a quarter turn using the right-hand rule around that normal).

        If this face IS the rotation axis (self == face or self ==
        face.get_opposite_face()), it lies on the axis and is unaffected by
        the rotation, so it is returned unchanged.
        """
        if self == face or self == face.get_opposite_face():
            return self

        # Each cycle lists the 4 faces perpendicular to the rotation axis, in
        # the order a right-hand rotation about that axis's outward normal
        # maps them (self -> next element, wrapping around).
        cycles = {
            TimberFace.TOP: [TimberFace.RIGHT, TimberFace.FRONT, TimberFace.LEFT, TimberFace.BACK],
            TimberFace.BOTTOM: [TimberFace.RIGHT, TimberFace.BACK, TimberFace.LEFT, TimberFace.FRONT],
            TimberFace.RIGHT: [TimberFace.FRONT, TimberFace.TOP, TimberFace.BACK, TimberFace.BOTTOM],
            TimberFace.LEFT: [TimberFace.FRONT, TimberFace.BOTTOM, TimberFace.BACK, TimberFace.TOP],
            TimberFace.FRONT: [TimberFace.RIGHT, TimberFace.BOTTOM, TimberFace.LEFT, TimberFace.TOP],
            TimberFace.BACK: [TimberFace.RIGHT, TimberFace.TOP, TimberFace.LEFT, TimberFace.BOTTOM],
        }
        cycle = cycles[face]
        index = cycle.index(self)
        return cycle[(index + 1) % len(cycle)]

class TimberEnd(Enum):
    TOP = 1
    BOTTOM = 2
    
    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)

class TimberLongFace(Enum):
    RIGHT = 3
    FRONT = 4
    LEFT = 5
    BACK = 6
    
    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)
    
    def is_perpendicular(self, other: 'TimberLongFace') -> bool:
        """
        Check if two long faces are perpendicular to each other.
        
        Perpendicular face pairs:
        - RIGHT <-> FRONT, RIGHT <-> BACK
        - LEFT <-> FRONT, LEFT <-> BACK
        """
        return self.to.face().is_perpendicular(other.to.face())

    def rotate_right(self) -> 'TimberLongFace':
        """Rotate the long face right (90 degrees clockwise)."""
        # Map from 3-6 to 0-3, rotate, then map back to 3-6
        return TimberLongFace((self.value - 3 + 1) % 4 + 3)
    
    def rotate_left(self) -> 'TimberLongFace':
        """Rotate the long face left (90 degrees counter-clockwise)."""
        # Map from 3-6 to 0-3, rotate, then map back to 3-6
        return TimberLongFace((self.value - 3 - 1) % 4 + 3)

class TimberCorner(Enum):
    BOT_RIGHT_FRONT = 20
    BOT_FRONT_LEFT = 21
    BOT_LEFT_BACK = 22
    BOT_BACK_RIGHT = 23
    TOP_RIGHT_FRONT = 24
    TOP_FRONT_LEFT = 25
    TOP_LEFT_BACK = 26
    TOP_BACK_RIGHT = 27
class TimberCenterline(Enum):
    """The timber's own axis, and nothing else.

    One member, and it stays that way. Half the library uses this enum as a
    SENTINEL TYPE rather than as a value -- `Union[TimberLongFace,
    TimberCenterline]` in construction.py means "a face, or else measure from
    the axis", and measuring.locate_edge branches on `isinstance(edge,
    TimberCenterline)` to return the axis line. A second member would make
    every one of those quietly wrong instead of raising, which is why a long
    face's centerline is TimberLongFaceCenterline and not a member here.

    TODO consider renaming this to TimberAxis. That is what it means, it is
    what stops anyone reading the name as "any centerline" and adding to it,
    and it would let SomeTimberCenterline be the name for the group.
    """

    CENTERLINE = 30

    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)


class TimberLongFaceCenterline(Enum):
    """The line down the middle of one long face, running the timber's length.

    Named for the face it lies on, as TimberLongFace is. Geometrically it is
    where a center plane meets that face, and the pairing crosses over: the
    RIGHT face's centerline lies in the FRONT_BACK plane, since that is the
    plane the RIGHT face is not parallel to.

    Only the four LONG faces have one. An end face has two centerlines rather
    than one, neither running the timber's length, and they move with every end
    cut -- a separate enum's problem, if anyone ever wants them.
    """

    RIGHT = 31
    FRONT = 32
    LEFT = 33
    BACK = 34

    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)

    @property
    def long_face(self) -> 'TimberLongFace':
        """The long face this centerline runs down the middle of."""
        # The four are numbered in TimberLongFace's order, 31..34 against 3..6.
        return TimberLongFace(self.value - 28)

    @property
    def center_plane(self) -> 'TimberCenterplane':
        """The center plane this centerline lies in.

        The crossed-over pairing: a RIGHT or LEFT face's centerline lies in the
        FRONT_BACK plane, and a FRONT or BACK face's in the RIGHT_LEFT plane.
        """
        if self in (TimberLongFaceCenterline.RIGHT, TimberLongFaceCenterline.LEFT):
            return TimberCenterplane.FRONT_BACK
        return TimberCenterplane.RIGHT_LEFT


class TimberCenterplane(Enum):
    """One of the two planes that bisect the timber along its length.

    Named for the pair of long faces it lies between, matching the
    RIGHT_FRONT_EDGE convention. Each contains the centerline and has its
    normal along one of the timber's local cross-section axes: RIGHT_LEFT's
    normal is the width axis, FRONT_BACK's the height axis.

    Unlike a face, a center plane is not a surface -- it is a datum, and it
    exists whether or not the timber is perfect, which is what makes it
    somewhere to measure from when no face is.
    """

    RIGHT_LEFT = 28
    FRONT_BACK = 29

    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)

    @property
    def long_faces(self) -> Tuple['TimberLongFace', 'TimberLongFace']:
        """The two long faces this plane lies between."""
        if self is TimberCenterplane.RIGHT_LEFT:
            return (TimberLongFace.RIGHT, TimberLongFace.LEFT)
        return (TimberLongFace.FRONT, TimberLongFace.BACK)

class TimberEdge(Enum):
    # Long edges (edges running along the length of the timber)
    RIGHT_FRONT = 8
    FRONT_LEFT = 9
    LEFT_BACK = 10
    BACK_RIGHT = 11
    # Short edges (edges on the ends of the timber)
    BOTTOM_RIGHT = 12
    BOTTOM_FRONT = 13
    BOTTOM_LEFT = 14
    BOTTOM_BACK = 15
    TOP_RIGHT = 16
    TOP_FRONT = 17
    TOP_LEFT = 18
    TOP_BACK = 19
    
    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)

    def canonical_line_from_corner(self) -> Tuple['TimberCorner', 'TimberFace']:
        """Returns canonical way to express a line from an edge.
        The line is defined by starting from the TimberCorner and pointing
        in the direction of the returned TimberFace's outward normal.

        For long edges the line starts at the bottom corner and points toward TOP.
        For short edges the direction follows cross(long_face_normal, end_outward).
        """
        _map = {
            TimberEdge.RIGHT_FRONT: (TimberCorner.BOT_RIGHT_FRONT, TimberFace.TOP),
            TimberEdge.FRONT_LEFT:  (TimberCorner.BOT_FRONT_LEFT,  TimberFace.TOP),
            TimberEdge.LEFT_BACK:   (TimberCorner.BOT_LEFT_BACK,   TimberFace.TOP),
            TimberEdge.BACK_RIGHT:  (TimberCorner.BOT_BACK_RIGHT,  TimberFace.TOP),

            TimberEdge.BOTTOM_RIGHT: (TimberCorner.BOT_BACK_RIGHT,  TimberFace.FRONT),
            TimberEdge.BOTTOM_FRONT: (TimberCorner.BOT_RIGHT_FRONT, TimberFace.LEFT),
            TimberEdge.BOTTOM_LEFT:  (TimberCorner.BOT_FRONT_LEFT,  TimberFace.BACK),
            TimberEdge.BOTTOM_BACK:  (TimberCorner.BOT_LEFT_BACK,   TimberFace.RIGHT),

            TimberEdge.TOP_RIGHT: (TimberCorner.TOP_RIGHT_FRONT, TimberFace.BACK),
            TimberEdge.TOP_FRONT: (TimberCorner.TOP_FRONT_LEFT,  TimberFace.RIGHT),
            TimberEdge.TOP_LEFT:  (TimberCorner.TOP_LEFT_BACK,   TimberFace.FRONT),
            TimberEdge.TOP_BACK:  (TimberCorner.TOP_BACK_RIGHT,  TimberFace.LEFT),
        }
        return _map[self]

    def long_edge(self) -> 'TimberLongEdge':
        """Convert to TimberLongEdge. Values 8-11 map to long edges."""
        if self.value not in range(8, 12):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberLongEdge. Only values 8-11 are valid long edges.")
        return TimberLongEdge(self.value)

    def short_edge(self) -> 'TimberShortEdge':
        """Convert to TimberShortEdge. Values 12-19 map to short edges."""
        if self.value not in range(12, 20):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberShortEdge. Only values 12-19 are valid short edges.")
        return TimberShortEdge(self.value)


class TimberLongEdge(Enum):
    RIGHT_FRONT = 8
    FRONT_LEFT = 9
    LEFT_BACK = 10
    BACK_RIGHT = 11

    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)

    @property
    def long_faces(self) -> Tuple['TimberLongFace', 'TimberLongFace']:
        """The two long faces that meet at this arris, in the order it is named."""
        first, second = self.name.split("_")
        return (TimberLongFace[first], TimberLongFace[second])


class TimberShortEdge(Enum):
    BOTTOM_RIGHT = 12
    BOTTOM_FRONT = 13
    BOTTOM_LEFT = 14
    BOTTOM_BACK = 15
    TOP_RIGHT = 16
    TOP_FRONT = 17
    TOP_LEFT = 18
    TOP_BACK = 19
    
    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)

    @property
    def end(self) -> TimberEnd:
        """Get the TimberEnd associated with this short edge."""
        if self.value in (12, 13, 14, 15):
            return TimberEnd.BOTTOM
        else:
            return TimberEnd.TOP

    @property
    def long_face(self) -> TimberLongFace:
        """Get the TimberLongFace associated with this short edge."""
        _map = {
            12: TimberLongFace.RIGHT,
            16: TimberLongFace.RIGHT,
            13: TimberLongFace.FRONT,
            17: TimberLongFace.FRONT,
            14: TimberLongFace.LEFT,
            18: TimberLongFace.LEFT,
            15: TimberLongFace.BACK,
            19: TimberLongFace.BACK,
        }
        return _map[self.value]


# ============================================================================
# Type Aliases
# ============================================================================

# Union type for face-like enums (TimberFace, TimberEnd, or TimberLongFace)
SomeTimberFace = Union[TimberFace, TimberEnd, TimberLongFace]

# Anything that names a timber feature: TimberFeature itself, or one of the
# narrow enums that `.to` widens into it. TimberCorner is the one member of the
# family missing, because it is the one without a `.to`.
#
# For PARAMETERS that accept any of them. A field that stores one should say
# TimberFeature, since that is what it holds once widened.
SomeTimberFeature = Union[
    TimberFeature, TimberFace, TimberEnd, TimberLongFace, TimberEdge,
    TimberLongEdge, TimberShortEdge, TimberCenterline,
    TimberLongFaceCenterline, TimberCenterplane,
]

# Either kind of centerline. An alias rather than one enum with five members,
# because TimberCenterline is a sentinel type half the library branches on --
# see the note on it. Annotate with this where BOTH are genuinely accepted, and
# with TimberCenterline where only the axis is.
SomeTimberCenterline = Union[TimberCenterline, TimberLongFaceCenterline]

# Everything on a timber that is a LINE running its full length: the four
# arrises, the axis, and the four long face centerlines. What a reference
# feature has to be to be drawn as a reference edge -- see
# TimberTicket.primary_reference_edge.
LongEdgeOrCenterline = Union[TimberLongEdge, TimberCenterline, TimberLongFaceCenterline]

# Every feature that runs the length of the timber, and so survives an end cut:
# the long faces, the arrises, both center planes and all five centerlines. The
# ends, short edges and corners are exactly what is missing, because each moves
# when the timber is cut to length.
LONG_TIMBER_FEATURES: frozenset = frozenset(
    [feature.to for feature in TimberLongFace]
    + [feature.to for feature in TimberLongEdge]
    + [feature.to for feature in TimberCenterplane]
    + [feature.to for feature in TimberCenterline]
    + [feature.to for feature in TimberLongFaceCenterline]
)
