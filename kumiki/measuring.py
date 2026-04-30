"""
Measuring related primitives and functions for marking timbers. The feature primitives defined in this class should only be used for measuring and marking.

When cutting joint on timbers, we want to do things like measure from a reference edge of one timber, and mark that location onto a face of another timber. The types defined in `LocatedTimberFeature` are exactly the features that we care about when measuring on timbers.

Timber features are named geometric features on a timber, e.g. the centerline, the top face, etc. See `TimberFeature` enum in `timber.py` for a list of all timber features.

- Locations are GLOBAL features
- Markings are LOCAL features

Measuring functions follow the following naming convention:

- `locate_*` : functions that take measurements relative to a (LOCAL) feature of a timber and outputs a feature in GLOBAL space
- `mark_*` : functions that take a feature in GLOBAL space and outputs a marking relative to a (LOCAL) feature of a timber
- `scribe_*` : functions that take multiple measurements relative to (LOCAL) features of timbers and outputs a measurement relative to a (LOCAL) feature of a timber

OR put more simply:

- `locate_*` means LOCAL to GLOBAL
- `mark_*` means GLOBAL to LOCAL
- `scribe_*` means LOCAL to LOCAL

In addition we use the naming convention `mark_*_by_*` which mark specific primitives using by the specified method.
TODO All `mark_*` methods that are not mark_*_by_* should be deprecated!

Using these functions, we can locate relative to features on one timber and mark them onto another timber. 

For example, if we `my_feature = locate_into_face(mm(10), TimberFace.RIGHT, timberA)` we mean the location (feature) that is a plane 10mm into and parallel with the right face of the timber.
And then if we `mark_distance_from_face_in_normal_direction(my_feature, timberB, TimberFace.RIGHT)` we mean mark the distance from `my_feature` to the right face of timberB. 

Some locations are signed and oriented. These features follow the following sign conventions:

- locations from timber faces are along the normal pointing INTO the timber i.e. positive is into the face
- locations from timber halfplanes aligning with a timber edge
    - positive X is towards the face
    - for long faces postivie Y is (usually) in the direction of the timber, sometimes it's the opposite so watch out!
    - for end faces, use RHS rule with +Z ponting in the direction of the end
- locations from timber corners
    - TODO but also we never do this so who cares

Some locations also have an "origin" point. This information is currently not used in any of these functions. Timber Features follow the following location conventions:

- timber faces are located at the center of the face surface
- timber edges are located on the bottom face of the timber

A `Point` is just a `V3` and sometimes you might find yourself marking a `Point` and simply using its contained `V3` directly! This is OK. We still wrap it in a `Point` to help ensure encapsulation of locating and marking functions. In particular, some of these functions can take many different types of features and we want to be intentional about passing `Points` into these functions!

Note there is some redundancy in terminology:

locate <-> measure
location <-> feature

measurements just mean some distance relative to some feature. Both markings and locations are measurements.
"""

from dataclasses import dataclass
from typing import Union, cast
from abc import ABC, abstractmethod
from .rule import *
from .timber import *



EdgeOrCenterline = Union[TimberEdge, TimberCenterline]


# ============================================================================
# Geometric Feature Types
# ============================================================================


# Type alias for all measurable geometric features on timbers
# We may also refer to these as `Locations` 
LocatedTimberFeature = Union['Point', 'Line', 'Plane', 'UnsignedPlane', 'HalfPlane', 'Space']

@dataclass(frozen=True)
class Point:
    """
    Represents a point in 3D space.
    """
    position: V3

    def __repr__(self) -> str:
        return f"Point(position={self.position})"


@dataclass(frozen=True)
class Line:
    """
    Represents an oriented line with origin in 3D space.
    """
    direction: Direction3D
    point: V3

    def __repr__(self) -> str:
        return f"Line(direction={self.direction}, point={self.point})"


@dataclass(frozen=True)
class Plane:
    """
    Represents an oriented plane with origin in 3D space.
    """
    normal: Direction3D
    point: V3

    def __repr__(self) -> str:
        return f"Plane(normal={self.normal}, point={self.point})"

    @staticmethod
    def from_transform_and_direction(transform: Transform, direction: Direction3D) -> 'Plane':
        """
        Create a plane from a transform and a direction.
        
        Args:
            transform: Transform defining the position and orientation
            direction: Direction in the transform's local coordinate system
            
        Returns:
            Plane with normal in global coordinates and point at transform position
        """
        from kumiki.rule import safe_transform_vector
        return Plane(safe_transform_vector(transform.orientation.matrix, direction), transform.position)

@dataclass(frozen=True)
class UnsignedPlane(Plane):
    """
    Same as Plane but the sign on the normal should be ignored.
    """
    normal: Direction3D
    point: V3

    def __repr__(self) -> str:
        return f"UnsignedPlane(normal={self.normal}, point={self.point})"


    @staticmethod
    def from_transform_and_direction(transform: Transform, direction: Direction3D) -> 'UnsignedPlane':
        """
        Create an unsigned plane from a transform and a direction.
        
        Args:
            transform: Transform defining the position and orientation
            direction: Direction in the transform's local coordinate system
            
        Returns:
            UnsignedPlane with normal in global coordinates and point at transform position
        """
        from kumiki.rule import safe_transform_vector
        return UnsignedPlane(safe_transform_vector(transform.orientation.matrix, direction), transform.position)

# TODO rename to LineOnPlane
@dataclass(frozen=True)
class HalfPlane:
    """
    Represents an oriented half-plane with origin in 3D space.
    """
    normal: Direction3D # this is the + direction of any measurements
    point_on_line: V3
    line_direction: Direction3D # MUST be perpendicular to the normal

    def __repr__(self) -> str:
        return f"HalfPlane(normal={self.normal}, point_on_line={self.point_on_line}, line_direction={self.line_direction})"


@dataclass(frozen=True)
class Space:
    """
    Represents an ORIENTED 3D space.
    """
    transform: Transform
    
    def __repr__(self) -> str:
        return f"Space(transform={self.transform})"

# ============================================================================
# Marking Classes
# ============================================================================

# TODO consider not having an ABC here... not actually needed
@dataclass(frozen=True)
class Marking(ABC):
    @abstractmethod
    def locate(self) -> Union[UnsignedPlane, Plane, Line, Point, HalfPlane, Space]:
        pass

@dataclass(frozen=True)
class DistanceFromFace(Marking):
    """
    Represents a distance from a face on a timber with + being AWAY from the face.
    """
    distance: Numeric
    timber: PerfectTimberWithin
    face: SomeTimberFace
    

    def locate(self) -> UnsignedPlane:
        """
        Convert the distance from a face to an unsigned plane.
        """
        return locate_into_face(self.distance, self.face, self.timber)

@dataclass(frozen=True)
class DistanceFromPointIntoFace(Marking):
    """
    Represents a distance from a point into a face on a timber with + being INTO the timber (that is the negative face normal direction is the + axis of the measurement)
    If the point is not supplied, the center of the face is used.
    """
    distance: Numeric
    timber: PerfectTimberWithin
    face: TimberFace
    point: Optional[V3] = None
    
    def locate(self) -> Point:
        """
        Convert the distance from a point into a face to a Point

        Returns:
            Point at the specified distance from the starting point
        """
        # Determine the starting point (either provided point or face center)
        if self.point is not None:
            starting_point = self.point
        else:
            starting_point = get_point_on_face_global(self.face, self.timber)

        # Get the face normal (pointing OUT of the timber)
        face_normal = self.timber.get_face_direction_global(self.face)

        # Direction AWAY from the face is -face_normal
        away_direction = -face_normal

        # Calculate the line position by offsetting from the starting point
        # Positive distance means away from the face
        line_point = starting_point + away_direction * self.distance

        # The line direction is perpendicular to the face (away from it)
        #return Line(away_direction, line_point)
        return Point(line_point)
    
@dataclass(frozen=True)
class DistanceFromLongEdgeOnFace(Marking):
    """
    Represents a distance from a long edge on a timber with + being onto the face from the edge.
    """
    distance: Numeric
    timber: Timber
    edge: TimberLongEdge
    face: TimberFace
    
    def locate(self) -> Line:
        """
        Convert the distance from a long edge to a line on the specified face.

        Returns a line parallel to the edge, on the given face, at the specified distance from the edge.
        The distance is measured along the face plane, perpendicular to the edge direction.
        Positive distance means moving in the direction of the "other" face's normal (the face that
        defines the edge together with self.face).

        Returns:
            Line parallel to the edge at the specified distance on the face
        """
        # Get the edge line
        edge_line = locate_long_edge(self.timber, self.edge)
        
        # Check that the face is adjacent to the edge
        # Long faces are RIGHT, FRONT, LEFT, BACK (not TOP or BOTTOM)
        LONG_FACES = {TimberFace.RIGHT, TimberFace.FRONT, TimberFace.LEFT, TimberFace.BACK}
        
        assert self.face in LONG_FACES, \
            f"Face must be a long face (RIGHT, FRONT, LEFT, BACK), got {self.face}"
        
        # Edge to faces mapping
        edge_to_faces = {
            TimberLongEdge.RIGHT_FRONT: (TimberFace.RIGHT, TimberFace.FRONT),
            TimberLongEdge.FRONT_LEFT: (TimberFace.FRONT, TimberFace.LEFT),
            TimberLongEdge.LEFT_BACK: (TimberFace.LEFT, TimberFace.BACK),
            TimberLongEdge.BACK_RIGHT: (TimberFace.BACK, TimberFace.RIGHT),
        }
        
        # The face must be one of the two faces that define the edge
        if self.edge not in edge_to_faces:
            raise ValueError(f"Unknown edge: {self.edge}")
        
        face1, face2 = edge_to_faces[self.edge]
        assert self.face == face1 or self.face == face2, \
            f"Face {self.face} is not adjacent to edge {self.edge}. Adjacent faces are {face1} and {face2}"
        
        # Calculate the direction to move on the face, parallel to the face plane
        # This is perpendicular to both the edge direction and the face normal
        # The "other" face defines this direction
        other_face = face1 if self.face == face2 else face2
        
        # The offset direction is the normal of the other face (parallel to our face plane)
        # Positive distance means moving in the direction of the other face's normal
        offset_direction = self.timber.get_face_direction_global(other_face)
        
        # Calculate the new line position by offsetting from the edge
        # Positive distance means moving in the offset direction (onto the face from the edge)
        new_point = edge_line.point + offset_direction * self.distance
        
        # Return a line parallel to the edge at the new position
        return Line(edge_line.direction, new_point)

@dataclass(frozen=True)
class PointFromCornerInFaceDirection(Marking):
    """
    Point on an edge in a given direction.
    """
    timber: Timber
    corner: TimberCorner
    face: TimberFace
    distance: Numeric

    def locate(self) -> Point:
        _corner_to_faces = {
            TimberCorner.BOT_RIGHT_FRONT: (TimberFace.BOTTOM, TimberFace.RIGHT, TimberFace.FRONT),
            TimberCorner.BOT_FRONT_LEFT:  (TimberFace.BOTTOM, TimberFace.FRONT, TimberFace.LEFT),
            TimberCorner.BOT_LEFT_BACK:   (TimberFace.BOTTOM, TimberFace.LEFT,  TimberFace.BACK),
            TimberCorner.BOT_BACK_RIGHT:  (TimberFace.BOTTOM, TimberFace.BACK,  TimberFace.RIGHT),
            TimberCorner.TOP_RIGHT_FRONT: (TimberFace.TOP,    TimberFace.RIGHT, TimberFace.FRONT),
            TimberCorner.TOP_FRONT_LEFT:  (TimberFace.TOP,    TimberFace.FRONT, TimberFace.LEFT),
            TimberCorner.TOP_LEFT_BACK:   (TimberFace.TOP,    TimberFace.LEFT,  TimberFace.BACK),
            TimberCorner.TOP_BACK_RIGHT:  (TimberFace.TOP,    TimberFace.BACK,  TimberFace.RIGHT),
        }
        corner_faces = _corner_to_faces[self.corner]
        assert self.face not in corner_faces, (
            f"Face {self.face} defines corner {self.corner} and points away from the timber. "
            f"Use the opposite face ({self.face.get_opposite_face()}) to point inward."
        )
        return Point(self.timber.get_corner_position_global(self.corner) + self.timber.get_face_direction_global(self.face) * self.distance)

@dataclass(frozen=True)
class DistanceFromCornerAlongEdge(Marking):
    """
    Distance along a timber edge from a reference end (corner) to an intersection
    or closest point. Positive means into the timber from the end.
    """
    distance: Numeric
    timber: PerfectTimberWithin
    edge: EdgeOrCenterline
    end: TimberReferenceEnd

    def locate(self) -> Point:
        edge_line = locate_edge(self.timber, self.edge)
        if self.end == TimberReferenceEnd.TOP:
            end_position = edge_line.point + edge_line.direction * (self.timber.length / Integer(2))
            into_direction = -self.timber.get_length_direction_global()
        else:
            end_position = edge_line.point - edge_line.direction * (self.timber.length / Integer(2))
            into_direction = self.timber.get_length_direction_global()
        return Point(end_position + into_direction * self.distance)

@dataclass(frozen=True)
class PlaneFromEdgeInDirection(Marking):
    """
    Plane with normal `direction` and `distance` from an edge in `direction`.
    """
    timber: PerfectTimberWithin
    edge: EdgeOrCenterline
    direction: Direction3D
    distance: Numeric
    
    def locate(self) -> Plane:
        return locate_plane_from_edge_in_direction(self.timber, self.edge, self.direction, self.distance)

class MarkingSpace(Marking):
    """
    Represents a space to mark in.
    """
    timber: Timber
    local_transform: Transform
    
    def locate(self) -> Space:
        return Space(self.timber.transform * self.local_transform)

# ============================================================================
# Helper Functions
# ============================================================================

def get_center_point_on_face_global(face: SomeTimberFace, timber: PerfectTimberWithin) -> V3:
    """
    Get the center point of a timber face in global coordinates.

    Args:
        face: The face to get the center of
        timber: The timber

    Returns:
        Center point of the face surface in global coordinates
    """
    timber_center = timber.get_bottom_position_global() + timber.get_length_direction_global() * timber.length / 2
    return timber_center + timber.get_face_direction_global(face) * timber.get_size_in_face_normal_axis(face) / 2


# DELETE ME
def get_point_on_face_global(face: SomeTimberFace, timber: PerfectTimberWithin) -> V3:
    """
    Get a point on the timber face surface (at the bottom-end of the timber).
    Useful for defining infinite planes through the face where the exact
    position along the face doesn't matter.

    For the actual center of the face, use get_center_point_on_face_global.
    """
    return get_center_point_on_face_global(face, timber)




def get_point_on_feature(feature: Union[UnsignedPlane, Plane, Line, Point, HalfPlane], timber: PerfectTimberWithin) -> V3:
    """
    Get a point on a feature.
    """

    if isinstance(feature, HalfPlane):
        return feature.point_on_line
    elif isinstance(feature, UnsignedPlane):
        return feature.point
    elif isinstance(feature, Plane):
        return feature.point
    elif isinstance(feature, Line):
        return feature.point
    elif isinstance(feature, Point):
        return feature.position

    raise ValueError(f"Unsupported feature type: {type(feature)}")


# ============================================================================
# Measuring functions
# ============================================================================


def locate_face(timber: PerfectTimberWithin, face: SomeTimberFace) -> Plane:
    """
    Measure a face on a timber, returning a Plane centered on the face pointing outward.

    The plane's normal points OUT of the timber (away from the timber's interior),
    and the plane's point is positioned at the center of the face surface.

    Args:
        timber: The timber to measure
        face: The face to measure

    Returns:
        Plane with normal pointing outward from the face and point at the face center

    Example:
        >>> plane = locate_face(timber, TimberFace.RIGHT)
        >>> # plane.normal points in +X direction (outward from RIGHT face)
        >>> # plane.point is at the center of the RIGHT face surface
    """
    # Get the face normal (pointing OUT of the timber)
    face_normal = timber.get_face_direction_global(face)
    
    # Get a point on the face surface (at the center)
    face_point = get_point_on_face_global(face, timber)
    
    return Plane(face_normal, face_point)


def locate_edge(timber: PerfectTimberWithin, edge: EdgeOrCenterline) -> Line:
    """
    Measure any edge or centerline on a timber, returning a Line along it.

    For TimberCenterline.CENTERLINE: direction = timber length direction, point at mid-length center.
    For TimberEdge values: uses canonical_line_from_corner to get the starting
    corner and direction face, then computes the global position and direction.

    Args:
        timber: The timber to measure
        edge: Which edge or centerline to measure

    Returns:
        Line representing the edge in global coordinates
    """
    if isinstance(edge, TimberCenterline):
        length_direction = timber.get_length_direction_global()
        center_position = timber.get_bottom_position_global() + length_direction * timber.length / 2
        return Line(length_direction, center_position)

    corner, direction_face = edge.canonical_line_from_corner()
    corner_position = timber.get_corner_position_global(corner)
    direction = timber.get_face_direction_global(direction_face)
    return Line(direction, corner_position)


def locate_long_edge(timber: PerfectTimberWithin, edge: TimberLongEdge) -> Line:
    """Measure a long edge on a timber. Thin wrapper around locate_edge."""
    return locate_edge(timber, TimberEdge(edge.value))


def locate_centerline(timber: PerfectTimberWithin) -> Line:
    """Measure the centerline of a timber. Thin wrapper around locate_edge."""
    return locate_edge(timber, TimberCenterline.CENTERLINE)

def locate_edge_on_face(timber: PerfectTimberWithin, edge: TimberLongEdge, face: TimberFace) -> HalfPlane:
    # TODO: Implement this function
    raise NotImplementedError("locate_edge_on_face is not yet implemented")

def locate_position_on_centerline_from_bottom(timber: PerfectTimberWithin, distance: Numeric) -> Point:
    """
    Measure a position at a specific point along the timber's centerline, measured from the bottom.

    Args:
        timber: The timber to measure on
        distance: Distance along the timber's length direction from the bottom position

    Returns:
        Point on the timber's centerline at the specified distance from bottom
    """
    position = timber.get_bottom_position_global() + timber.get_length_direction_global() * distance
    return Point(position)


def locate_position_on_centerline_from_top(timber: PerfectTimberWithin, distance: Numeric) -> Point:
    """
    Measure a position at a specific point along the timber's centerline, measured from the top.

    Args:
        timber: The timber to measure on
        distance: Distance along the timber's length direction from the top position

    Returns:
        Point on the timber's centerline at the specified distance from top
    """
    position = timber.get_bottom_position_global() + timber.get_length_direction_global() * (timber.length - distance)
    return Point(position)


def locate_bottom_center_position(timber: PerfectTimberWithin) -> Point:
    """
    Measure the position of the center of the bottom cross-section of the timber.

    Args:
        timber: The timber to measure on

    Returns:
        Point at the center of the bottom cross-section
    """
    return Point(timber.get_bottom_position_global())


def locate_top_center_position(timber: PerfectTimberWithin) -> Point:
    """
    Measure the position of the center of the top cross-section of the timber.

    Args:
        timber: The timber to measure on

    Returns:
        Point at the center of the top cross-section
    """
    position = timber.get_bottom_position_global() + timber.get_length_direction_global() * timber.length
    return Point(position)

def locate_into_face(distance: Numeric, face: SomeTimberFace, timber: PerfectTimberWithin) -> UnsignedPlane:
    """
    Measure a distance from a face on a timber.
    """

    # First pick any point on the face
    point_on_face = get_point_on_face_global(face, timber)

    # Measure INTO the face
    point_on_plane = point_on_face - timber.get_face_direction_global(face) * distance

    return UnsignedPlane(timber.get_face_direction_global(face), point_on_plane)

def locate_plane_from_edge_in_direction(timber: PerfectTimberWithin, edge: EdgeOrCenterline, direction: Direction3D, distance: Numeric = Integer(0)) -> Plane:
    """
    Return a Plane that is parallel to the given edge, has `direction` as its
    normal, and sits `distance` away from the edge in that direction.

    Args:
        timber: The timber whose edge to measure from
        edge: Which edge or centerline
        direction: Normal direction of the resulting plane
        distance: How far from the edge to place the plane (default 0 = through the edge)
    """
    edge_line = locate_edge(timber, edge)
    return Plane(normal=direction, point=edge_line.point + direction * distance)

def locate_plane_from_centerline_in_direction(timber: PerfectTimberWithin, direction: Direction3D) -> Plane:
    return locate_plane_from_edge_in_direction(timber, TimberCenterline.CENTERLINE, direction)

# ============================================================================
# Marking functions
# ============================================================================

def mark_distance_from_face_in_normal_direction(feature: Union[UnsignedPlane, Plane, Line, Point, HalfPlane], timber: PerfectTimberWithin, face: SomeTimberFace) -> DistanceFromFace:
    """
    Mark a feature onto a face on a timber.

    Returns a DistanceFromFace measurement representing the distance from the face to the feature, measured INTO the timber.
    Positive means the feature is inside the timber (deeper than the face surface).
    Negative means the feature is outside the timber (shallower than the face surface).

    This is the inverse of locate_into_face:
    If feature = locate_into_face(d, face, timber), then mark_distance_from_face_in_normal_direction(feature, timber, face).distance = d
    """

    if isinstance(feature, UnsignedPlane) or isinstance(feature, Plane) or isinstance(feature, HalfPlane):
        assert are_vectors_parallel(feature.normal, timber.get_face_direction_global(face)), \
            f"Feature must be parallel to the face. Feature {feature} is not parallel to face {face} on timber {timber}"
    elif isinstance(feature, Line):
        assert are_vectors_perpendicular(feature.direction, timber.get_face_direction_global(face)), \
            f"Feature must be parallel to the face. Feature {feature} is not parallel to face {face} on timber {timber}"

    # Pick a point on the feature
    feature_point = get_point_on_feature(feature, timber)

    # Project the feature point onto the face to get the signed distance
    # Get a reference point on the face surface
    face_point_global = get_point_on_face_global(face, timber)
    
    # Get the face normal (pointing OUT of the timber)
    face_direction_global = timber.get_face_direction_global(face)
    
    # Calculate signed distance: how far from the face is the point?
    # Positive if point is in the direction opposite to face_direction (inside timber)
    # Negative if point is in the direction of face_direction (outside timber)
    from kumiki.rule import safe_dot_product
    distance = safe_dot_product(face_direction_global, (face_point_global - feature_point))
    
    return DistanceFromFace(distance=distance, timber=timber, face=face)


def mark_distance_from_corner_along_edge_by_intersecting_plane(plane: Union[UnsignedPlane, Plane], timber: PerfectTimberWithin, edge: Union[TimberLongEdge, EdgeOrCenterline], end: TimberReferenceEnd) -> DistanceFromCornerAlongEdge:
    """
    Mark onto an edge by intersecting a plane, returning a DistanceFromCornerAlongEdge.

    Args:
        plane: the plane to intersect with
        timber: the timber whose edge we're intersecting
        edge: the edge to intersect with (TimberLongEdge, TimberEdge, or TimberCenterline)
        end: the end of the timber to mark from

    Returns:
        DistanceFromCornerAlongEdge with the signed distance from the end to the
        intersection. Positive means into the timber from the end.
    """
    assert isinstance(end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(end).__name__}"
    if isinstance(edge, TimberLongEdge):
        edge_line = locate_edge(timber, TimberEdge(edge.value))
    else:
        edge_line = locate_edge(timber, edge)

    if end == TimberReferenceEnd.TOP:
        end_position = edge_line.point + edge_line.direction * (timber.length / Integer(2))
        into_timber_direction = -timber.get_length_direction_global()
    else:  # BOTTOM
        end_position = edge_line.point - edge_line.direction * (timber.length / Integer(2))
        into_timber_direction = timber.get_length_direction_global()

    numerator = safe_dot_product(plane.normal, (plane.point - end_position))
    denominator = safe_dot_product(plane.normal, into_timber_direction)

    if zero_test(denominator):
        raise ValueError(f"Edge is parallel to plane - no intersection exists")

    resolved_edge: EdgeOrCenterline = TimberEdge(edge.value) if isinstance(edge, TimberLongEdge) else edge
    return DistanceFromCornerAlongEdge(
        distance=numerator / denominator,
        timber=timber,
        edge=resolved_edge,
        end=end,
    )


def mark_distance_from_corner_along_edge_by_finding_closest_point_on_line(line: Line, timber: PerfectTimberWithin, edge: Union[TimberLongEdge, EdgeOrCenterline], end: TimberReferenceEnd) -> DistanceFromCornerAlongEdge:
    """
    Mark onto an edge by finding the closest point to a line, returning a DistanceFromCornerAlongEdge.

    Args:
        line: The line feature to mark from
        timber: The timber whose edge we're marking to
        edge: The edge to mark to (TimberLongEdge, TimberEdge, or TimberCenterline)
        end: Which end of the timber to mark from

    Returns:
        DistanceFromCornerAlongEdge with the signed distance from the end to the closest point.
    """
    assert isinstance(end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(end).__name__}"
    if isinstance(edge, TimberLongEdge):
        edge_line = locate_edge(timber, TimberEdge(edge.value))
    else:
        edge_line = locate_edge(timber, edge)

    if are_vectors_parallel(line.direction, edge_line.direction):
        raise ValueError(f"Lines are parallel - no intersection exists")

    if end == TimberReferenceEnd.TOP:
        edge_end_position = edge_line.point + edge_line.direction * (timber.length / Integer(2))
    else:  # BOTTOM
        edge_end_position = edge_line.point - edge_line.direction * (timber.length / Integer(2))
    
    # Solve for closest points on two 3D lines using the standard formula
    # Line 1 (given line): line.point + s * line.direction
    # Line 2 (edge): edge_end_position + t * edge_line.direction
    # We need to find s and t such that the connecting vector is perpendicular to both directions
    
    w = line.point - edge_end_position  # Vector between starting points
    
    a = safe_dot_product(line.direction, line.direction)  # Should be 1 for normalized directions
    b = safe_dot_product(line.direction, edge_line.direction)
    c = safe_dot_product(edge_line.direction, edge_line.direction)  # Should be 1 for normalized directions
    d = safe_dot_product(w, line.direction)
    e = safe_dot_product(w, edge_line.direction)
    
    denominator = a * c - b * b
    
    if zero_test(denominator):
        t = Rational(0)
    else:
        t = (a * e - b * d) / denominator

    resolved_edge: EdgeOrCenterline = TimberEdge(edge.value) if isinstance(edge, TimberLongEdge) else edge
    return DistanceFromCornerAlongEdge(
        distance=t,
        timber=timber,
        edge=resolved_edge,
        end=end,
    )

# TODO DELETE?
def mark_distance_from_end_along_centerline(feature: Union[UnsignedPlane, Plane, Line, Point, HalfPlane], timber: PerfectTimberWithin, end: TimberReferenceEnd = TimberReferenceEnd.BOTTOM) -> DistanceFromPointIntoFace:
    """
    Mark a feature onto the centerline of a timber.

    Returns a DistanceFromPointIntoFace measurement representing the distance from the specified end of the timber
    to the intersection/closest point on the centerline.

    Args:
        feature: The feature to mark (Plane, Line, Point, etc.)
        timber: The timber whose centerline we're marking to
        end: Which end of the timber to mark from (defaults to BOTTOM)

    Returns:
        DistanceFromPointIntoFace with distance from the specified end to where the feature intersects/is closest
        to the centerline. Positive means into the timber from the end. The point is set to the end's
        centerline position.
    """
    assert isinstance(end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(end).__name__}"
    if isinstance(feature, UnsignedPlane) or isinstance(feature, Plane):
        distance = mark_distance_from_corner_along_edge_by_intersecting_plane(feature, timber, TimberCenterline.CENTERLINE, end).distance
    elif isinstance(feature, Line):
        distance = mark_distance_from_corner_along_edge_by_finding_closest_point_on_line(feature, timber, TimberCenterline.CENTERLINE, end).distance
    else:
        assert False, f"Not implemented for feature type {type(feature)}"

    # Get the reference end's centerline position as the reference point
    centerline = locate_centerline(timber)
    if end == TimberReferenceEnd.BOTTOM:
        end_centerline_position = timber.get_bottom_position_global()
        reference_face = TimberFace.BOTTOM
    else:  # TOP
        end_centerline_position = timber.get_bottom_position_global() + timber.get_length_direction_global() * timber.length
        reference_face = TimberFace.TOP
    
    return DistanceFromPointIntoFace(
        distance=distance,
        timber=timber,
        face=reference_face,
        point=end_centerline_position
    )


def mark_plane_from_edge_in_direction(plane: Union[UnsignedPlane, Plane, HalfPlane], timber: PerfectTimberWithin, edge: EdgeOrCenterline) -> PlaneFromEdgeInDirection:
    """
    Mark a plane onto a timber edge, returning the direction and signed distance
    from the edge to the plane.

    This is the inverse of locate_plane_from_edge_in_direction:
    if p = locate_plane_from_edge_in_direction(timber, edge, dir, dist),
    then mark_plane_from_edge_in_direction(p, timber, edge) returns (dir, dist).

    Args:
        plane: The plane to mark (its normal becomes the direction)
        timber: The timber whose edge we're measuring from
        edge: Which edge to measure from
    """
    edge_line = locate_edge(timber, edge)
    direction = plane.normal
    plane_point = plane.point_on_line if isinstance(plane, HalfPlane) else plane.point
    distance = safe_dot_product(direction, plane_point - edge_line.point)
    return PlaneFromEdgeInDirection(
        timber=timber,
        edge=edge,
        direction=direction,
        distance=distance,
    )