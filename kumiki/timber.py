"""
Kumiki - Timber types, enums, constants, and core classes
Contains all core data structures and type definitions for the timber framing system
"""

from sympy import Matrix, Abs, Rational, Integer, Expr, sqrt, simplify, Min, Max
from .rule import *
from .footprint import *
from .cutcsg import *
from .ticket import Ticket, TimberTicket, AccessoryTicket, JointTicket
from enum import Enum
from typing import List, Optional, Tuple, Union, TYPE_CHECKING, Dict, Literal, final, cast, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import warnings

# Aliases for backwards compatibility
CSGUnion = SolidUnion
CSGDifference = Difference

# ============================================================================
# Constants
# ============================================================================

# Epsilon constants are now imported from rule module

# Thresholds for geometric decisions
OFFSET_TEST_POINT = Rational(1, 1000)  # Small offset (0.001) for testing inward direction on footprint

# ============================================================================
# Timber Feature Enums
# ============================================================================


class TimberFeature(Enum):
    TOP_FACE = 1
    BOTTOM_FACE = 2
    RIGHT_FACE = 3
    FRONT_FACE = 4
    LEFT_FACE = 5
    BACK_FACE = 6
    CENTERLINE = 7
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
    
    def end(self) -> 'TimberReferenceEnd':
        """Convert to TimberReferenceEnd. Values 1-2 map to ends."""
        if self.value not in range(1, 3):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberReferenceEnd. Only values 1-2 are valid ends.")
        return TimberReferenceEnd(self.value)
    
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
        """Convert to TimberCenterline. Value 7 maps to CENTERLINE."""
        if self.value != 7:
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberCenterline. Only value 7 is valid.")
        return TimberCenterline(self.value)
    
    def long_edge(self) -> 'TimberLongEdge':
        """Convert to TimberLongEdge. Values 8-11 map to long edges."""
        if self.value not in range(8, 12):
            raise ValueError(f"Cannot convert {self} (value={self.value}) to TimberLongEdge. Only values 8-11 are valid long edges.")
        return TimberLongEdge(self.value)

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
            return create_v3(Integer(0), Integer(0), Integer(1))
        elif self == TimberFace.BOTTOM:
            return create_v3(Integer(0), Integer(0), Integer(-1))
        elif self == TimberFace.RIGHT:
            return create_v3(Integer(1), Integer(0), Integer(0))
        elif self == TimberFace.LEFT:
            return create_v3(Integer(-1), Integer(0), Integer(0))
        elif self == TimberFace.FRONT:
            return create_v3(Integer(0), Integer(1), Integer(0))
        else:  # BACK
            return create_v3(Integer(0), Integer(-1), Integer(0))
    
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

class TimberReferenceEnd(Enum):
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
    CENTERLINE = 7

    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)

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

    
class TimberLongEdge(Enum):
    RIGHT_FRONT = 8
    FRONT_LEFT = 9
    LEFT_BACK = 10
    BACK_RIGHT = 11
    
    @property
    def to(self) -> TimberFeature:
        """Convert to TimberFeature for further conversions."""
        return TimberFeature(self.value)


# ============================================================================
# Type Aliases
# ============================================================================

# Union type for face-like enums (TimberFace, TimberReferenceEnd, or TimberLongFace)
SomeTimberFace = Union[TimberFace, TimberReferenceEnd, TimberLongFace]


# ============================================================================
# Core Classes
#============================================================================


def _ensure_ticket(ticket: Optional[Union[TimberTicket, str]]) -> TimberTicket:
    """Convert a ticket parameter to a Ticket object.
    
    Args:
        ticket: Either a TimberTicket object, a string name, or None
        
    Returns:
        TimberTicket object (creates one with default name if None provided)
    """
    if ticket is None:
        return TimberTicket()
    elif isinstance(ticket, str):
        return TimberTicket(name=ticket)
    else:
        return ticket


def compute_timber_orientation(length_direction: Direction3D, width_direction: Direction3D) -> Orientation:
    """Compute the orientation matrix from length and width directions
    
    Args:
        length_direction: Direction vector for the length axis as 3D vector, the +length direction is the +Z direction
        width_direction: Direction vector for the width axis as 3D vector, the +width direction is the +X direction
        
    Returns:
        Orientation object representing the timber's orientation in 3D space
    """
    # Normalize the length direction first (this will be our primary axis)
    length_norm = normalize_vector(length_direction)
    
    # Orthogonalize face direction relative to length direction using Gram-Schmidt
    face_input = normalize_vector(width_direction)
    
    # Project face_input onto length_norm and subtract to get orthogonal component
    projection = length_norm * (face_input.dot(length_norm))
    face_orthogonal = face_input - projection
    
    # Check if face_orthogonal is too small (vectors were nearly parallel)
    if zero_test(safe_norm(face_orthogonal)):
        # Choose an arbitrary orthogonal direction
        # Find a vector that's not parallel to length_norm
        if Abs(length_norm[0]) < Rational(9, 10):  # Threshold comparison
            temp_vector = create_v3(Integer(1), Integer(0), Integer(0))
        else:
            temp_vector = create_v3(Integer(0), Integer(1), Integer(0))
        
        # Project and orthogonalize
        projection = length_norm * (temp_vector.dot(length_norm))
        face_orthogonal = temp_vector - projection
    
    # Normalize the orthogonalized face direction
    face_norm = normalize_vector(face_orthogonal)
    
    # Cross product to get the third axis (guaranteed to be orthogonal)
    cross_result = cross_product(length_norm, face_norm)
    height_norm = normalize_vector(cross_result)
    
    # Create rotation matrix [face_norm, height_norm, length_norm]
    rotation_matrix = Matrix([
        [face_norm[0], height_norm[0], length_norm[0]],
        [face_norm[1], height_norm[1], length_norm[1]],
        [face_norm[2], height_norm[2], length_norm[2]]
    ])
    
    # Convert to Orientation
    return Orientation(rotation_matrix)


# TODO rename to create_timber (or maybe hew lolololol) + add defaults
def timber_from_directions(length: Numeric, size: V2, bottom_position: V3,
                          length_direction: Direction3D, width_direction: Direction3D,
                          ticket: Optional[Union[TimberTicket, str]] = None) -> 'Timber':
    """Factory function to create a Timber with computed orientation from direction vectors
    
    This is the main way to construct Timber instances. It takes direction vectors
    and computes the proper orientation matrix automatically.
    
    Args:
        length: Length of the timber
        size: Cross-sectional size (width, height) as 2D vector, width is the X dimension (left to right), height is the Y dimension (front to back)
        bottom_position: Position of the bottom point (center of cross-section) as 3D vector
        length_direction: Direction vector for the length axis as 3D vector, the +length direction is the +Z direction
        width_direction: Direction vector for the width axis as 3D vector, the +width direction is the +X direction
        ticket: Optional ticket for this timber (can be TimberTicket object or string name, used for rendering/debugging)
        
    Returns:
        Timber instance with computed orientation
    """
    orientation = compute_timber_orientation(length_direction, width_direction)
    transform = Transform(position=bottom_position, orientation=orientation)
    return Timber(length=length, size=size, transform=transform, ticket=_ensure_ticket(ticket))


@dataclass(frozen=True)
class PerfectTimberWithin(ABC):
    """Base class for all timber types in the timber framing system (immutable)
    
    This is an abstract base class (ABC) to prevent direct instantiation.
    All timbers contain a perfect rectangular timber within their nominal bounding box.
    
    Note: Use timber_from_directions() factory function to construct timber instances from
    length_direction and width_direction vectors. Subclasses are frozen to ensure immutability
    after construction.
    
    Alternatively, if you already have a Transform object, you can construct
    a timber directly by passing: Timber(length, size, transform, ticket)
    
    Attributes:
        length: Length of the timber along its centerline axis
        size: Cross-sectional size (width, height) of the nominal bounding box
        transform: Position and orientation in global coordinates
        ticket: Ticket for this timber (used for rendering/debugging)
    """
    length: Numeric
    size: V2
    transform: Transform
    ticket: TimberTicket = field(default_factory=TimberTicket)

    def __post_init__(self):
        if self.ticket.reference_faces is not None:
            self._validate_reference_faces()

    def _validate_reference_faces(self):
        """Assert that each reference face is a valid long face and that
        the nominal half-size matches the PTW half-size on that face
        (i.e. the nominal face plane and PTW face plane are coincident)."""
        ref_faces = self.ticket.reference_faces
        assert ref_faces is not None
        valid_names = {f.name for f in TimberLongFace}
        ptw_w_half = self.size[0] / Integer(2)
        ptw_h_half = self.size[1] / Integer(2)
        width_halves, height_halves = self.get_nominal_half_sizes()

        # TODO consider allowing top/bot ends?
        _face_to_nominal_and_ptw = {
            "RIGHT": (width_halves[0], ptw_w_half),
            "LEFT":  (width_halves[1], ptw_w_half),
            "FRONT": (height_halves[0], ptw_h_half),
            "BACK":  (height_halves[1], ptw_h_half),
        }
        for face_name in ref_faces:
            assert face_name in valid_names, (
                f"reference_face '{face_name}' is not a valid TimberLongFace "
                f"(expected one of {sorted(valid_names)})"
            )
            nominal_half, ptw_half = _face_to_nominal_and_ptw[face_name]
            assert equality_test(nominal_half, ptw_half), (
                f"Reference face {face_name} on timber '{self.ticket.name}' is not coincident: "
                f"nominal half-size ({nominal_half}) != PTW half-size ({ptw_half})"
            )

    @property
    def orientation(self) -> Orientation:
        """Get the orientation from the transform."""
        return self.transform.orientation

    def get_orientation_global(self) -> Orientation:
        """Get the orientation from the transform."""
        return self.orientation

    def get_bottom_position_global(self) -> V3:
        """Get the bottom position (center of bottom cross-section) in global coordinates from the transform."""
        return self.transform.position
    
    
    def get_length_direction_global(self) -> Direction3D:
        """Get the length direction vector in global coordinates from the orientation matrix"""
        # Length direction is the 3rd column (index 2) of the rotation matrix
        # The +length direction is the +Z direction
        return Matrix([
            self.orientation.matrix[0, 2],
            self.orientation.matrix[1, 2],
            self.orientation.matrix[2, 2]
        ])
    
    def get_width_direction_global(self) -> Direction3D:
        """Get the width direction vector in global coordinates from the orientation matrix"""
        # Width direction is the 1st column (index 0) of the rotation matrix
        # The +width direction is the +X direction
        return Matrix([
            self.orientation.matrix[0, 0],
            self.orientation.matrix[1, 0],
            self.orientation.matrix[2, 0]
        ])
    
    def get_height_direction_global(self) -> Direction3D:
        """Get the height direction vector in global coordinates from the orientation matrix"""
        # Height direction is the 2nd column (index 1) of the rotation matrix
        # The +height direction is the +Y direction
        return Matrix([
            self.orientation.matrix[0, 1],
            self.orientation.matrix[1, 1],
            self.orientation.matrix[2, 1]
        ])
    def get_face_direction_global(self, face: SomeTimberFace) -> Direction3D:
        """
        Get the world direction vector for a specific face of this timber.
        
        Args:
            face: The face to get the direction for (can be TimberFace, TimberEnd, or TimberLongFace)
            
        Returns:
            Direction vector pointing outward from the specified face in world coordinates
        """
        # Convert to TimberFace
        face = face.to.face()
        
        if face == TimberFace.TOP:
            return self.get_length_direction_global()
        elif face == TimberFace.BOTTOM:
            return -self.get_length_direction_global()
        elif face == TimberFace.RIGHT:
            return self.get_width_direction_global()
        elif face == TimberFace.LEFT:
            return -self.get_width_direction_global()
        elif face == TimberFace.FRONT:
            return self.get_height_direction_global()
        else:  # BACK
            return -self.get_height_direction_global()

    def get_corner_position_global(self, corner: TimberCorner) -> V3:
        """Get the position of a corner in global coordinates."""
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
        faces = _corner_to_faces[corner]
        timber_center = self.get_bottom_position_global() + self.get_length_direction_global() * self.length / 2
        position = timber_center
        for face in faces:
            position = position + self.get_face_direction_global(face) * self.get_size_in_face_normal_axis(face) / 2
        return position

    def get_size_index_in_long_face_normal_axis(self, face: TimberLongFace) -> int:
        """
        Get the index of the size in the direction normal to the specified face.
        """
        assert isinstance(face, TimberLongFace), f"expected TimberLongFace, got {type(face).__name__}"
        if face == TimberLongFace.RIGHT or face == TimberLongFace.LEFT:
            return 0
        elif face == TimberLongFace.FRONT or face == TimberLongFace.BACK:
            return 1
        else:
            raise ValueError(f"Unknown face: {face}")

    def get_size_in_face_normal_axis(self, face: SomeTimberFace) -> Numeric:
        """
        Get the size of the timber in the direction normal to the specified face.
        
        Args:
            face: The face to get the size for (can be TimberFace, TimberEnd, or TimberLongFace)
        """
        # Convert to TimberFace
        face = face.to.face()
        
        if face == TimberFace.TOP or face == TimberFace.BOTTOM:
            return self.length
        elif face == TimberFace.RIGHT or face == TimberFace.LEFT:
            return self.size[0]
        else:  # FRONT or BACK
            return self.size[1]
    
    def get_nominal_size_in_face_normal_axis(self, face: SomeTimberFace) -> Numeric:
        """
        Get the full nominal size of the timber in the direction normal to the specified face.
        
        For long faces this returns the sum of the two half-sizes (e.g. right + left for
        RIGHT or LEFT). For end faces (TOP/BOTTOM) this returns the length.
        
        Args:
            face: The face to get the size for (can be TimberFace, TimberEnd, or TimberLongFace)
        """
        face = face.to.face()
        
        if face == TimberFace.TOP or face == TimberFace.BOTTOM:
            return self.length
        
        width_halves, height_halves = self.get_nominal_half_sizes()
        if face == TimberFace.RIGHT or face == TimberFace.LEFT:
            return width_halves[0] + width_halves[1]
        else:  # FRONT or BACK
            return height_halves[0] + height_halves[1]

    def get_half_nominal_size_in_face_normal_axis(self, face: SomeTimberFace) -> Numeric:
        """
        Get the nominal half-size of the timber from the centerline to the specified face.
        
        Args:
            face: A long face (RIGHT, LEFT, FRONT, or BACK). TOP/BOTTOM will raise ValueError
                  since length has no asymmetry concept.
        
        Returns:
            The half-size from centerline to the specified face.
        """
        face = face.to.face()
        width_halves, height_halves = self.get_nominal_half_sizes()
        
        if face == TimberFace.RIGHT:
            return width_halves[0]
        elif face == TimberFace.LEFT:
            return width_halves[1]
        elif face == TimberFace.FRONT:
            return height_halves[0]
        elif face == TimberFace.BACK:
            return height_halves[1]
        else:
            raise ValueError(f"get_half_nominal_size_in_face_normal_axis does not support end faces (got {face})")

    def get_size_in_direction_2d(self, direction: V2) -> Numeric:
        """
        Get the size of the timber's cross-section measured along an arbitrary 2D direction.
        
        The direction is in the timber's local cross-section plane where x is the width
        axis and y is the height axis. Returns the total extent (support width) of the
        rectangular cross-section projected onto that direction.
        
        For axis-aligned directions this matches get_size_in_face_normal_axis.
        
        Args:
            direction: A 2D direction vector (x=width, y=height) in local cross-section space.
                       Does not need to be normalized.
        
        Returns:
            The size of the cross-section measured along the given direction.
        """
        d = normalize_vector(direction)
        return self.size[0] * Abs(d[0]) + self.size[1] * Abs(d[1])

    def get_size_in_direction_3d(self, direction: Direction3D) -> Numeric:
        """
        Get the size of the timber measured along an arbitrary 3D direction in global space.
        
        Transforms the direction into the timber's local frame and computes the total
        extent (support width) of the rectangular prism projected onto that direction.
        
        For axis-aligned directions this matches get_size_in_face_normal_axis.
        
        Args:
            direction: A 3D direction vector in global coordinates.
                       Does not need to be normalized.
        
        Returns:
            The size of the timber measured along the given direction.
        """
        d_global = normalize_vector(direction)
        # Rotate to local frame (transpose of rotation matrix, no translation for directions)
        d_local = safe_transform_vector(self.orientation.matrix.T, d_global)
        return self.size[0] * Abs(d_local[0]) + self.size[1] * Abs(d_local[1]) + self.length * Abs(d_local[2])

    def _get_closest_oriented_face_from_faces(self, faces: List[TimberFace], target_direction: Direction3D) -> TimberFace:
        """Return the face in `faces` whose outward normal best aligns with `target_direction` (max dot product)."""
        from kumiki.rule import numeric_dot_product
        best_face = faces[0]
        best_alignment = numeric_dot_product(target_direction, self.get_face_direction_global(faces[0]))
        for face in faces[1:]:
            alignment = numeric_dot_product(target_direction, self.get_face_direction_global(face))
            if alignment > best_alignment:
                best_alignment = alignment
                best_face = face
        return best_face

    def get_closest_oriented_face_from_global_direction(self, target_direction: Direction3D) -> TimberFace:
        """
        Find which face of this timber best aligns with the target direction.

        The target_direction should point "outwards" from the desired face (not into it).

        Args:
            target_direction: Direction vector to match against

        Returns:
            The TimberFace that best aligns with the target direction
        """
        faces = [
            TimberFace.TOP, TimberFace.BOTTOM, TimberFace.RIGHT,
            TimberFace.LEFT, TimberFace.FRONT, TimberFace.BACK,
        ]
        return self._get_closest_oriented_face_from_faces(faces, target_direction)

    def get_closest_oriented_long_face_from_global_direction(self, target_direction: Direction3D) -> TimberLongFace:
        """
        Find which long face of this timber best aligns with the target direction.

        The target_direction should point "outwards" from the desired face (not into it).

        Args:
            target_direction: Direction vector to match against

        Returns:
            The TimberLongFace that best aligns with the target direction
        """
        faces = [TimberFace.RIGHT, TimberFace.LEFT, TimberFace.FRONT, TimberFace.BACK]
        return self._get_closest_oriented_face_from_faces(faces, target_direction).to.long_face()

    def get_closest_oriented_end_face_from_global_direction(self, target_direction: Direction3D) -> TimberReferenceEnd:
        """
        Find which end face of this timber best aligns with the target direction.

        The target_direction should point "outwards" from the desired end face (not into it).

        Returns:
            The TimberReferenceEnd that best aligns with the target direction
        """
        faces = [TimberFace.TOP, TimberFace.BOTTOM]
        return self._get_closest_oriented_face_from_faces(faces, target_direction).to.end()
    
    # UNTESTED
    def get_inside_face_from_footprint(self, footprint: Footprint) -> TimberFace:
        """
        Get the inside face of this timber relative to the footprint.
        
        This method finds which face of the timber is oriented toward the interior
        of the footprint by:
        1. Finding the nearest boundary of the footprint to the timber's centerline
        2. Getting the inward normal of that boundary
        3. Finding which timber face best aligns with that inward direction
        
        Args:
            footprint: The footprint to determine inside/outside orientation
            
        Returns:
            The TimberFace that points toward the inside of the footprint
        """
        from .measuring import locate_top_center_position
        
        # Project timber's centerline onto XY plane for footprint comparison
        bottom_2d = create_v2(self.get_bottom_position_global()[0], self.get_bottom_position_global()[1])
        top_position = locate_top_center_position(self).position
        top_2d = create_v2(top_position[0], top_position[1])
        
        # Find nearest boundary to timber's centerline
        boundary_idx, boundary_side, distance = footprint.nearest_boundary_from_line(bottom_2d, top_2d)
        
        # Get the inward normal of that boundary
        inward_normal = footprint.get_inward_normal(boundary_idx)
        
        # Find which face of the timber aligns with the inward direction
        return self.get_closest_oriented_face_from_global_direction(inward_normal)

    # UNTESTED
    def get_outside_face_from_footprint(self, footprint: Footprint) -> TimberFace:
        """
        Get the outside face of this timber relative to the footprint.
        
        This method finds which face of the timber is oriented toward the exterior
        of the footprint by:
        1. Finding the nearest boundary of the footprint to the timber's centerline
        2. Getting the inward normal of that boundary
        3. Finding which timber face best aligns with the opposite (outward) direction
        
        Args:
            footprint: The footprint to determine inside/outside orientation
            
        Returns:
            The TimberFace that points toward the outside of the footprint
        """
        from .measuring import locate_top_center_position
        
        # Project timber's centerline onto XY plane for footprint comparison
        bottom_2d = create_v2(self.get_bottom_position_global()[0], self.get_bottom_position_global()[1])
        top_position = locate_top_center_position(self).position
        top_2d = create_v2(top_position[0], top_position[1])
        
        # Find nearest boundary to timber's centerline
        boundary_idx, boundary_side, distance = footprint.nearest_boundary_from_line(bottom_2d, top_2d)
        
        # Get the inward normal of that boundary
        inward_normal = footprint.get_inward_normal(boundary_idx)
        
        # Find which face of the timber aligns with the outward direction (negative of inward)
        outward_normal = -inward_normal
        return self.get_closest_oriented_face_from_global_direction(outward_normal)
    
    def get_transform_matrix(self) -> Matrix:
        """Get the 4x4 transformation matrix for this timber"""
        # Create 4x4 transformation matrix
        transform = Matrix([
            [self.orientation.matrix[0,0], self.orientation.matrix[0,1], self.orientation.matrix[0,2], self.get_bottom_position_global()[0]],
            [self.orientation.matrix[1,0], self.orientation.matrix[1,1], self.orientation.matrix[1,2], self.get_bottom_position_global()[1]],
            [self.orientation.matrix[2,0], self.orientation.matrix[2,1], self.orientation.matrix[2,2], self.get_bottom_position_global()[2]],
            [0, 0, 0, 1]
        ])
        return transform


    # TODO DELETE this is duplicated in timber_shavings.py which you should also delete and replce with smothenig in measuring
    def project_global_point_onto_timber_face_global(self, global_point: V3, face: SomeTimberFace) -> V3:
        """
        Project a point from global coordinates onto the timber's face and return result in global coordinates.
        
        Args:
            global_point: The point to project in global coordinates (3x1 Matrix)
            face: The face to project onto (can be TimberFace, TimberReferenceEnd, or TimberLongFace)
        """
        # Convert to TimberFace
        face = face.to.face()
        
        # Convert global point to local coordinates
        local_point = self.transform.global_to_local(global_point)
        
        # project the 0,0 point onto the face
        face_zero_local = face.get_direction() * self.get_size_in_face_normal_axis(face) / 2
        local_point_face_component = (local_point-face_zero_local).dot(face.get_direction()) * face.get_direction()
        local_point_projected = local_point - local_point_face_component
        return self.transform.local_to_global(local_point_projected)
    
    @final
    def get_perfect_size(self) -> V2:
        """
        Returns the perfect cross sectional size of the timber.
        
        The perfect size is the cross sectional size of the perfect timber within.
        """
        return self.size

    def can_be_extended_for_joints(self) -> bool:
        """
        Returns True if the timber can be extended when cutting joints.
        
        Returns:
            True if the timber can be extended when cutting joints.
        """
        return True
    
    
    @abstractmethod
    def get_nominal_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the nominal half-sizes of the timber measured from the centerline.
        
        The nominal bounding box is defined by four half-sizes measured from the
        centerline in each direction. This allows the nominal timber to be non-coaxial
        with the perfect timber within (useful for square rule layout).
        
        Returns:
            Tuple of two V2s:
              - width_halves: V2(right_half, left_half) — half-sizes in the width dimension
              - height_halves: V2(front_half, back_half) — half-sizes in the height dimension
        """
        pass
    
    def get_perfect_timber_within_CSG_local(self) -> RectangularPrism:
        """
        Returns the perfect rectangular prism CSG in local coordinates.
        
        This represents the nominal bounding box as a CSG object. All timber types
        have a perfect rectangular prism that bounds their actual geometry.
        
        Returns:
            RectangularPrism in local coordinates (relative to timber's bottom position)
        """
        return RectangularPrism(
            size=self.size,
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=self.length,
            named_features=_timber_face_tags(),
        )
    
    def get_actual_csg_local(self) -> CutCSG:
        """
        Returns the actual CSG geometry for this timber.
        
        For the base PerfectTimberWithin class, this returns the perfect rectangular
        prism. Subclasses override this to return different geometries (cylinder, mesh, etc.).
        
        Returns:
            CutCSG representing the actual geometry in local coordinates
        """
        return self.get_perfect_timber_within_CSG_local()

    def get_extended_actual_csg_local(self, extend_bot: bool, extend_top: bool) -> CutCSG:
        """
        Returns the actual CSG geometry extended to infinity at specified ends.
        
        For the base PerfectTimberWithin class, this returns a rectangular prism
        using the perfect timber within size, optionally extended to infinity.
        
        Args:
            extend_bot: If True, extend to -infinity at bottom (z=0)
            extend_top: If True, extend to +infinity at top (z=length)
            
        Returns:
            CutCSG representing the extended geometry in local coordinates
        """
        return _create_extended_rectangular_prism(
            size=self.get_perfect_size(),
            length=self.length,
            extend_bot=extend_bot,
            extend_top=extend_top
        )
    
    def is_perfect_timber(self) -> bool:
        """
        Check if this timber's actual geometry matches its nominal bounding box.
        
        Returns True when the nominal half-sizes are symmetric and equal to half
        the perfect timber within size.
        
        Returns:
            True if the timber is a perfect timber, False otherwise
        """
        width_halves, height_halves = self.get_nominal_half_sizes()
        w_half = self.size[0] / Integer(2)
        h_half = self.size[1] / Integer(2)
        return (equality_test(width_halves[0], w_half) and
                equality_test(width_halves[1], w_half) and
                equality_test(height_halves[0], h_half) and
                equality_test(height_halves[1], h_half))


# TODO HomeDepotTimber or like BoxTimber or NominalTimber, sticktimber and dressedtimber are also cute names?
@dataclass(frozen=True)
class Timber(PerfectTimberWithin):
    """Perfect rectangular timber (the current default timber type)
    
    This is a perfect rectangular prism where the nominal bounding box
    exactly matches the actual geometry. This is the most common timber type
    used in timber framing.
    
    Inherits all attributes and methods from PerfectTimberWithin:
        - length: Length of the timber
        - size: Cross-sectional size (width, height)
        - transform: Position and orientation
        - name: Optional name
    """
    nominal_half_sizes: Optional[Tuple[V2, V2]] = None  # Optional asymmetric half-sizes from centerline
    
    def get_nominal_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the nominal half-sizes of the timber.
        
        If nominal_half_sizes is set, returns that. Otherwise returns symmetric
        half-sizes derived from the perfect timber within size.
        
        Returns:
            Tuple of (V2(right_half, left_half), V2(front_half, back_half))
        """
        if self.nominal_half_sizes is not None:
            return self.nominal_half_sizes
        w_half = self.size[0] / Integer(2)
        h_half = self.size[1] / Integer(2)
        return (create_v2(w_half, w_half), create_v2(h_half, h_half))
    
    def _nominal_csg_size_and_offset(self) -> Tuple[V2, V3]:
        """Compute the total nominal cross-section size and the local offset from the centerline."""
        width_halves, height_halves = self.get_nominal_half_sizes()
        total_w = width_halves[0] + width_halves[1]
        total_h = height_halves[0] + height_halves[1]
        # Offset: positive means shift toward RIGHT / FRONT
        offset_x = (width_halves[0] - width_halves[1]) / Integer(2)
        offset_y = (height_halves[0] - height_halves[1]) / Integer(2)
        return (create_v2(total_w, total_h),
                create_v3(offset_x, offset_y, Integer(0)))
    
    def get_actual_csg_local(self) -> CutCSG:
        """
        Returns the actual CSG geometry for this timber.
        
        For Timber, this returns a rectangular prism using the nominal half-sizes,
        offset from the centerline when the half-sizes are asymmetric.
        
        Returns:
            RectangularPrism representing the actual geometry in local coordinates
        """
        from .cutcsg import RectangularPrism
        nominal_size, offset = self._nominal_csg_size_and_offset()
        return RectangularPrism(
            size=nominal_size,
            transform=Transform(position=offset, orientation=Orientation.identity()),
            start_distance=Integer(0),
            end_distance=self.length,
            named_features=_timber_face_tags(),
        )
    
    def get_extended_actual_csg_local(self, extend_bot: bool, extend_top: bool) -> CutCSG:
        """
        Returns the actual CSG geometry extended to infinity at specified ends.
        
        For Timber, this returns a rectangular prism using the nominal half-sizes,
        offset from the centerline when the half-sizes are asymmetric.
        
        Args:
            extend_bot: If True, extend to -infinity at bottom (z=0)
            extend_top: If True, extend to +infinity at top (z=length)
            
        Returns:
            CutCSG representing the extended geometry in local coordinates
        """
        from .cutcsg import RectangularPrism
        nominal_size, offset = self._nominal_csg_size_and_offset()
        return RectangularPrism(
            size=nominal_size,
            transform=Transform(position=offset, orientation=Orientation.identity()),
            start_distance=None if extend_bot else Integer(0),
            end_distance=None if extend_top else self.length,
            named_features=_timber_face_tags(),
        )
    

@dataclass(frozen=True)
class Board(PerfectTimberWithin):
    """Short perfect timber with board-specific semantics
    
    Boards are structurally identical to perfect timbers but semantically different.
    They tend to be big in size and stubby in lengeth.
    """

    def get_nominal_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the nominal half-sizes of the board.
        
        For Board, these are symmetric halves of the perfect timber within size.
        
        Returns:
            Tuple of (V2(right_half, left_half), V2(front_half, back_half))
        """
        w_half = self.size[0] / Integer(2)
        h_half = self.size[1] / Integer(2)
        return (create_v2(w_half, w_half), create_v2(h_half, h_half))
    
    def get_extended_actual_csg_local(self, extend_bot: bool, extend_top: bool) -> CutCSG:
        """
        Returns the actual CSG geometry extended to infinity at specified ends.
        
        For Board, this returns a rectangular prism using the perfect timber within size.
        
        Args:
            extend_bot: If True, extend to -infinity at bottom (z=0)
            extend_top: If True, extend to +infinity at top (z=length)
            
        Returns:
            CutCSG representing the extended geometry in local coordinates
        """
        return _create_extended_rectangular_prism(
            size=self.get_perfect_size(),
            length=self.length,
            extend_bot=extend_bot,
            extend_top=extend_top
        )
    
    # TODO: Add board-specific validation and methods


# TODO finish
@dataclass(frozen=True)
class FauxTimber(PerfectTimberWithin):
    """proxy class allowing us to pretend rotated boards are timbers which allows us to use timber joints on boards"""

    board: Board = field(kw_only=True)
    
    # init from a Board
    @classmethod
    def from_board(cls, board: Board, map_top_to : TimberFace = TimberFace.TOP, map_right_to: TimberFace = TimberFace.RIGHT) -> 'FauxTimber':
        #TODO create a PerfectTimberWithin from the reoriented board
        raise NotImplementedError("TODO")

    def get_nominal_half_sizes(self) -> Tuple[V2, V2]:
        #TODO return the nominal half-sizes of the faux timber which should be the same as the original board
        return self.board.get_nominal_half_sizes()

    def reorient_csg(self, csg: CutCSG) -> CutCSG:
        #TODO reorient the csg from the faux timber's orientation to the board's orientation
        raise NotImplementedError("TODO")

    def reconstruct_joint(self, joint: 'Joint') -> 'Joint':
        #TODO reconstruct a joint by reorienting all the cut CSGs and replacing the FauxTimber with the original Board
        raise NotImplementedError("TODO")
        


# TODO consider renaming to Log LOL
@dataclass(frozen=True)
class RoundTimber(PerfectTimberWithin):
    """Cylindrical timber (e.g., logs, poles)
    
    Round timbers have a circular cross-section centered on the centerline. The nominal bounding box
    is a square that contains the circle, but the actual geometry is a cylinder.
    """
    diameter: Numeric = field(kw_only=True)  # Diameter of the circular cross-section
    
    def get_nominal_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the nominal half-sizes of the round timber.
        
        For round timbers, this is a symmetric square bounding box using the diameter.
        
        Returns:
            Tuple of (V2(d/2, d/2), V2(d/2, d/2))
        """
        half_d = self.diameter / Integer(2)
        return (create_v2(half_d, half_d), create_v2(half_d, half_d))
    
    def get_actual_csg_local(self) -> CutCSG:
        """
        Returns the actual CSG geometry for this timber.
        
        For RoundTimber, this returns a Cylinder with the specified diameter.
        
        Returns:
            Cylinder representing the actual geometry in local coordinates
        """
        from .cutcsg import Cylinder
        return Cylinder(
            radius=self.diameter / Integer(2),
            axis_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Local Z-axis
            position=create_v3(Integer(0), Integer(0), Integer(0)),  # Origin in local coords
            start_distance=Integer(0),
            end_distance=self.length
        )
    
    def get_extended_actual_csg_local(self, extend_bot: bool, extend_top: bool) -> CutCSG:
        """
        Returns the actual CSG geometry extended to infinity at specified ends.
        
        For RoundTimber, this returns a Cylinder optionally extended to infinity.
        
        Args:
            extend_bot: If True, extend to -infinity at bottom (z=0)
            extend_top: If True, extend to +infinity at top (z=length)
            
        Returns:
            Cylinder representing the extended geometry in local coordinates
        """
        from .cutcsg import Cylinder
        return Cylinder(
            radius=self.diameter / Integer(2),
            axis_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Local Z-axis
            position=create_v3(Integer(0), Integer(0), Integer(0)),  # Origin in local coords
            start_distance=None if extend_bot else Integer(0),
            end_distance=None if extend_top else self.length
        )



# TODO consider renaming to FancyTimber
@dataclass(frozen=True)
class MeshTimber(PerfectTimberWithin):
    """Timber represented by an arbitrary mesh geometry
    
    This timber type uses a mesh CSG to represent complex or irregular
    timber geometries that cannot be represented by simple primitives.
    
    TODO: Add mesh_csg field and override get_actual_csg_local()
    """
    def get_nominal_half_sizes(self) -> Tuple[V2, V2]:
        w_half = self.size[0] / Integer(2)
        h_half = self.size[1] / Integer(2)
        return (create_v2(w_half, w_half), create_v2(h_half, h_half))

    def can_be_extended_for_joints(self) -> bool:
        return False
    
    def get_extended_actual_csg_local(self, extend_bot: bool, extend_top: bool) -> CutCSG:
        """
        Returns the actual CSG geometry extended to infinity at specified ends.
        
        For MeshTimber, this returns a rectangular prism using the perfect timber within size
        (the bounding box). Note: MeshTimber cannot be extended for joints.
        
        Args:
            extend_bot: If True, extend to -infinity at bottom (z=0)
            extend_top: If True, extend to +infinity at top (z=length)
            
        Returns:
            CutCSG representing the extended geometry in local coordinates
        """
        return _create_extended_rectangular_prism(
            size=self.get_perfect_size(),
            length=self.length,
            extend_bot=extend_bot,
            extend_top=extend_top
        )

    # TODO: Add mesh_csg field and override get_actual_csg_local()

# TODO rename to RegularPolygonTimber
@dataclass(frozen=True)
class RegularPolygonTimber(PerfectTimberWithin):
    """Timber with regular polygonal cross-section
    
    This timber type has a polygonal (non-rectangular) cross-section that is
    extruded along the length axis. Examples include hexagonal or octagonal timbers.
    
    The polygon is inscribed in a circle with radius equal to half the minimum dimension
    of the nominal bounding box.
    """
    num_sides: int = field(kw_only=True)  # Number of sides for the regular polygon (e.g., 6 for hexagon)
    
    def _compute_polygon_vertices(self) -> List[V2]:
        """
        Compute vertices of regular polygon inscribed in the nominal bounding box.
        
        The polygon is centered at the origin with radius equal to half the minimum
        dimension of the bounding box.
        
        Returns:
            List of V2 vertices for the polygon
        """
        assert self.num_sides >= 3, "RegularPolygonTimber must have at least 3 sides"
        from sympy import pi, cos, sin
        # Use the smaller dimension of size as the diameter of the inscribed circle
        radius = min(self.size[0], self.size[1]) / Integer(2)
        vertices = []
        # start at (1,0) and go counterclockwise
        for i in range(self.num_sides):
            angle = radians(Integer(2) * pi * i / self.num_sides)
            x = radius * cos(angle)
            y = radius * sin(angle)
            vertices.append(Matrix([x, y]))
        return vertices
    
    def get_nominal_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the nominal half-sizes of the polygon timber.
        
        For polygon extrusion timbers, these are symmetric halves of the rectangular bounding box.
        
        Returns:
            Tuple of (V2(w/2, w/2), V2(h/2, h/2))
        """
        w_half = self.size[0] / Integer(2)
        h_half = self.size[1] / Integer(2)
        return (create_v2(w_half, w_half), create_v2(h_half, h_half))
    
    def get_actual_csg_local(self) -> CutCSG:
        """
        Returns the actual CSG geometry for this timber.
        
        For RegularPolygonTimber, this returns a ConvexPolygonExtrusion with the specified number of sides.
        
        Returns:
            ConvexPolygonExtrusion representing the actual geometry in local coordinates
        """
        from .cutcsg import ConvexPolygonExtrusion
        return ConvexPolygonExtrusion(
            points=self._compute_polygon_vertices(),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=self.length
        )
    
    def get_extended_actual_csg_local(self, extend_bot: bool, extend_top: bool) -> CutCSG:
        """
        Returns the actual CSG geometry extended to infinity at specified ends.
        
        For RegularPolygonTimber, this returns a ConvexPolygonExtrusion optionally extended to infinity.
        
        Args:
            extend_bot: If True, extend to -infinity at bottom (z=0)
            extend_top: If True, extend to +infinity at top (z=length)
            
        Returns:
            ConvexPolygonExtrusion representing the extended geometry in local coordinates
        """
        from .cutcsg import ConvexPolygonExtrusion
        return ConvexPolygonExtrusion(
            points=self._compute_polygon_vertices(),
            transform=Transform.identity(),
            start_distance=None if extend_bot else Integer(0),
            end_distance=None if extend_top else self.length
        )



# Type alias for all timber-like objects (excludes Board)
# TimberLike objects are timbers that can be used in structural joinery
# TODO come up with a cuter name for this
TimberLike = Union[Timber, MeshTimber, RoundTimber, RegularPolygonTimber]
BoardLike = Union[Board]

# ============================================================================
# Joint Related Types and Functions
# ============================================================================




@dataclass(frozen=True)
class Cutting:
    """
    A set of cuts on a timber (to create a joint, for example), defined by a CSG object representing the volume to be removed.
    
    The CSG object represents the volume to be REMOVED from the timber (negative CSG),
    in LOCAL coordinates (relative to timber.bottom_position).
    """
    # debug reference to the base timber we are cutting
    # each Cutting is tied to a timber so this is very reasonable to store here
    timber: PerfectTimberWithin

    # these end cuts are special as they determine "rough cut" of the timber in that direction.
    # If there is not an end cut in a direction, the original timber end point in that direction is used instead.
    maybe_top_end_cut: Optional[HalfSpace] = None
    maybe_bottom_end_cut: Optional[HalfSpace] = None

    # The negative CSG of the cut (the part of the timber that is removed by the cut)
    # in LOCAL coordinates (relative to timber.bottom_position)
    # Does NOT include the end cuts (those are stored separately above)
    negative_csg: Optional[CutCSG] = None

    # Optional tag for this cutting in the CSG hierarchy (e.g. "mortise_and_tenon").
    # When set, get_negative_csg_local() wraps the result in a tagged SolidUnion so that
    # the viewer can navigate the CSG tree by tag.
    tag: Optional[str] = None
    
    def get_negative_csg_local(self) -> CutCSG:
        """
        Get the complete negative CSG including end cuts.
        
        Returns the union of negative_csg with any end cuts that are defined.
        If self.tag is set, wraps the result in a tagged SolidUnion grouping node.
        """
        # Collect all CSG components
        csg_components = []
        
        # Add the base negative_csg if it exists
        if self.negative_csg is not None:
            csg_components.append(self.negative_csg)
        
        # Add end cuts if they exist
        if self.maybe_top_end_cut is not None:
            csg_components.append(self.maybe_top_end_cut)
        if self.maybe_bottom_end_cut is not None:
            csg_components.append(self.maybe_bottom_end_cut)
        
        # Return union of all components, or empty if none exist
        if len(csg_components) == 0:
            # No cuts at all - this shouldn't happen but handle gracefully
            # Return a HalfSpace that contains nothing (impossible condition)
            return HalfSpace(normal=create_v3(Integer(0), Integer(0), Integer(1)), offset=Rational(-999999))
        elif len(csg_components) == 1:
            result = csg_components[0]
            if self.tag is not None:
                from .cutcsg import SolidUnion
                # Preserve any existing tag on the component by wrapping it.
                result = SolidUnion([result], tag=self.tag)
        else:
            from .cutcsg import SolidUnion
            result = SolidUnion(csg_components, tag=self.tag)

        return result

    @staticmethod
    def make_end_cut(timber: PerfectTimberWithin, end: TimberReferenceEnd, distance_from_end_to_cut: Numeric) -> HalfSpace:
        """
        Create a HalfSpace for an end cut at the specified distance from the end.
        
        Args:
            timber: The timber being cut
            end: Which end (TOP or BOTTOM)
            distance_from_end_to_cut: Distance from the end to the cut plane
            
        Returns:
            HalfSpace representing the end cut in local coordinates
        """
        assert isinstance(end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(end).__name__}"
        if end == TimberReferenceEnd.TOP:
            return HalfSpace(normal=create_v3(Integer(0), Integer(0), Integer(1)), offset=timber.length - distance_from_end_to_cut)
        else:
            return HalfSpace(normal=create_v3(Integer(0), Integer(0), Integer(-1)), offset=-distance_from_end_to_cut)


def _timber_face_tags() -> List[Tuple[str, PrismFace]]:
    """Standard named feature tags for the 6 faces of a timber RectangularPrism."""
    return [
        ("right", PrismFace.RIGHT),
        ("left", PrismFace.LEFT),
        ("front", PrismFace.FRONT),
        ("back", PrismFace.BACK),
        ("top", PrismFace.TOP),
        ("bottom", PrismFace.BOTTOM),
    ]


def _create_extended_rectangular_prism(
    size: V2,
    length: Numeric,
    extend_bot: bool,
    extend_top: bool
) -> 'RectangularPrism':
    """
    Helper to create an extended rectangular prism in local coordinates.
    
    Args:
        size: Cross-sectional size (width, height)
        length: Length of the prism
        extend_bot: If True, extend to -infinity at bottom
        extend_top: If True, extend to +infinity at top
        
    Returns:
        RectangularPrism in local coordinates
    """
    from .cutcsg import RectangularPrism
    return RectangularPrism(
        size=size,
        transform=Transform.identity(),
        start_distance=None if extend_bot else Integer(0),
        end_distance=None if extend_top else length,
        named_features=_timber_face_tags(),
    )


def _create_timber_prism_csg_local(
    timber: PerfectTimberWithin, 
    cuts: list
) -> CutCSG:
    """
    Helper function to create a prism CSG for a timber in LOCAL coordinates, 
    extending ends with cuts to infinity.
    
    LOCAL coordinates means distances are relative to timber.bottom_position.
    This is used for rendering (where the prism is created at origin and then transformed)
    and for CSG operations (where cuts are also in local coordinates).
    
    Args:
        timber: The timber to create a prism for
        cuts: List of cuts on this timber (used to determine if ends should be infinite)
        
    Returns:
        CutCSG representing the timber (possibly semi-infinite or infinite) in LOCAL coordinates
    """
    # Check if bottom end has cuts
    has_bottom_cut = any(
        cut.maybe_bottom_end_cut is not None
        for cut in cuts
    )
    
    # Check if top end has cuts  
    has_top_cut = any(
        cut.maybe_top_end_cut is not None
        for cut in cuts
    )
    
    # Check if timber can be extended for joints
    if (has_bottom_cut or has_top_cut) and not timber.can_be_extended_for_joints():
        assert False, f"Cannot extend {type(timber).__name__} for joints - timber does not support extension"
    
    # Note: did_end_cuts_extend_timber() can be called separately to check if cuts extend beyond bounds
    # For splice joints and similar, cuts extending beyond is expected and valid behavior
    
    # Use polymorphic method to get extended CSG
    return timber.get_extended_actual_csg_local(extend_bot=has_bottom_cut, extend_top=has_top_cut)


def did_end_cuts_extend_timber(timber: PerfectTimberWithin, cuts: List['Cutting']) -> bool:
    """
    Check if any end cuts extend beyond the timber's original bounds.
    
    An end cut extends beyond if:
    - Top cut: The cutting plane is at z > timber.length (cuts beyond the top)
    - Bottom cut: The cutting plane is at z < 0 (cuts beyond the bottom)
    
    In local coordinates, HalfSpace end cuts are defined with:
    - Top cuts: normal pointing up (+Z), offset at the cut location
    - Bottom cuts: normal pointing down (-Z), offset at the cut location (negative value)
    
    Args:
        timber: The timber being cut
        cuts: List of cuts on the timber
        
    Returns:
        True if any end cut extends beyond the timber's original length
    """
    from kumiki.rule import safe_compare, Comparison
    
    for cut in cuts:
        # Check top end cut
        if cut.maybe_top_end_cut is not None:
            # For top cuts, normal is (0,0,1) and offset is the z-position of the cut
            # If offset > timber.length, the cut extends beyond the top
            if safe_compare(cut.maybe_top_end_cut.offset - timber.length, 0, Comparison.GT):
                return True
        
        # Check bottom end cut
        if cut.maybe_bottom_end_cut is not None:
            # For bottom cuts, normal is (0,0,-1) and offset is negative
            # If offset > 0, the cut extends beyond the bottom (into negative z)
            if safe_compare(cut.maybe_bottom_end_cut.offset, 0, Comparison.GT):
                return True
    
    return False


class CutTimber:
    """A timber with cuts applied to it."""
    
    # Declare members
    timber: PerfectTimberWithin
    cuts: List['Cutting']
    joints: List  # List of joints this timber participates in
    
    def __init__(self, timber: PerfectTimberWithin, cuts: Optional[List['Cutting']] = None):
        """
        Create a CutTimber from a Timber.
        
        Args:
            timber: The timber to be cut
            cuts: List of cuts to apply (default: empty list)
        """
        self.timber = timber
        self.cuts = cuts if cuts is not None else []
        self.joints = []  # List of joints this timber participates in

    @property
    def name(self) -> str:
        """Get the name from the underlying timber's ticket."""
        return self.timber.ticket.name

    # this one returns the timber without cuts where ends with joints are infinite in length
    def _extended_timber_without_cuts_csg_local(self) -> CutCSG:
        """
        Returns a CSG representation of the timber without any cuts applied.
        
        If an end has cuts on it (indicated by maybeEndCut), that end is extended to infinity.
        This allows joints to extend the timber as needed during the CSG cutting operations.
        
        Uses LOCAL coordinates (relative to timber.bottom_position).
        All cuts on this timber are also in LOCAL coordinates.
        
        Returns:
            RectangularPrism CSG representing the timber (possibly semi-infinite or infinite) in LOCAL coordinates
        """
        return _create_timber_prism_csg_local(self.timber, self.cuts)

    # this one returns the timber with all cuts applied
    def render_timber_with_cuts_csg_local(self) -> CutCSG:
        """
        Returns a CSG representation of the timber with all cuts applied.

        
        Returns:
            Difference CSG representing the timber with all cuts subtracted
        """
        # Start with the timber prism (possibly with infinite ends where cuts exist)
        starting_csg = self._extended_timber_without_cuts_csg_local()
        
        # If there are no cuts, just return the starting CSG
        if not self.cuts:
            return starting_csg
        
        # Collect all the negative CSGs (volumes to be removed) from the cuts
        negative_csgs = [cut.get_negative_csg_local() for cut in self.cuts]
        
        # Return the difference: timber - all cuts
        from .cutcsg import Difference
        return Difference(starting_csg, negative_csgs)

    def get_bounding_box_prism(self) -> RectangularPrism:
        """
        Get the bounding box prism for this timber including all its cuts.
        The bounding box is aligned with the timber's orientation.
        
        Uses PerfectTimberWithin size to determine the cross-sectional size of the bounding box.
        Uses the end cuts (maybe_top_end_cut and maybe_bottom_end_cut) to determine
        the extent of the timber along its length. For skewed end cuts, finds where
        the plane intersects the four long edges of the timber and takes the max/min.
        
        Returns:
            RectangularPrism: The bounding box for the cut timber in global coordinates
        """
        from .cutcsg import RectangularPrism, HalfSpace
        
        # Start with the timber's original bounds (in local coordinates)
        min_z = Rational(0)
        max_z = self.timber.length
        
        # Get timber half-sizes for the four corner edges
        half_width = self.timber.size[0] / Rational(2)
        half_height = self.timber.size[1] / Rational(2)
        
        # The four corner edges in local coordinates are at:
        # (-half_width, -half_height, z), (half_width, -half_height, z),
        # (-half_width, half_height, z), (half_width, half_height, z)
        corner_positions = [
            (half_width, half_height),
            (half_width, -half_height),
            (-half_width, half_height),
            (-half_width, -half_height)
        ]
        
        # Check all cuts for end cuts
        for cut in self.cuts:
            # Handle top end cut
            if cut.maybe_top_end_cut is not None:
                end_cut = cut.maybe_top_end_cut
                # Find where the plane intersects each of the four corner edges
                # Plane equation: normal · point = offset
                # Point on edge: (corner_x, corner_y, z)
                # Solve for z: normal[0]*corner_x + normal[1]*corner_y + normal[2]*z = offset
                # z = (offset - normal[0]*corner_x - normal[1]*corner_y) / normal[2]
                
                intersections = []
                for corner_x, corner_y in corner_positions:
                    # Check if normal[2] is not zero (otherwise plane is perpendicular to length)
                    if not equality_test(end_cut.normal[2], 0):
                        z_intersect = (end_cut.offset - end_cut.normal[0]*corner_x - end_cut.normal[1]*corner_y) / end_cut.normal[2]
                        intersections.append(z_intersect)
                
                # For top end cut, take the maximum intersection (furthest extent)
                if intersections:
                    max_z = Max(max_z, *intersections)
            
            # Handle bottom end cut
            if cut.maybe_bottom_end_cut is not None:
                end_cut = cut.maybe_bottom_end_cut
                # Same logic as above
                intersections = []
                for corner_x, corner_y in corner_positions:
                    if not equality_test(end_cut.normal[2], 0):
                        z_intersect = (end_cut.offset - end_cut.normal[0]*corner_x - end_cut.normal[1]*corner_y) / end_cut.normal[2]
                        intersections.append(z_intersect)
                
                # For bottom end cut, take the minimum intersection (furthest extent)
                if intersections:
                    min_z = Min(min_z, *intersections)
        
        return RectangularPrism(
            size=self.timber.size,
            transform=Transform(
                position=self.timber.get_bottom_position_global(),
                orientation=self.timber.orientation
            ),
            start_distance=min_z,
            end_distance=max_z
        )
    
    # TODO test me
    # TODO DELETE ME
    def DEPRECATED_approximate_bounding_prism(self) -> RectangularPrism:
        """
        TODO someday we want a fully analytical solution for this, but for now this is sufficient for our needs.

        Get the bounding box prism for this timber including all its cuts.
        The bounding box is aligned with the timber's orientation.
        
        Uses a hybrid approach: analytical methods for simple cases (HalfSpace cuts),
        and sampling for complex CSG operations. Works with all CSG types and orientations.
        
        Returns:
            RectangularPrism: The bounding box for the cut timber in global coordinates
        """
        from .cutcsg import RectangularPrism, HalfSpace, Difference
        
        # Start with the timber's original bounds (in local coordinates)
        min_z = Rational(0)
        max_z = self.timber.length
        
        # Length direction in local coordinates (always +Z)
        length_direction_local = Matrix([Rational(0), Rational(0), Rational(1)])
        
        # Try analytical approach first for simple HalfSpace cuts
        can_use_analytical = True
        for cut in self.cuts:
            csg = cut.get_negative_csg_local()
            
            # Check if it's a simple HalfSpace or a Difference with HalfSpaces
            if isinstance(csg, HalfSpace):
                half_space = csg
                from kumiki.rule import safe_compare, Comparison, safe_dot_product
                dot_product = safe_dot_product(half_space.normal, length_direction_local)
                
                if equality_test(Abs(dot_product), 1):
                    # HalfSpace aligned with length direction
                    # HalfSpace contains points where (p · normal) >= offset
                    # When subtracted, remaining points are where (p · normal) < offset
                    if safe_compare(dot_product, 0, Comparison.GT):
                        # Normal points in +Z direction
                        # Subtraction removes points with Z >= offset
                        max_z = Min(max_z, half_space.offset)
                    else:
                        # Normal points in -Z direction
                        # Subtraction removes points with Z <= -offset
                        min_z = Max(min_z, -half_space.offset)
                else:
                    # HalfSpace not aligned with length - need sampling
                    can_use_analytical = False
                    break
            else:
                # Complex CSG - need sampling
                can_use_analytical = False
                break
        
        if can_use_analytical:
            # All cuts were simple aligned HalfSpaces, we're done
            return RectangularPrism(
                size=self.timber.size,
                transform=Transform(
                    position=self.timber.get_bottom_position_global(),
                    orientation=self.timber.orientation
                ),
                start_distance=min_z,
                end_distance=max_z
            )
        
        # Fall back to sampling for complex cases
        cut_csg = self.render_timber_with_cuts_csg_local()
        
        # Use fewer samples for speed, using float arithmetic
        num_length_samples = 50
        num_cross_section_samples = 5
        
        # Get timber half-sizes
        half_width = self.timber.size[0] / 2
        half_height = self.timber.size[1] / 2
        
        # Find actual min Z (bottom bound)
        for i in range(num_length_samples + 1):
            z_float = float(min_z) + (float(max_z) - float(min_z)) * (i / num_length_samples)
            z = Rational(int(z_float * 1000), 1000)  # Round to 3 decimal places for speed
            
            # Sample points in the cross-section
            found_point_at_z = False
            for ix in range(-num_cross_section_samples, num_cross_section_samples + 1):
                if found_point_at_z:
                    break
                for iy in range(-num_cross_section_samples, num_cross_section_samples + 1):
                    x = half_width * Rational(ix, num_cross_section_samples)
                    y = half_height * Rational(iy, num_cross_section_samples)
                    
                    test_point = Matrix([x, y, z])
                    if cut_csg.contains_point(test_point):
                        found_point_at_z = True
                        min_z = z
                        break
            
            if found_point_at_z:
                break
        
        # Find actual max Z (top bound)
        for i in range(num_length_samples + 1):
            z_float = float(max_z) - (float(max_z) - float(min_z)) * (i / num_length_samples)
            z = Rational(int(z_float * 1000), 1000)  # Round to 3 decimal places for speed
            
            # Sample points in the cross-section
            found_point_at_z = False
            for ix in range(-num_cross_section_samples, num_cross_section_samples + 1):
                if found_point_at_z:
                    break
                for iy in range(-num_cross_section_samples, num_cross_section_samples + 1):
                    x = half_width * Rational(ix, num_cross_section_samples)
                    y = half_height * Rational(iy, num_cross_section_samples)
                    
                    test_point = Matrix([x, y, z])
                    if cut_csg.contains_point(test_point):
                        found_point_at_z = True
                        max_z = z
                        break
            
            if found_point_at_z:
                break
        
        # Create the bounding box prism in global coordinates
        return RectangularPrism(
            size=self.timber.size,
            transform=Transform(
                position=self.timber.get_bottom_position_global(),
                orientation=self.timber.orientation
            ),
            start_distance=min_z,
            end_distance=max_z
        )


# TODO rename to just Accessory
@dataclass(frozen=True)
class JointAccessory(ABC):
    """Base class for joint accessories like wedges, drawbores, etc."""

    ticket: AccessoryTicket = field(default_factory=AccessoryTicket, kw_only=True)
    
    @abstractmethod
    def render_csg_local(self) -> CutCSG:
        """
        Generate CSG representation of the accessory in local space.
        
        The local space is defined by the accessory's orientation and position,
        where the CSG is generated at the origin with identity orientation.
        
        Returns:
            CutCSG: The CSG representation of the accessory in local space
        """
        pass


# ============================================================================
# Joint Accessory Types: Pegs and Wedges
# ============================================================================

class PegShape(Enum):
    """Shape of a peg."""
    SQUARE = "square"
    ROUND = "round"


# TODO add a get_local_csg function that returns the CSG of the peg at the origin 
@dataclass(frozen=True)
class Peg(JointAccessory):
    """
    Represents a peg used in timber joinery (e.g., draw bore pegs, komisen).
    
    The peg is stored in GLOBAL SPACE with absolute position and orientation.
    In identity orientation, the peg points in the +Z direction,
    with the insertion end at the origin.

    By convention, the origin of the peg is on the mortise face that the peg is going into.
    This is why there are 2 lengths parameters, one for how deep the peg goes past the mortise face, and one for how far the peg sticks out of the mortise face.
    
    Attributes:
        transform: Transform (position and orientation) of the peg in global space
        size: Size/diameter of the peg (for square pegs, this is the side length)
        shape: Shape of the peg (SQUARE or ROUND)
        forward_length: How far the peg reaches in the forward direction (into the mortise)
        stickout_length: How far the peg "sticks out" in the back direction (outside the mortise)
    """
    transform: Transform
    # for square pegs, this is the side length
    # for round pegs, this is the diameter
    size: Numeric
    shape: PegShape

    # how far the peg reaches in the forward direction
    forward_length: Numeric

    # how far the peg "sticks out" in the back direction
    stickout_length: Numeric
    
    def render_csg_local(self) -> CutCSG:
        """
        Generate CSG representation of the peg in local space.
        
        The peg is centered at the origin with identity orientation,
        extending from -stickout_length to forward_length along the Z axis.
        
        Returns:
            CutCSG: The CSG representation of the peg
        """
        if self.shape == PegShape.SQUARE:
            # Square peg - use RectangularPrism with square cross-section
            return RectangularPrism(
                size=create_v2(self.size, self.size),
                transform=Transform.identity(),
                start_distance=-self.stickout_length,
                end_distance=self.forward_length
            )
        else:  # PegShape.ROUND
            # Round peg - use Cylinder
            radius = self.size / Integer(2)
            return Cylinder(
                axis_direction=create_v3(Integer(0), Integer(0), Integer(1)),
                radius=radius,
                position=create_v3(Integer(0), Integer(0), Integer(0)),
                start_distance=-self.stickout_length,
                end_distance=self.forward_length
            )


@dataclass(frozen=True)
class WedgeShape:
    """Specification for wedge dimensions."""
    base_width: Numeric # width of the base of the trapezoid in the X axis
    tip_width: Numeric # width of the tip of the trapezoid in the X axis
    height: Numeric # height of the trapezoid in the Y axis
    length: Numeric  # From bottom to top of trapezoid in the Z axis


@dataclass(frozen=True)
class Wedge(JointAccessory):
    r"""
    Represents a wedge used in timber joinery (e.g., wedged tenons).
    
    The wedge is stored in local space of a timber. In identity orientation,
    the pointy end of the wedge goes in the length direction of the timber.
    
    The profile of the wedge (trapezoidal shape) is in the Y axis 
    (height in Y). The width of the wedge is in the X axis.
    The origin (0,0) is at the bottom center of the longer side of the triangle.
    
    Visual representation (looking at wedge from the side):
         +z
          __________       <- tip width   
         /   \      \
        /     \      \  +y
   -x  /_______\______\    <- base width
          ↑
        origin
    """
    transform: Transform
    base_width: Numeric
    tip_width: Numeric
    height: Numeric
    length: Numeric
    stickout_length: Numeric = Integer(0)
    
    @property
    def width(self) -> Numeric:
        """Alias for base_width for convenience."""
        return self.base_width
    
    def render_csg_local(self) -> CutCSG:
        """
        Generate CSG representation of the wedge in local space.
        
        The wedge is created using a polyline extrusion (ConvexPolygonExtrusion)
        with a trapezoidal profile in the XZ plane. The base is at z=0 with base_width,
        and the tip is at z=length with tip_width. The extrusion extends along Y
        from -height/2 to height/2.
        
        The polygon profile is a trapezoid in the XZ plane:
        - Base at z=0 with width = base_width (centered at x=0)
        - Tip at z=length with width = tip_width (centered at x=0)
        
        The transform is rotated so that +Y goes to +Z (rotation around X axis by +90°).
        
        Returns:
            CutCSG: The CSG representation of the wedge
        """
        from sympy import pi
        
        # Create trapezoid polygon in XZ plane
        # Points are (x, z) where x is X coordinate and y (2D) is Z coordinate
        # Ordered counter-clockwise when viewed from +Y
        half_base_width = self.base_width / Rational(2)
        half_tip_width = self.tip_width / Rational(2)
        
        # Calculate width at stickout position (z = -stickout_length)
        # The taper goes from base_width at z=0 to tip_width at z=length
        # Linear interpolation: width(z) = base_width + (tip_width - base_width) * z / length
        has_stickout = safe_compare(self.stickout_length, 0, Comparison.GT)
        if has_stickout:
            # Width at z = -stickout_length
            stickout_width = self.base_width + (self.tip_width - self.base_width) * (-self.stickout_length) / self.length
            half_stickout_width = stickout_width / Rational(2)
            base_z = -self.stickout_length
        else:
            half_stickout_width = half_base_width
            base_z = Integer(0)
        
        trapezoid_points = [
            create_v2(-half_stickout_width, base_z),      # Bottom-left (base with stickout)
            create_v2(half_stickout_width, base_z),       # Bottom-right (base with stickout)
            create_v2(half_tip_width, self.length),       # Top-right (tip)
            create_v2(-half_tip_width, self.length)        # Top-left (tip)
        ]
        
        # Rotate transform so that +Y goes to +Z
        # This rotates around X axis by +90° (pi/2 radians)
        x_axis = create_v3(Integer(1), Integer(0), Integer(0))
        rotation_orientation = Orientation.from_axis_angle(x_axis, radians(pi / Integer(2)))
        
        wedge_transform = Transform(
            position=create_v3(Integer(0), Integer(0), Integer(0)),
            orientation=rotation_orientation
        )
        
        # Extrusion extends along Y from -height/2 to height/2
        half_height = self.height / Rational(2)
        
        return ConvexPolygonExtrusion(
            points=trapezoid_points,
            transform=wedge_transform,
            start_distance=-half_height,
            end_distance=half_height
        )


@dataclass(frozen=True)
class CSGAccessory(JointAccessory):
    """Generic accessory represented as local-space positive CSG plus a global transform."""

    transform: Transform
    positive_csg: CutCSG

    def render_csg_local(self) -> CutCSG:
        return self.positive_csg


# TODO you should build this out, maybe do any LocatedTimberFeature
@dataclass(frozen=True)
class Sticker(JointAccessory):
    """
    Just a marking used for debugging (ball at center + shaft in local +Z).
    """
    transform: Transform
    size: Numeric = inches(1)

    def render_csg_local(self) -> CutCSG:
        # Ball diameter = size, shaft diameter = size/2, shaft length = 2*size
        ball_radius = self.size / Integer(2)
        shaft_radius = self.size / Integer(4)
        shaft_length = self.size * Integer(2)
        axis_z = create_v3(Integer(0), Integer(0), Integer(1))
        origin = create_v3(Integer(0), Integer(0), Integer(0))
        ball = Cylinder(
            position=origin,
            axis_direction=axis_z,
            radius=ball_radius,
            start_distance=-ball_radius,
            end_distance=ball_radius,
        )
        shaft_position = axis_z * ball_radius
        shaft = Cylinder(
            position=shaft_position,
            axis_direction=axis_z,
            radius=shaft_radius,
            start_distance=Integer(0),
            end_distance=shaft_length,
        )
        return SolidUnion(children=[ball, shaft])
        
@dataclass(frozen=True)
class Joint:
    cut_timbers: Dict[str, CutTimber]
    ticket: JointTicket
    jointAccessories: Dict[str, JointAccessory] = field(default_factory=dict)


@dataclass(frozen=True)
class Frame:
    """
    Represents a complete timber frame structure with all cut timbers and accessories.
    
    In traditional timber framing, a 'frame' is the complete structure ready for raising.
    This class encapsulates all the timbers that have been cut with their joints,
    plus any accessories like pegs, wedges, or drawbores.
    
    Attributes:
        cut_timbers: List of CutTimber objects representing all timbers in the frame
        accessories: List of JointAccessory objects (already in global space)
        name: Optional name for this frame (e.g., "Oscar's Shed", "Main Frame")
    """
    cut_timbers: List[CutTimber]
    accessories: List[JointAccessory] = field(default_factory=list)
    name: Optional[str] = None
    
    @classmethod
    def from_joints(cls, joints: List[Joint], 
                    additional_unjointed_timbers: Optional[List[Timber]] = None,
                    name: Optional[str] = None) -> 'Frame':
        """
        Create a Frame from a list of joints and optional additional unjointed timbers.
        
        This constructor extracts all cut timbers and accessories from the joints,
        and combines cut timbers that share the same underlying timber reference.
        
        Args:
            joints: List of Joint objects
            additional_unjointed_timbers: Optional list of Timber objects that don't 
                                         participate in any joints (default: empty list)
            name: Optional name for the frame
            
        Returns:
            Frame: A new Frame object with merged cut timbers and collected accessories
            
        Raises:
            ValueError: If two timbers with the same name but same underlying timber 
                       have different references (indicates a bug)
        
        Warnings:
            Prints a warning if two timbers with the same name have different underlying 
            timber references and the underlying timbers are actually different.
        """
        import warnings
        
        if additional_unjointed_timbers is None:
            additional_unjointed_timbers = []
        
        # Dictionary to group CutTimber objects by their underlying Timber reference (identity)
        # Key: id(timber), Value: List of CutTimber objects
        timber_ref_to_cut_timbers: Dict[int, List[CutTimber]] = {}
        
        # Extract cut timbers from all joints
        for joint in joints:
            for cut_timber in joint.cut_timbers.values():
                timber_id = id(cut_timber.timber)
                if timber_id not in timber_ref_to_cut_timbers:
                    timber_ref_to_cut_timbers[timber_id] = []
                timber_ref_to_cut_timbers[timber_id].append(cut_timber)
        
        # Check for name conflicts
        # Build a mapping from name to list of timber references
        name_to_timber_refs: Dict[str, List[PerfectTimberWithin]] = {}
        for timber_id, cut_timber_list in timber_ref_to_cut_timbers.items():
            timber = cut_timber_list[0].timber  # Get timber from first CutTimber
            timber_name = timber.ticket.name
            if timber_name is not None:
                if timber_name not in name_to_timber_refs:
                    name_to_timber_refs[timber_name] = []
                # Only add if not already in the list (check by identity)
                if not any(t is timber for t in name_to_timber_refs[timber_name]):
                    name_to_timber_refs[timber_name].append(timber)
        
        # Check for conflicts
        for timber_name, timber_refs in name_to_timber_refs.items():
            if len(timber_refs) > 1:
                # Multiple timbers with the same name
                # Check if the underlying timbers are actually different
                for i in range(len(timber_refs)):
                    for j in range(i + 1, len(timber_refs)):
                        timber_i = timber_refs[i]
                        timber_j = timber_refs[j]
                        
                        # Compare using structural equality (==)
                        if timber_i == timber_j:
                            # Same timber data but different references - this is a bug
                            raise ValueError(
                                f"Error: Found two timber references with the same name '{timber_name}' "
                                f"that have identical underlying timber data. This indicates a bug "
                                f"where the same timber was created multiple times instead of reusing "
                                f"the same reference."
                            )
                        else:
                            # Different timber data with the same name - just a warning
                            warnings.warn(
                                f"Warning: Found multiple timbers with the same name '{timber_name}' "
                                f"but different properties (length, size, position, or orientation). "
                                f"This may indicate an error in timber naming. "
                                f"Timber 1: length={timber_i.length}, size={timber_i.size}, "
                                f"position={timber_i.get_bottom_position_global()}. "
                                f"Timber 2: length={timber_j.length}, size={timber_j.size}, "
                                f"position={timber_j.get_bottom_position_global()}."
                            )
        
        # Merge cut timbers with the same underlying timber reference
        merged_cut_timbers: List[CutTimber] = []
        for timber_id, cut_timber_list in timber_ref_to_cut_timbers.items():
            timber = cut_timber_list[0].timber
            
            # Collect all cuts from all CutTimber instances for this timber
            all_cuts: List[Cutting] = []
            for cut_timber in cut_timber_list:
                all_cuts.extend(cut_timber.cuts)
            
            # Create a single merged CutTimber
            merged_cut_timber = CutTimber(timber, cuts=all_cuts)
            merged_cut_timbers.append(merged_cut_timber)
        
        # Add additional unjointed timbers as CutTimbers with no cuts
        for timber in additional_unjointed_timbers:
            merged_cut_timbers.append(CutTimber(timber, cuts=[]))
        
        # Collect all accessories from all joints
        all_accessories: List[JointAccessory] = []
        for joint in joints:
            all_accessories.extend(joint.jointAccessories.values())
        
        # Create and return the Frame
        return cls(
            cut_timbers=merged_cut_timbers,
            accessories=all_accessories,
            name=name
        )
    
    def get_bounding_box(self) -> tuple[V3, V3]:
        """
        Get the axis-aligned bounding box for the entire frame in global coordinates.
        
        This computes the bounding box by getting the bounding prism for each cut timber
        and finding the global min/max coordinates that enclose all of them.
        
        Returns:
            tuple[V3, V3]: (min_corner, max_corner) where each is a 3x1 Matrix representing
                          the minimum and maximum corners of the axis-aligned bounding box
                          in global coordinates
        
        Raises:
            ValueError: If the frame contains no cut timbers
        """
        from sympy import Min as SymMin, Max as SymMax
        
        if not self.cut_timbers:
            raise ValueError("Cannot compute bounding box for empty frame (no cut timbers)")
        
        # Get bounding prism for each cut timber
        bounding_prisms = [ct.get_bounding_box_prism() for ct in self.cut_timbers]
        
        # For each prism, we need to find its 8 corners and track global min/max
        # Initialize with infinities
        min_x = None
        min_y = None
        min_z = None
        max_x = None
        max_y = None
        max_z = None
        
        for prism in bounding_prisms:
            # Get the 8 corners of the rectangular prism
            # The prism is defined by its size (width, height) in the XY plane
            # and start_distance/end_distance along the Z axis
            
            half_width = prism.size[0] / 2
            half_height = prism.size[1] / 2
            
            # Generate 8 corners in local coordinates
            # (±half_width, ±half_height, start_distance or end_distance)
            local_corners = []
            for x_sign in [-1, 1]:
                for y_sign in [-1, 1]:
                    for z_val in [prism.start_distance, prism.end_distance]:
                        local_corner = Matrix([
                            x_sign * half_width,
                            y_sign * half_height,
                            z_val
                        ])
                        local_corners.append(local_corner)
            
            # Transform each corner to global coordinates
            from kumiki.rule import safe_transform_vector
            for local_corner in local_corners:
                global_corner = prism.transform.position + safe_transform_vector(prism.transform.orientation.matrix, local_corner)
                
                # Update min/max for each axis
                if min_x is None:
                    min_x = global_corner[0]
                    max_x = global_corner[0]
                    min_y = global_corner[1]
                    max_y = global_corner[1]
                    min_z = global_corner[2]
                    max_z = global_corner[2]
                else:
                    min_x = SymMin(min_x, global_corner[0])
                    max_x = SymMax(max_x, global_corner[0])
                    min_y = SymMin(min_y, global_corner[1])
                    max_y = SymMax(max_y, global_corner[1])
                    min_z = SymMin(min_z, global_corner[2])
                    max_z = SymMax(max_z, global_corner[2])
        
        min_corner = Matrix([min_x, min_y, min_z])
        max_corner = Matrix([max_x, max_y, max_z])
        
        return (min_corner, max_corner)
    
    def __post_init__(self):
        """Validate that the frame contains no floating point numbers."""
        self._check_no_python_floats()
        pass
    
    def _check_no_python_floats(self):
        """
        Check that all numeric values in the frame use SymPy Rationals, not floats.
        
        Raises:
            AssertionError: If any float values are found in the frame
        """
        # Check all cut timbers
        for cut_timber in self.cut_timbers:
            timber = cut_timber.timber
            self._check_timber_no_python_floats(timber)
            
            # Check all cuts on this timber
            for cut in cut_timber.cuts:
                self._check_cut_no_python_floats(cut)
        
        # Check all accessories
        for accessory in self.accessories:
            self._check_accessory_no_python_floats(accessory)
    
    def _check_timber_no_python_floats(self, timber: PerfectTimberWithin):
        """Check a single timber for float values."""
        self._check_numeric_value_no_python_floats(timber.length, f"Timber '{timber.ticket.name}' length")
        self._check_vector_no_python_floats(timber.size, f"Timber '{timber.ticket.name}' size")
        self._check_vector_no_python_floats(timber.transform.position, f"Timber '{timber.ticket.name}' transform.position")
        # Note: orientation.matrix is checked as part of the matrix
        self._check_matrix_no_python_floats(timber.transform.orientation.matrix, f"Timber '{timber.ticket.name}' transform.orientation")
    
    def _check_accessory_no_python_floats(self, accessory: JointAccessory):
        """Check an accessory for float values."""
        if isinstance(accessory, Peg):
            self._check_vector_no_python_floats(accessory.transform.position, f"Peg transform.position")
            self._check_numeric_value_no_python_floats(accessory.size, f"Peg size")
            self._check_numeric_value_no_python_floats(accessory.forward_length, f"Peg forward_length")
            self._check_numeric_value_no_python_floats(accessory.stickout_length, f"Peg stickout_length")
            self._check_matrix_no_python_floats(accessory.transform.orientation.matrix, f"Peg transform.orientation")
        elif isinstance(accessory, Wedge):
            self._check_vector_no_python_floats(accessory.transform.position, f"Wedge transform.position")
            self._check_numeric_value_no_python_floats(accessory.base_width, f"Wedge base_width")
            self._check_numeric_value_no_python_floats(accessory.tip_width, f"Wedge tip_width")
            self._check_numeric_value_no_python_floats(accessory.height, f"Wedge height")
            self._check_numeric_value_no_python_floats(accessory.length, f"Wedge length")
            self._check_numeric_value_no_python_floats(accessory.stickout_length, f"Wedge stickout_length")
            self._check_matrix_no_python_floats(accessory.transform.orientation.matrix, f"Wedge transform.orientation")
        elif isinstance(accessory, CSGAccessory):
            self._check_vector_no_python_floats(accessory.transform.position, f"CSGAccessory transform.position")
            self._check_matrix_no_python_floats(accessory.transform.orientation.matrix, f"CSGAccessory transform.orientation")
    
    def _check_cut_no_python_floats(self, cut: Cutting):
        """Check a cut for float values."""
        # Cutting contains arbitrary CSG in negative_csg - would need recursive checking
        # For now, we'll skip deep CSG validation of the negative_csg field
        # (This could be extended to recursively check all CSG nodes if needed)
        pass
    
    def _check_numeric_value_no_python_floats(self, value: Numeric, description: str):
        """Check that a numeric value is not a float."""
        if isinstance(value, float):
            raise AssertionError(
                f"Float detected in Frame: {description} = {value}. "
                f"All numeric values must use SymPy Rational, not float."
            )
    
    def _check_vector_no_python_floats(self, vec: Matrix, description: str):
        """Check that all elements in a vector are not floats."""
        for i in range(vec.rows):
            self._check_numeric_value_no_python_floats(vec[i], f"{description}[{i}]")
    
    def _check_matrix_no_python_floats(self, mat: Matrix, description: str):
        """Check that all elements in a matrix are not floats."""
        for i in range(mat.rows):
            for j in range(mat.cols):
                self._check_numeric_value_no_python_floats(mat[i, j], f"{description}[{i},{j}]")



def require_check(err: Optional[str]):
    if err is not None:
        raise AssertionError(err)


def add_milestone(name: str):
    """Emit a milestone marker for the viewer loading screen.

    Writes a JSON protocol message to the real stdout pipe so the viewer
    extension can display progress during script execution.  No-ops when
    not running inside the Kumiki Viewer (checks KUMIKI_VIEWER_MILESTONES
    environment variable).
    """
    import os, sys, json as _json  # noqa: E401 — lazy imports to avoid burdening the core module
    if not os.environ.get("KUMIKI_VIEWER_MILESTONES"):
        return
    stdout = sys.__stdout__
    assert stdout is not None
    _json.dump({"type": "milestone", "name": name}, stdout)
    stdout.write("\n")
    stdout.flush()
