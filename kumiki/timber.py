"""
Kumiki - Timber types, enums, constants, and core classes
Contains all core data structures and type definitions for the timber framing system
"""

import re
from dataclasses import replace as dataclass_replace

from .rule import *
from .footprint import *
from .cutcsg import *
from .ticket import Ticket, TimberTicket, AccessoryTicket, JointTicket
from .drawing import Drawing
from .assembly import (
    AssemblyFreedom,
    AssemblyJoint,
    AssemblyMember,
    AssemblySolution,
    JointMemberSpec,
    Ordering,
    solve_assembly,
)
# Aliased: cutcsg (wildcard-imported above) also exports a BoundingBox.
from .assembly import BoundingBox as AssemblyBoundingBox
from enum import Enum
from typing import Iterable, List, Mapping, Optional, Tuple, Union, TYPE_CHECKING, Dict, Literal, final, cast, Callable
from dataclasses import dataclass, field, replace
from abc import ABC, abstractmethod
from typing_extensions import deprecated
import warnings

if TYPE_CHECKING:
    # Annotations only. The runtime imports stay inside the three methods that
    # use these -- identity.py is below timber.py in the import order and
    # reaching for it at module level would close the loop -- but a string
    # annotation naming a type nothing has imported is unresolvable, which is
    # what the type checker was reporting on each of them.
    from .identity import (JointPath, ResolvedJointPath, ResolvedTimberPath,
                           TimberPath)
    from .kiwari import Kiwari

# TODO DELETE ME
# Aliases for backwards compatibility
CSGUnion = SolidUnion
CSGDifference = Difference

# ============================================================================
# Constants
# ============================================================================

# Epsilon constants are now imported from rule module

# Thresholds for geometric decisions
OFFSET_TEST_POINT = scalar(1, 1000)  # Small offset (0.001) for testing inward direction on footprint

# ============================================================================
# Timber Feature Enums
# ============================================================================

# The vocabulary for naming part of a timber lives one module down, so that
# ticket.py can use it without importing this one. Re-exported here because
# `from kumiki.timber import TimberLongFace` is how every caller reaches it.
from .timber_features import *


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
        return TimberTicket(path=ticket)
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
    length_norm = safe_normalize_vector(length_direction)
    
    # Orthogonalize face direction relative to length direction using Gram-Schmidt
    face_input = safe_normalize_vector(width_direction)
    
    # Project face_input onto length_norm and subtract to get orthogonal component
    projection = length_norm * (face_input.dot(length_norm))
    face_orthogonal = face_input - projection
    
    # Check if face_orthogonal is too small (vectors were nearly parallel)
    if safe_zero_test(safe_norm(face_orthogonal)):
        # Choose an arbitrary orthogonal direction
        # Find a vector that's not parallel to length_norm
        if Abs(length_norm[0]) < scalar(9, 10):  # Threshold comparison
            temp_vector = create_v3(scalar(1), scalar(0), scalar(0))
        else:
            temp_vector = create_v3(scalar(0), scalar(1), scalar(0))
        
        # Project and orthogonalize
        projection = length_norm * (temp_vector.dot(length_norm))
        face_orthogonal = temp_vector - projection
    
    # Normalize the orthogonalized face direction
    face_norm = safe_normalize_vector(face_orthogonal)
    
    # Cross product to get the third axis (guaranteed to be orthogonal)
    cross_result = cross_product(length_norm, face_norm)
    height_norm = safe_normalize_vector(cross_result)
    
    # Create rotation matrix [face_norm, height_norm, length_norm]
    rotation_matrix = Matrix([
        [face_norm[0], height_norm[0], length_norm[0]],
        [face_norm[1], height_norm[1], length_norm[1]],
        [face_norm[2], height_norm[2], length_norm[2]]
    ])
    
    # Convert to Orientation
    return Orientation(rotation_matrix)


def create_timber(length: Numeric, size: V2, bottom_position: V3,
                          length_direction: Direction3D, width_direction: Direction3D,
                          ticket: Optional[Union[TimberTicket, str]] = None) -> 'Timber':
    """Factory function to create a Timber with computed orientation from direction vectors

    This is the main way to construct Timber instances. It takes direction vectors
    and computes the proper orientation matrix automatically.

    AGENT NOTE: AVOID this function if possible, prefer methods like join_timber, attach_timber, create_*_timber_on_footprint, or even create_axis_aligned_timber, which are more robust and easier to use.

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
    All timbers contain a perfect rectangular timber within their rough bounding box.

    Note: Use create_timber() factory function to construct timber instances from
    length_direction and width_direction vectors. Subclasses are frozen to ensure immutability
    after construction.

    Alternatively, if you already have a Transform object, you can construct
    a timber directly by passing: Timber(length, size, transform, ticket)

    Attributes:
        length: Length of the timber along its centerline axis
        size: Cross-sectional size (width, height) of the perfect timber within
        transform: Position and orientation in global coordinates
        ticket: Ticket for this timber (used for rendering/debugging)
    """
    length: Numeric
    size: V2
    transform: Transform
    ticket: TimberTicket = field(default_factory=TimberTicket)

    def __post_init__(self):
        self._warn_about_imperfect_reference_features()

    def _warn_about_imperfect_reference_features(self):
        """Warn where a reference rests on a face the rough timber does not match.

        The expectation, by kind of reference:

        - a reference FACE expects the rough timber's dimension in that face to
          match the perfect timber within's, so the two faces are one plane;
        - a reference ARRIS expects that of BOTH the long faces meeting at it,
          since the line is only where it should be if both are;
        - a centerline or a center plane expects nothing. Both are intrinsic to
          the perfect timber within and have no rough counterpart to disagree
          with, which is exactly what makes them somewhere to measure from when
          no face is.

        A warning rather than an error, and that is the point. Measurements are
        taken off the perfect timber within, so a reference face is only
        somewhere you can physically put a rule when the two coincide. When
        they do not, the reference still means something -- it says which face
        the layout is worked from -- and a drawing answers by rendering the
        internal PTW face to carry the measurements. A timber with no perfect
        face at all still has to be measured from somewhere.

        Whether the feature is a LONG one at all is settled by the ticket, in
        normalize_reference_features; it needs no timber, so it does not wait
        for one.
        """
        for feature in self.ticket.reference_features:
            faces = feature.long_faces_it_rests_on()
            imperfect = [face for face in faces
                         if not self.is_face_perfect(face.to.face())]
            if not imperfect:
                continue
            # Naming the whole expectation and then what fell short of it: for
            # an arris, which face is at fault is the useful half, and that
            # both were required is the half that says why.
            shortfall = ("It does not." if len(imperfect) == len(faces)
                         else f"It does not on {', '.join(f.name for f in imperfect)}.")
            warnings.warn(
                f"Reference feature {feature.name} on timber "
                f"'{self.ticket.path}' rests on "
                f"{' and '.join(face.name for face in faces)}, so the rough "
                f"timber is expected to match the perfect timber within there. "
                f"{shortfall} The rough face and the PTW face are not the same "
                f"plane, so a measurement from this reference has to be drawn "
                f"on the PTW."
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

        Args:
            face: The long face to get the size index for (RIGHT/LEFT or FRONT/BACK)

        Returns:
            Index into self.size: 0 (width) for RIGHT/LEFT, 1 (height) for FRONT/BACK
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

        Returns:
            The timber's extent along the axis normal to the given face: self.length for
            TOP/BOTTOM, self.size[0] (width) for RIGHT/LEFT, self.size[1] (height) for FRONT/BACK
        """
        # Convert to TimberFace
        face = face.to.face()
        
        if face == TimberFace.TOP or face == TimberFace.BOTTOM:
            return self.length
        elif face == TimberFace.RIGHT or face == TimberFace.LEFT:
            return self.size[0]
        else:  # FRONT or BACK
            return self.size[1]
    
    def get_rough_size_in_face_normal_axis(self, face: SomeTimberFace) -> Numeric:
        """
        Get the full rough size of the timber in the direction normal to the specified face.

        For long faces this returns the sum of the two half-sizes (e.g. right + left for
        RIGHT or LEFT). For end faces (TOP/BOTTOM) this returns the length.

        Args:
            face: The face to get the size for (can be TimberFace, TimberEnd, or TimberLongFace)
        """
        face = face.to.face()

        if face == TimberFace.TOP or face == TimberFace.BOTTOM:
            return self.length

        width_halves, height_halves = self.get_rough_half_sizes()
        if face == TimberFace.RIGHT or face == TimberFace.LEFT:
            return width_halves[0] + width_halves[1]
        else:  # FRONT or BACK
            return height_halves[0] + height_halves[1]

    def get_half_rough_size_in_face_normal_axis(self, face: SomeTimberFace) -> Numeric:
        """
        Get the rough half-size of the timber from the centerline to the specified face.

        Args:
            face: A long face (RIGHT, LEFT, FRONT, or BACK). TOP/BOTTOM will raise ValueError
                  since length has no asymmetry concept.

        Returns:
            The half-size from centerline to the specified face.
        """
        face = face.to.face()
        width_halves, height_halves = self.get_rough_half_sizes()

        if face == TimberFace.RIGHT:
            return width_halves[0]
        elif face == TimberFace.LEFT:
            return width_halves[1]
        elif face == TimberFace.FRONT:
            return height_halves[0]
        elif face == TimberFace.BACK:
            return height_halves[1]
        else:
            raise ValueError(f"get_half_rough_size_in_face_normal_axis does not support end faces (got {face})")

    @deprecated("use get_rough_size_in_face_normal_axis instead")
    def get_nominal_size_in_face_normal_axis(self, face: SomeTimberFace) -> Numeric:
        return self.get_rough_size_in_face_normal_axis(face)

    @deprecated("use get_half_rough_size_in_face_normal_axis instead")
    def get_half_nominal_size_in_face_normal_axis(self, face: SomeTimberFace) -> Numeric:
        return self.get_half_rough_size_in_face_normal_axis(face)

    # TODO DELETE replace with or forward call to get_perfect_support_distance_from_centerline
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
        d = safe_normalize_vector(direction)
        return self.size[0] * Abs(d[0]) + self.size[1] * Abs(d[1])

    # TODO DELETE replace with or forward call to get_perfect_support_distance
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
        d_global = safe_normalize_vector(direction)
        # Rotate to local frame (transpose of rotation matrix, no translation for directions)
        d_local = safe_transform_vector(self.orientation.matrix.T, d_global)
        return self.size[0] * Abs(d_local[0]) + self.size[1] * Abs(d_local[1]) + self.length * Abs(d_local[2])

    def _get_closest_oriented_face_from_faces(self, faces: List[TimberFace], target_direction: Direction3D) -> TimberFace:
        """Return the face in `faces` whose outward normal best aligns with `target_direction` (max dot product)."""
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

    def get_closest_oriented_end_face_from_global_direction(self, target_direction: Direction3D) -> TimberEnd:
        """
        Find which end face of this timber best aligns with the target direction.

        The target_direction should point "outwards" from the desired end face (not into it).

        Returns:
            The TimberEnd that best aligns with the target direction
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
            face: The face to project onto (can be TimberFace, TimberEnd, or TimberLongFace)
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
    def get_rough_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the rough half-sizes of the timber measured from the centerline.

        The rough bounding box is defined by four half-sizes measured from the
        centerline in each direction. This allows the rough timber to be non-coaxial
        with the perfect timber within (useful for square rule layout).

        Returns:
            Tuple of two V2s:
              - width_halves: V2(right_half, left_half) — half-sizes in the width dimension
              - height_halves: V2(front_half, back_half) — half-sizes in the height dimension
        """
        pass

    @deprecated("use get_rough_half_sizes instead")
    def get_nominal_half_sizes(self) -> Tuple[V2, V2]:
        return self.get_rough_half_sizes()

    def get_rough_size(self) -> V2:
        """
        Returns the rough cross sectional size of the timber.

        The rough size is the total cross sectional size defined by the rough half-sizes.
        For a perfect timber, this matches the perfect size. For an imperfect timber, this
        may differ and represents the intended bounding box for joint layout and intersection tests.
        """
        width_halves, height_halves = self.get_rough_half_sizes()
        total_w = width_halves[0] + width_halves[1]
        total_h = height_halves[0] + height_halves[1]
        return create_v2(total_w, total_h)

    @deprecated("use get_rough_size instead")
    def get_nominal_size(self) -> V2:
        return self.get_rough_size()

    def get_perfect_timber_within_csg_local(self) -> RectangularPrism:
        """
        Returns the perfect rectangular prism CSG in local coordinates.

        This represents the perfect timber within as a CSG object -- the idealized,
        finished-dimension bounding box (self.size), not the rough/as-sawn stock
        boundary. All timber types have a perfect rectangular prism that bounds
        their actual geometry.

        Returns:
            RectangularPrism in local coordinates (relative to timber's bottom position)
        """
        return RectangularPrism(
            size=self.size,
            transform=Transform.identity(),
            start_distance=scalar(0),
            end_distance=self.length,
            _features=_ptw_face_tags(),
            label=self.csg_label("perfect"),
        )

    @classmethod
    def csg_label_name(cls) -> str:
        """What this kind of timber is called in a CSG label.

        Derived from the class name -- "board", "round_timber" -- so a new
        timber type names itself without anyone remembering to add it here.
        """
        return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()

    @classmethod
    def csg_label(cls, *qualifiers: str) -> CutCSGLabel:
        """Label for one of this timber's own CSG shapes.

        A classmethod so the name follows the derived class -- a Board's rough
        extended prism reads "board (rough, extended)", not "timber (...)".
        """
        if not qualifiers:
            return CutCSGLabel(cls.csg_label_name())
        return CutCSGLabel(f"{cls.csg_label_name()} ({', '.join(qualifiers)})")

    # TODO rename to get_rough_csg_local
    def get_actual_csg_local(self) -> CutCSG:
        """
        Returns the actual CSG geometry for this timber.
        
        For the base PerfectTimberWithin class, this returns the perfect rectangular
        prism. Subclasses override this to return different geometries (cylinder, mesh, etc.).
        
        Returns:
            CutCSG representing the actual geometry in local coordinates
        """
        # The base timber's rough shape is its perfect one, but it is still
        # the rough CSG in the tree, so it is named as such.
        return dataclass_replace(
            self.get_perfect_timber_within_csg_local(),
            label=self.csg_label("rough"),
        )

    # TODO rename to get_extended_rough_csg_local
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
            face_tags=_rough_face_tags(),
            size=self.get_perfect_size(),
            length=self.length,
            extend_bot=extend_bot,
            extend_top=extend_top,
            label=self.csg_label("rough", "extended"),
        )

    @final
    def get_extended_perfect_csg_local(self, extend_bot: bool, extend_top: bool) -> CutCSG:
        """
        Returns the PERFECT (finished-dimension) CSG geometry extended to infinity at
        specified ends -- always self.get_perfect_size(), regardless of any rough/actual
        sizing a subclass's get_extended_actual_csg_local may use instead. Unlike
        get_extended_actual_csg_local, this is not overridden per-subclass: every timber
        type's perfect timber within is a rectangular prism (see
        get_perfect_timber_within_csg_local), so one implementation suffices for all of them.

        Args:
            extend_bot: If True, extend to -infinity at bottom (z=0)
            extend_top: If True, extend to +infinity at top (z=length)

        Returns:
            CutCSG representing the extended geometry in local coordinates
        """
        return _create_extended_rectangular_prism(
            face_tags=_ptw_face_tags(),
            size=self.get_perfect_size(),
            length=self.length,
            extend_bot=extend_bot,
            extend_top=extend_top,
            label=self.csg_label("perfect", "extended"),
        )

    def is_face_perfect(self, face: TimberFace) -> bool:
        """
        Check if the specified face of the timber is perfect (matches the perfect timber within).
        
        Args:
            face: The TimberFace to check
        """
        width_halves, height_halves = self.get_rough_half_sizes()
        w_half = self.size[0] / scalar(2)
        h_half = self.size[1] / scalar(2)

        if face == TimberFace.TOP or face == TimberFace.BOTTOM:
            return True  # Length is always perfect
        elif face == TimberFace.RIGHT:
            return safe_equality_test(width_halves[0], w_half)
        elif face == TimberFace.LEFT:
            return safe_equality_test(width_halves[1], w_half)
        elif face == TimberFace.FRONT:
            return safe_equality_test(height_halves[0], h_half)
        elif face == TimberFace.BACK:
            return safe_equality_test(height_halves[1], h_half)
        else:
            raise ValueError(f"Face {face} is not a long face; only RIGHT, LEFT, FRONT, BACK are valid for this check.")
    
    def is_perfect_timber(self) -> bool:
        """
        Check if this timber's actual geometry matches its rough bounding box.

        Returns True when the rough half-sizes are symmetric and equal to half
        the perfect timber within size.

        Returns:
            True if the timber is a perfect timber, False otherwise
        """
        width_halves, height_halves = self.get_rough_half_sizes()
        w_half = self.size[0] / scalar(2)
        h_half = self.size[1] / scalar(2)
        return (safe_equality_test(width_halves[0], w_half) and
                safe_equality_test(width_halves[1], w_half) and
                safe_equality_test(height_halves[0], h_half) and
                safe_equality_test(height_halves[1], h_half))

    def get_imperfect_fringe_csg_local(self) -> CutCSG:
        """
        Returns the CSG (local coordinates) of the region where this timber's actual
        geometry sticks out beyond its perfect-timber-within boundary, i.e. actual
        minus perfect.
        """
        if self.is_perfect_timber():
            return EmptyCSG()
        return Difference(
            base=self.get_extended_actual_csg_local(extend_bot=False, extend_top=False),
            subtract=[self.get_perfect_timber_within_csg_local()],
        )


# TODO HomeDepotTimber or like BoxTimber or NominalTimber, sticktimber and dressedtimber are also cute names?
@dataclass(frozen=True)
class Timber(PerfectTimberWithin):
    """Rectangular timber which may or may not be perfect.
    
    Inherits all attributes and methods from PerfectTimberWithin:
        - length: Length of the timber
        - size: Cross-sectional size (width, height)
        - transform: Position and orientation
        - name: Optional name
    """
    rough_half_sizes: Optional[Tuple[V2, V2]] = None  # Optional asymmetric half-sizes from centerline

    @staticmethod
    def from_perfect_timber_within(perfect_timber: PerfectTimberWithin, rough_half_sizes: Optional[Tuple[V2, V2]] = None) -> 'Timber':
        """
        Create a Timber instance from a PerfectTimberWithin instance.

        Args:
            perfect_timber: An instance of PerfectTimberWithin
            rough_half_sizes: Optional asymmetric half-sizes from centerline
        """
        return Timber(
            length=perfect_timber.length,
            size=perfect_timber.size,
            transform=perfect_timber.transform,
            ticket=perfect_timber.ticket,
            rough_half_sizes=rough_half_sizes
        )

    def get_rough_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the rough half-sizes of the timber.

        If rough_half_sizes is set, returns that. Otherwise returns symmetric
        half-sizes derived from the perfect timber within size.

        Returns:
            Tuple of (V2(right_half, left_half), V2(front_half, back_half))
        """
        if self.rough_half_sizes is not None:
            return self.rough_half_sizes
        w_half = self.size[0] / scalar(2)
        h_half = self.size[1] / scalar(2)
        return (create_v2(w_half, w_half), create_v2(h_half, h_half))

    def get_actual_csg_local(self) -> CutCSG:
        """
        Returns the actual CSG geometry for this timber.

        For Timber, this returns a rectangular prism using the rough half-sizes,
        offset from the centerline when the half-sizes are asymmetric.

        Returns:
            RectangularPrism representing the actual geometry in local coordinates
        """
        rough_size, offset = _get_rough_size_and_offset(self)
        return RectangularPrism(
            size=rough_size,
            transform=Transform(position=offset, orientation=Orientation.identity()),
            start_distance=scalar(0),
            end_distance=self.length,
            _features=_rough_face_tags(),
            label=self.csg_label("rough"),
        )

    def get_extended_actual_csg_local(self, extend_bot: bool, extend_top: bool) -> CutCSG:
        """
        Returns the actual CSG geometry extended to infinity at specified ends.

        For Timber, this returns a rectangular prism using the rough half-sizes,
        offset from the centerline when the half-sizes are asymmetric.

        Args:
            extend_bot: If True, extend to -infinity at bottom (z=0)
            extend_top: If True, extend to +infinity at top (z=length)

        Returns:
            CutCSG representing the extended geometry in local coordinates
        """
        rough_size, offset = _get_rough_size_and_offset(self)
        return RectangularPrism(
            size=rough_size,
            transform=Transform(position=offset, orientation=Orientation.identity()),
            start_distance=None if extend_bot else scalar(0),
            end_distance=None if extend_top else self.length,
            _features=_rough_face_tags(),
            label=self.csg_label("rough", "extended"),
        )
    

@dataclass(frozen=True)
class Board(PerfectTimberWithin):
    """Boards are perfect timbers with board-specific semantics
    
    Boards are structurally identical to perfect timbers but carry additional semantics:
    - the "length" of the board runs in the Z direction so the TOP and BOTTOM faces are referred to as the "ends" of the board
    - the "width" of the board runs in the X direction so the LEFT and RIGHT faces are referred to as the "sides" of the board
    - the "thickness" of the board runs in the Y direction so the FRONT and BACK faces are the same as the "faces" of the board

    Like timbers, we assume the grain is always running in the length direction.

    Note that you can end cut along the length direction but not in the other directions so you must ensure the board dimensions are large enough to incorporate the cuts
    """
    
    def get_rough_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the rough half-sizes of the board.

        For Board, these are symmetric halves of the perfect timber within size.
        
        Returns:
            Tuple of (V2(right_half, left_half), V2(front_half, back_half))
        """
        w_half = self.size[0] / scalar(2)
        h_half = self.size[1] / scalar(2)
        return (create_v2(w_half, w_half), create_v2(h_half, h_half))

    # TODO rename to get_extended_rough_csg_local
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
            face_tags=_rough_face_tags(),
            size=self.get_perfect_size(),
            length=self.length,
            extend_bot=extend_bot,
            extend_top=extend_top,
            label=self.csg_label("rough", "extended"),
        )
    
    # TODO: Add board-specific validation and methods


# TODO finish
#@dataclass(frozen=True)
#class FauxTimber(PerfectTimberWithin):
#    """proxy class allowing us to pretend rotate timbers to cut joints in in different orientations."""
    

# TODO consider renaming to Log LOL
@dataclass(frozen=True)
class RoundTimber(PerfectTimberWithin):
    """Cylindrical timber (e.g., logs, poles)
    
    Round timbers have a circular cross-section centered on the centerline. The rough bounding box
    is a square that contains the circle, but the actual geometry is a cylinder.
    """
    diameter: Numeric = field(kw_only=True)  # Diameter of the circular cross-section

    def is_perfect_timber(self) -> bool:
        """Round timber has a perfect cylindrical geometry, so it is perfect."""
        return True

    @staticmethod
    def from_perfect_timber_within(perfect_timber: PerfectTimberWithin, diameter: Optional[Numeric] = None) -> 'RoundTimber':
        """
        Create a Timber instance from a PerfectTimberWithin instance.
        
        Args:
            perfect_timber: An instance of PerfectTimberWithin
            diameter: Optional diameter for the round timber, if None, then the diagonal of the perfect_timber.size is used to compute the diameter.
        """
        if diameter is None:
            diameter = sqrt(perfect_timber.size[0]**2 + perfect_timber.size[1]**2)
        return RoundTimber(
            length=perfect_timber.length,
            size=perfect_timber.size,
            transform=perfect_timber.transform,
            ticket=perfect_timber.ticket,
            diameter=diameter
        )

    
    def get_rough_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the rough half-sizes of the round timber.

        For round timbers, this is a symmetric square bounding box using the diameter.
        
        Returns:
            Tuple of (V2(d/2, d/2), V2(d/2, d/2))
        """
        half_d = self.diameter / scalar(2)
        return (create_v2(half_d, half_d), create_v2(half_d, half_d))
    
    def get_actual_csg_local(self) -> CutCSG:
        """
        Returns the actual CSG geometry for this timber.
        
        For RoundTimber, this returns a Cylinder with the specified diameter.
        
        Returns:
            Cylinder representing the actual geometry in local coordinates
        """
        return Cylinder(
            radius=self.diameter / scalar(2),
            axis_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Local Z-axis
            position=create_v3(scalar(0), scalar(0), scalar(0)),  # Origin in local coords
            start_distance=scalar(0),
            end_distance=self.length,
            label=self.csg_label("rough"),
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
        return Cylinder(
            radius=self.diameter / scalar(2),
            axis_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Local Z-axis
            position=create_v3(scalar(0), scalar(0), scalar(0)),  # Origin in local coords
            start_distance=None if extend_bot else scalar(0),
            end_distance=None if extend_top else self.length,
            label=self.csg_label("rough", "extended"),
        )



# TODO consider renaming to FancyTimber
@dataclass(frozen=True)
class MeshTimber(PerfectTimberWithin):
    """Timber represented by an arbitrary mesh geometry
    
    This timber type uses a mesh CSG to represent complex or irregular
    timber geometries that cannot be represented by simple primitives.
    
    TODO: Add mesh_csg field and override get_actual_csg_local()
    """
    def get_rough_half_sizes(self) -> Tuple[V2, V2]:
        w_half = self.size[0] / scalar(2)
        h_half = self.size[1] / scalar(2)
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
            face_tags=_rough_face_tags(),
            size=self.get_perfect_size(),
            length=self.length,
            extend_bot=extend_bot,
            extend_top=extend_top,
            label=self.csg_label("rough", "extended"),
        )

    # TODO: Add mesh_csg field and override get_actual_csg_local()

@dataclass(frozen=True)
class RegularPolygonTimber(PerfectTimberWithin):
    """Timber with regular polygonal cross-section
    
    This timber type has a polygonal (non-rectangular) cross-section that is
    extruded along the length axis. Examples include hexagonal or octagonal timbers.
    
    The polygon is inscribed in a circle with radius equal to half the minimum dimension
    of the rough bounding box.
    """
    num_sides: int = field(kw_only=True)  # Number of sides for the regular polygon (e.g., 6 for hexagon)
    
    def is_perfect_timber(self) -> bool:
        """Polygonal timber has a perfect regular geometry, so it is perfect."""
        return True

    def _compute_polygon_vertices(self) -> List[V2]:
        """
        Compute vertices of regular polygon inscribed in the rough bounding box.
        
        The polygon is centered at the origin with radius equal to half the minimum
        dimension of the bounding box.
        
        Returns:
            List of V2 vertices for the polygon
        """
        assert self.num_sides >= 3, "RegularPolygonTimber must have at least 3 sides"
        # Use the smaller dimension of size as the diameter of the inscribed circle
        radius = min(self.size[0], self.size[1]) / scalar(2)
        vertices = []
        # start at (1,0) and go counterclockwise
        for i in range(self.num_sides):
            angle = radians(scalar(2) * pi * i / self.num_sides)
            x = radius * cos(angle)
            y = radius * sin(angle)
            vertices.append(Matrix([x, y]))
        return vertices
    
    def get_rough_half_sizes(self) -> Tuple[V2, V2]:
        """
        Returns the rough half-sizes of the polygon timber.

        For polygon extrusion timbers, these are symmetric halves of the rectangular bounding box.
        
        Returns:
            Tuple of (V2(w/2, w/2), V2(h/2, h/2))
        """
        w_half = self.size[0] / scalar(2)
        h_half = self.size[1] / scalar(2)
        return (create_v2(w_half, w_half), create_v2(h_half, h_half))
    
    def get_actual_csg_local(self) -> CutCSG:
        """
        Returns the actual CSG geometry for this timber.
        
        For RegularPolygonTimber, this returns a ConvexPolygonExtrusion with the specified number of sides.
        
        Returns:
            ConvexPolygonExtrusion representing the actual geometry in local coordinates
        """
        return ConvexPolygonExtrusion(
            points=self._compute_polygon_vertices(),
            transform=Transform.identity(),
            start_distance=scalar(0),
            end_distance=self.length,
            label=self.csg_label("rough"),
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
        return ConvexPolygonExtrusion(
            points=self._compute_polygon_vertices(),
            transform=Transform.identity(),
            start_distance=None if extend_bot else scalar(0),
            end_distance=None if extend_top else self.length,
            label=self.csg_label("rough", "extended"),
        )



# Type alias for all timber-like objects. This could/should just be an alias for PerfectTimberWithin but isn't for some odd reason.
TimberLike = Union[Timber, MeshTimber, RoundTimber, RegularPolygonTimber, Board]

# type alias for all block-like timber objects
BlockLike = Union[Timber,Board]


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

    # End cuts are represented canonically as fixed distances from timber bottom
    # (local z), with normals constrained to +/- local Z.
    maybe_top_end_cut_distance_from_bottom: Optional[Numeric] = None
    maybe_bottom_end_cut_distance_from_bottom: Optional[Numeric] = None

    # The negative CSG of the cut (the part of the timber that is removed by the cut)
    # in LOCAL coordinates (relative to timber.bottom_position)
    # Does NOT include the end cuts (those are stored separately above)
    negative_csg: Optional[CutCSG] = None

    # Label for this cutting's node in the CSG hierarchy (e.g. "mortise_and_tenon").
    # The cutting owns that node, so it owns the label for it.
    label: CutCSGLabel = field(default_factory=CutCSGLabel.NoLabel)

    # Assembly freedom of this timber within this joint (global space).
    # None means unspecified: the assembly solver treats the connection as rigid.
    assembly_freedom: Optional[AssemblyFreedom] = None

    # Extraction position of this timber within the assembly plan. The
    # suborder is authored by the cut function (sequencing required within the
    # joint); the order is assigned afterwards via Joint.with_order.
    assembly_ordering: Ordering = Ordering()

    def get_maybe_top_end_cut(self) -> Optional[HalfSpace]:
        """Return the top end cut HalfSpace derived from distance metadata."""
        if self.maybe_top_end_cut_distance_from_bottom is not None:
            return HalfSpace(
                normal=create_v3(scalar(0), scalar(0), scalar(1)),
                offset=self.maybe_top_end_cut_distance_from_bottom,
                label=CutCSGLabel("top_end_cut"),
            )
        return None

    def get_maybe_bottom_end_cut(self) -> Optional[HalfSpace]:
        """Return the bottom end cut HalfSpace derived from distance metadata."""
        if self.maybe_bottom_end_cut_distance_from_bottom is not None:
            return HalfSpace(
                normal=create_v3(scalar(0), scalar(0), scalar(-1)),
                offset=-self.maybe_bottom_end_cut_distance_from_bottom,
                label=CutCSGLabel("bottom_end_cut"),
            )
        return None

    def get_negative_csg_local(self) -> Optional[CutCSG]:
        """
        Get the complete negative CSG including end cuts.

        Returns the union of negative_csg with any end cuts that are defined,
        or None when this cutting removes nothing at all.
        """
        csg_components = []

        # negative_csg and the end-cut metadata can describe the same plane.
        # Both are kept: subtracting a plane twice removes the same material,
        # and a search resolves to the first match -- so the joint's own cut,
        # which goes in first, is the one that answers for the plane, and the
        # generated end cut trails behind it.
        if self.negative_csg is not None:
            csg_components.append(self.negative_csg)

        top_end_cut = self.get_maybe_top_end_cut()
        bottom_end_cut = self.get_maybe_bottom_end_cut()
        if top_end_cut is not None:
            csg_components.append(top_end_cut)
        if bottom_end_cut is not None:
            csg_components.append(bottom_end_cut)

        # A cutting that removes nothing has no node and no label; the timber
        # is then just its own CSG. Returning EmptyCSG instead would put a
        # subtract-nothing node in every such tree.
        if len(csg_components) == 0:
            return None

        # Always one SolidUnion, named or not, one piece or several: the
        # cutting owns this node, so the tree has the same shape either way.
        return SolidUnion(csg_components, label=self.label)

    @staticmethod
    def make_end_cut_distance_from_bottom(
        timber: PerfectTimberWithin,
        end: TimberEnd,
        distance_from_end_to_cut: Numeric,
    ) -> Numeric:
        """Convert distance-from-end to cut-plane distance from timber bottom."""
        assert isinstance(end, TimberEnd), f"expected TimberEnd, got {type(end).__name__}"
        if end == TimberEnd.TOP:
            return timber.length - distance_from_end_to_cut
        return distance_from_end_to_cut


def _get_rough_size_and_offset(timber: PerfectTimberWithin) -> Tuple[V2, V3]:
    """
    Returns the total rough cross-sectional size and the local (x, y) offset
    from the centerline to the center of the rough bounding box.

    Positive offset_x shifts the rough box center toward the RIGHT face;
    positive offset_y shifts it toward the FRONT face. The offset is (0, 0)
    whenever the rough half-sizes are symmetric (the default for every
    built-in timber type unless given explicit asymmetric rough_half_sizes,
    e.g. for square-rule layout).

    Internal helper (not part of the public PerfectTimberWithin API) shared by
    Timber's actual-CSG methods and CutTimber.get_rough_bounding_box_prism.
    """
    width_halves, height_halves = timber.get_rough_half_sizes()
    total_w = width_halves[0] + width_halves[1]
    total_h = height_halves[0] + height_halves[1]
    offset_x = (width_halves[0] - width_halves[1]) / scalar(2)
    offset_y = (height_halves[0] - height_halves[1]) / scalar(2)
    return (create_v2(total_w, total_h),
            create_v3(offset_x, offset_y, scalar(0)))


# Reserved prefixes for a timber's own two bounding prisms. Joint authors must
# not use them for their own features: drawing generation depends on being able
# to tell a perfect-timber-within face from a rough (as-sawn) one, and every
# timber has exactly one set of each.
#
# These used to share a single unprefixed set of names ("right", "left", ...),
# which made a feature called "right" ambiguous between the two prisms -- and
# only the rough prism ever appears in the rendered CSG tree, so the ambiguity
# resolved silently and wrongly.
# RESERVED. Nothing outside this module may name a feature with either prefix:
# they mean "a face of a timber's own body", and picking, edge derivation and
# drawing all read them that way.
#
# Reserved is not yet enforced, and there is a known hole even within the rule:
# relief geometry embeds the mating timber's rough body to scribe against, so
# one timber's CSG tree can hold another's rough.* faces. They pair into edges
# that read as this timber's -- rough.back x rough.back -- because the name
# carries no owner. Fixing that means the name, or the embedding, saying whose
# body it is.
PTW_FACE_PREFIX = "ptw."
ROUGH_FACE_PREFIX = "rough."

_TIMBER_FACES: List[Tuple[str, PrismFace]] = [
    ("right", PrismFace.RIGHT),
    ("left", PrismFace.LEFT),
    ("front", PrismFace.FRONT),
    ("back", PrismFace.BACK),
    ("top", PrismFace.TOP),
    ("bottom", PrismFace.BOTTOM),
]


#: The four arrises that run a timber's length, each between two long faces.
#: Named in the order the faces are, so front_right is one thing however it is
#: reached. Top and bottom take no part: those are ends, and the edges round an
#: end are the end face meeting each long face -- a different set, not named yet.
_TIMBER_LONG_ARRISES: List[Tuple[str, PrismFace, PrismFace]] = [
    ("front_right", PrismFace.FRONT, PrismFace.RIGHT),
    ("front_left", PrismFace.FRONT, PrismFace.LEFT),
    ("back_right", PrismFace.BACK, PrismFace.RIGHT),
    ("back_left", PrismFace.BACK, PrismFace.LEFT),
]


#: The eight arrises around a timber's two ends, each between an end face and
#: a long face. Named and ordered as TimberFeature has them --
#: BOTTOM_RIGHT_EDGE through TOP_BACK_EDGE -- so the two vocabularies line up.
_TIMBER_SHORT_ARRISES: List[Tuple[str, PrismFace, PrismFace]] = [
    ("bottom_right", PrismFace.BOTTOM, PrismFace.RIGHT),
    ("bottom_front", PrismFace.BOTTOM, PrismFace.FRONT),
    ("bottom_left", PrismFace.BOTTOM, PrismFace.LEFT),
    ("bottom_back", PrismFace.BOTTOM, PrismFace.BACK),
    ("top_right", PrismFace.TOP, PrismFace.RIGHT),
    ("top_front", PrismFace.TOP, PrismFace.FRONT),
    ("top_left", PrismFace.TOP, PrismFace.LEFT),
    ("top_back", PrismFace.TOP, PrismFace.BACK),
]


def _long_arris_tags(prefix: str) -> List[CSGFeature]:
    """Named features for a timber's four long arrises.

    Declared rather than left to be derived from the two faces meeting. A
    derived edge cannot be referred to by name afterwards and depends on both
    its parents being found again at a point; an arris a timber simply has is
    worth naming once. It is also why the faces themselves no longer meet each
    other -- see _ptw_face_tags -- since otherwise the same line would be
    reachable two ways and show up twice.
    """
    return [
        SimpleRectangularPrismEdgeFeature(
            name=f"{prefix}{name}",
            faces=(first, second),
            properties=FeatureProperties(group=FeatureGroup.B1),
        )
        for name, first, second in _TIMBER_LONG_ARRISES
    ]


def _short_arris_tags(prefix: str) -> List[CSGFeature]:
    """Named features for the eight arrises around a timber's two ends.

    The same argument as _long_arris_tags: a timber HAS these, so they are
    worth a name that survives being referred to later. The prism underneath
    names them too, as arris.4 through arris.11, and an override at the same
    key replaces the default rather than joining it -- so naming them here is
    what turns "arris.7" into "ptw.bottom_back" without leaving both.

    Where they differ from the long ones is what they are for. A long arris
    runs the length of the piece and is what you measure a joint from. An end
    arris moves whenever the timber is cut to length, so it is a thing to point
    at rather than to measure from -- which is a reason to name it, not a
    reason to leave it anonymous.
    """
    return [
        SimpleRectangularPrismEdgeFeature(
            name=f"{prefix}{name}",
            faces=(first, second),
            properties=FeatureProperties(group=FeatureGroup.B1),
        )
        for name, first, second in _TIMBER_SHORT_ARRISES
    ]


def _ptw_face_tags() -> List[CSGFeature]:
    """Named features for the 6 faces of a timber's perfect-timber-within prism.

    Group B1: they form edges against joint features (group A) and not against
    each other. The timber's own arrises used to come from faces meeting faces;
    all twelve are declared outright now (see _long_arris_tags and
    _short_arris_tags), so letting the faces pair as well would make the same
    line reachable two ways and show it twice.

    Between the faces, the long arrises and the short ones, this names every
    slot the prism underneath offers -- so a timber's body carries no anonymous
    defaults at all, and every part of it can be referred to by a name that
    means something about a timber rather than about a prism.
    """
    return [
        SimpleRectangularPrismFeature(
            name=PTW_FACE_PREFIX + face_name,
            face=face,
            properties=FeatureProperties(group=FeatureGroup.B1),
        )
        for face_name, face in _TIMBER_FACES
    ] + _long_arris_tags(PTW_FACE_PREFIX) + _short_arris_tags(PTW_FACE_PREFIX)


def _rough_face_tags() -> List[CSGFeature]:
    """Named features for the 6 faces of a timber's rough (as-sawn) prism.

    Group B1 as well, but kept separately named: a rough face only coincides
    with its perfect-timber-within counterpart on a reference face, and
    measurements may never be taken from one that does not (see
    PerfectTimberWithin.is_face_perfect).
    """
    return [
        SimpleRectangularPrismFeature(
            name=ROUGH_FACE_PREFIX + face_name,
            face=face,
            properties=FeatureProperties(group=FeatureGroup.B1),
        )
        for face_name, face in _TIMBER_FACES
    ] + _long_arris_tags(ROUGH_FACE_PREFIX) + _short_arris_tags(ROUGH_FACE_PREFIX)


def _create_extended_rectangular_prism(
    face_tags: List[CSGFeature],
    size: V2,
    length: Numeric,
    extend_bot: bool,
    extend_top: bool,
    label: CutCSGLabel = CutCSGLabel.NoLabel(),
) -> 'RectangularPrism':
    """
    Helper to create an extended rectangular prism in local coordinates.
    
    Args:
        size: Cross-sectional size (width, height)
        length: Length of the prism
        extend_bot: If True, extend to -infinity at bottom
        extend_top: If True, extend to +infinity at top
        label: What this shape is called in the CSG tree; callers building a
            timber's own body pass PerfectTimberWithin.csg_label(...)
        
    Returns:
        RectangularPrism in local coordinates
    """
    return RectangularPrism(
        size=size,
        transform=Transform.identity(),
        start_distance=None if extend_bot else scalar(0),
        end_distance=None if extend_top else length,
        _features=face_tags,
        label=label,
    )


# TODO DELETE, just combine with _extended_timber_without_cuts_csg_local
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
        cut.get_maybe_bottom_end_cut() is not None
        for cut in cuts
    )
    
    # Check if top end has cuts  
    has_top_cut = any(
        cut.get_maybe_top_end_cut() is not None
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
    
    for cut in cuts:
        top_end_cut = cut.get_maybe_top_end_cut()
        bottom_end_cut = cut.get_maybe_bottom_end_cut()

        # Check top end cut
        if top_end_cut is not None:
            # For top cuts, normal is (0,0,1) and offset is the z-position of the cut
            # If offset > timber.length, the cut extends beyond the top
            if safe_compare(top_end_cut.offset - timber.length, 0, Comparison.GT):
                return True
        
        # Check bottom end cut
        if bottom_end_cut is not None:
            # For bottom cuts, normal is (0,0,-1) and offset is negative
            # If offset > 0, the cut extends beyond the bottom (into negative z)
            if safe_compare(bottom_end_cut.offset, 0, Comparison.GT):
                return True
    
    return False


def _joints_touching_timber(
    joints: List['Joint'],
    timber: PerfectTimberWithin,
) -> List['Joint']:
    """Those *joints* that cut *timber*, in order, each listed once.

    A joint can hold more than one cutting for the same timber, so this
    deduplicates by identity rather than counting cuttings.
    """
    touching: List['Joint'] = []
    for joint in joints:
        if not any(cutting.timber is timber for cutting in joint.cuttings.values()):
            continue
        if not any(seen is joint for seen in touching):
            touching.append(joint)
    return touching


class CutTimber:
    """A timber with cuts applied to it."""
    
    # Declare members
    timber: PerfectTimberWithin
    cuts: List['Cutting']
    joints: List['Joint']

    def __init__(
        self,
        timber: PerfectTimberWithin,
        cuts: Optional[List['Cutting']] = None,
        joints: Optional[List['Joint']] = None,
    ):
        """
        Create a CutTimber from a Timber.

        Args:
            timber: The timber to be cut
            cuts: List of cuts to apply (default: empty list)
            joints: Joints this timber participates in (default: empty list).
                Populated by the from_joints constructors. Anything asking
                "which joint produced this cut?" reads it, so a CutTimber built
                by hand simply cannot answer that -- which is the honest
                outcome, since by hand there is no joint to name.
        """
        self.timber = timber
        self.cuts = cuts if cuts is not None else []
        self.joints = joints if joints is not None else []

    def resolve_joint_path(self, path: 'JointPath') -> List['ResolvedJointPath']:
        """Which of this timber's joints a name refers to.

        A list, for the same reason Frame.resolve_timber_path returns one: two
        identical joints on one timber -- both ends of a brace -- share a name,
        and pretending a name means one joint quietly picks whichever was cut
        first. Where it does match several the reference stops being stable, so
        it warns.

        Counted over this timber's cuts, in order, which is what the cut labels
        and the CSG paths below them are numbered by.
        """
        from .identity import ResolvedJointPath

        wanted = str(path)
        matches = [
            ResolvedJointPath(path=wanted, occurrence=occurrence)
            for occurrence, _ in enumerate(
                cut for cut in (self.cuts or [])
                if getattr(getattr(cut, "label", None), "name", None) == wanted
            )
        ]
        if len(matches) > 1:
            warnings.warn(
                f"{len(matches)} joints on this timber share the name {wanted!r}. They can "
                "only be told apart by the order they were cut in, so adding another before "
                "them will move anything that refers to them -- a drawing, or a measurement."
            )
        return matches

    @property
    def name(self) -> str:
        """Get the name from the underlying timber's ticket."""
        return self.timber.ticket.path

    @classmethod
    def from_joints(cls, timber: PerfectTimberWithin, joints: List['Joint']) -> 'CutTimber':
        """
        Build a CutTimber for `timber` by collecting every Cutting across `joints`
        whose Cutting.timber is this exact timber (matched by identity -- the same
        matching Frame.from_joints uses to merge cuttings for a timber across the
        whole frame).

        Useful when a joint function needs "this timber's actual body so far" (e.g.
        cut_free_house_joint's housed_timbers) but the timber has cuts from more than
        one joint (e.g. a corner miter plus a roundover decoration): rather than
        manually picking which Joint.cuttings key belongs to which timber (easy to
        mix up -- see cuttings["timberA"] vs cuttings["timberB"]), this collects
        every relevant cutting automatically, in the order `joints` are given.

        Args:
            timber: The timber to build a CutTimber for
            joints: Joints to search for cuttings on `timber`. Joints that don't
                involve `timber` at all contribute nothing.

        Returns:
            CutTimber wrapping `timber` with all matching cuts, in joint order.
        """
        cuts = [
            cutting
            for joint in joints
            for cutting in joint.cuttings.values()
            if cutting.timber is timber
        ]
        contributing = _joints_touching_timber(joints, timber)
        return cls(timber, cuts=cuts, joints=contributing)

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
        
        # Collect all the negative CSGs (volumes to be removed) from the cuts.
        # A cut that removes nothing contributes no node.
        negative_csgs = [
            csg for csg in (cut.get_negative_csg_local() for cut in self.cuts)
            if csg is not None
        ]
        if not negative_csgs:
            return starting_csg
        
        # Return the difference: timber - all cuts
        return Difference(starting_csg, negative_csgs)

    
    def _bounding_box_prism_for_cross_section(
        self,
        size: V2,
        offset_x: Numeric = scalar(0),
        offset_y: Numeric = scalar(0),
    ) -> RectangularPrism:
        """
        Shared helper: build a RectangularPrism of a given cross-sectional `size`,
        whose center may be offset from the timber's centerline by (offset_x,
        offset_y) in the timber's LOCAL (centerline-origin) frame -- e.g. for an
        asymmetric rough/as-sawn cross-section (see get_rough_bounding_box_prism).

        Cropped in length by the most restrictive top/bottom end cut across every
        Cutting on this timber (the frame's aggregated outer length trims -- not
        each joint's own internal cut geometry). For skewed end cuts, finds where
        the plane intersects the four long edges of the (possibly offset) cross-
        section and takes the max/min, narrowing progressively across all cuts.

        Returns:
            RectangularPrism: The bounding box for the cut timber in global coordinates
        """
        # Start with the timber's original bounds (in local coordinates)
        min_z = scalar(0)
        max_z = self.timber.length

        half_width = size[0] / scalar(2)
        half_height = size[1] / scalar(2)

        # The four corner edges in local coordinates are at:
        # (offset_x -+ half_width, offset_y -+ half_height, z)
        corner_positions = [
            (offset_x + half_width, offset_y + half_height),
            (offset_x + half_width, offset_y - half_height),
            (offset_x - half_width, offset_y + half_height),
            (offset_x - half_width, offset_y - half_height)
        ]

        # Check all cuts for end cuts
        for cut in self.cuts:
            top_end_cut = cut.get_maybe_top_end_cut()
            bottom_end_cut = cut.get_maybe_bottom_end_cut()

            # Handle top end cut
            if top_end_cut is not None:
                end_cut = top_end_cut
                # Find where the plane intersects each of the four corner edges
                # Plane equation: normal · point = offset
                # Point on edge: (corner_x, corner_y, z)
                # Solve for z: normal[0]*corner_x + normal[1]*corner_y + normal[2]*z = offset
                # z = (offset - normal[0]*corner_x - normal[1]*corner_y) / normal[2]

                intersections = []
                for corner_x, corner_y in corner_positions:
                    # Check if normal[2] is not zero (otherwise plane is perpendicular to length)
                    if not safe_equality_test(end_cut.normal[2], 0):
                        z_intersect = (end_cut.offset - end_cut.normal[0]*corner_x - end_cut.normal[1]*corner_y) / end_cut.normal[2]
                        intersections.append(z_intersect)

                # For top end cut, clamp the top bound down to the cut plane extent.
                if intersections:
                    max_z = Min(max_z, *intersections)

            # Handle bottom end cut
            if bottom_end_cut is not None:
                end_cut = bottom_end_cut
                # Same logic as above
                intersections = []
                for corner_x, corner_y in corner_positions:
                    if not safe_equality_test(end_cut.normal[2], 0):
                        z_intersect = (end_cut.offset - end_cut.normal[0]*corner_x - end_cut.normal[1]*corner_y) / end_cut.normal[2]
                        intersections.append(z_intersect)

                # For bottom end cut, clamp the bottom bound up to the cut plane extent.
                if intersections:
                    min_z = Max(min_z, *intersections)

        global_offset = (
            self.timber.get_width_direction_global() * offset_x
            + self.timber.get_height_direction_global() * offset_y
        )

        return RectangularPrism(
            size=size,
            transform=Transform(
                position=self.timber.get_bottom_position_global() + global_offset,
                orientation=self.timber.orientation
            ),
            start_distance=min_z,
            end_distance=max_z
        )

    def get_perfect_timber_within_bounding_box_prism(self) -> RectangularPrism:
        """
        Get the bounding box prism for this timber cropped based on its end cuts if any, otherwise the original perfet timber within box is produced.
        The bounding box is aligned with the timber's orientation.

        Uses PerfectTimberWithin size to determine the cross-sectional size of the bounding box.
        Uses the end cuts (maybe_top_end_cut and maybe_bottom_end_cut) to determine
        the extent of the timber along its length. For skewed end cuts, finds where
        the plane intersects the four long edges of the timber and takes the max/min.

        Returns:
            RectangularPrism: The bounding box for the cut timber in global coordinates
        """
        return self._bounding_box_prism_for_cross_section(self.timber.size)

    def get_rough_bounding_box_prism(self) -> RectangularPrism:
        """
        Get the bounding box prism for this timber's ROUGH (as-sawn) cross-section,
        cropped in length the same way as get_perfect_timber_within_bounding_box_prism
        (the most restrictive end cut across every Cutting on this timber -- the
        frame's aggregated outer length trims, not each joint's own internal cut
        geometry).

        Unlike the perfect-timber-within box, the rough box may be off-center from
        the timber's centerline (see get_rough_half_sizes -- e.g. for square-rule
        layout) and is generally larger than the perfect/finished size.

        Returns:
            RectangularPrism: The rough bounding box for the cut timber, in global coordinates
        """
        rough_size, offset = _get_rough_size_and_offset(self.timber)
        return self._bounding_box_prism_for_cross_section(rough_size, offset[0], offset[1])
    
    @deprecated("use get_perfect_timber_within_bounding_box_prism instead")
    def get_bounding_box_prism(self) -> RectangularPrism:
        return self.get_perfect_timber_within_bounding_box_prism()
    
    @deprecated("use get_perfect_timber_within_bounding_box_prism instead")
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
        
        # Start with the timber's original bounds (in local coordinates)
        min_z = scalar(0)
        max_z = self.timber.length
        
        # Length direction in local coordinates (always +Z)
        length_direction_local = Matrix([scalar(0), scalar(0), scalar(1)])
        
        # Try analytical approach first for simple HalfSpace cuts
        can_use_analytical = True
        for cut in self.cuts:
            csg = cut.get_negative_csg_local()
            if csg is None:
                continue
            
            # A cutting always wraps what it removes in a SolidUnion of its
            # own, so look through that to the pieces doing the removing.
            components = list(csg.children) if isinstance(csg, SolidUnion) else [csg]

            for half_space in components:
                # Check if it's a simple HalfSpace
                if not isinstance(half_space, HalfSpace):
                    # Complex CSG - need sampling
                    can_use_analytical = False
                    break

                dot_product = safe_dot_product(half_space.normal, length_direction_local)
                if not safe_equality_test(Abs(dot_product), 1):
                    # HalfSpace not aligned with length - need sampling
                    can_use_analytical = False
                    break

                # HalfSpace aligned with length direction.
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

            if not can_use_analytical:
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
            z = scalar(int(z_float * 1000), 1000)  # Round to 3 decimal places for speed
            
            # Sample points in the cross-section
            found_point_at_z = False
            for ix in range(-num_cross_section_samples, num_cross_section_samples + 1):
                if found_point_at_z:
                    break
                for iy in range(-num_cross_section_samples, num_cross_section_samples + 1):
                    x = half_width * scalar(ix, num_cross_section_samples)
                    y = half_height * scalar(iy, num_cross_section_samples)
                    
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
            z = scalar(int(z_float * 1000), 1000)  # Round to 3 decimal places for speed
            
            # Sample points in the cross-section
            found_point_at_z = False
            for ix in range(-num_cross_section_samples, num_cross_section_samples + 1):
                if found_point_at_z:
                    break
                for iy in range(-num_cross_section_samples, num_cross_section_samples + 1):
                    x = half_width * scalar(ix, num_cross_section_samples)
                    y = half_height * scalar(iy, num_cross_section_samples)
                    
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
class Accessory(ABC):
    """Base class for joint accessories like wedges, drawbores, etc."""

    ticket: AccessoryTicket = field(default_factory=AccessoryTicket, kw_only=True)

    # Assembly freedom of this accessory within its joint (global space).
    # None means unspecified: the assembly solver treats the connection as rigid.
    assembly_freedom: Optional[AssemblyFreedom] = field(default=None, kw_only=True)

    # Extraction position within the assembly plan; the cut function sets the
    # suborder (e.g. pegs pop before the joint slides apart), Joint.with_order
    # sets the order.
    assembly_ordering: Ordering = field(default=Ordering(), kw_only=True)
    
    @abstractmethod
    def get_csg_local(self) -> CutCSG:
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


@dataclass(frozen=True)
class Peg(Accessory):
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
    
    def get_csg_local(self) -> CutCSG:
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
            radius = self.size / scalar(2)
            return Cylinder(
                axis_direction=create_v3(scalar(0), scalar(0), scalar(1)),
                radius=radius,
                position=create_v3(scalar(0), scalar(0), scalar(0)),
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
class Wedge(Accessory):
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
    stickout_length: Numeric = scalar(0)
    
    @property
    def width(self) -> Numeric:
        """Alias for base_width for convenience."""
        return self.base_width
    
    def get_csg_local(self) -> CutCSG:
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
        # Create trapezoid polygon in XZ plane
        # Points are (x, z) where x is X coordinate and y (2D) is Z coordinate
        # Ordered counter-clockwise when viewed from +Y
        half_base_width = self.base_width / scalar(2)
        half_tip_width = self.tip_width / scalar(2)
        
        # Calculate width at stickout position (z = -stickout_length)
        # The taper goes from base_width at z=0 to tip_width at z=length
        # Linear interpolation: width(z) = base_width + (tip_width - base_width) * z / length
        has_stickout = safe_compare(self.stickout_length, 0, Comparison.GT)
        if has_stickout:
            # Width at z = -stickout_length
            stickout_width = self.base_width + (self.tip_width - self.base_width) * (-self.stickout_length) / self.length
            half_stickout_width = stickout_width / scalar(2)
            base_z = -self.stickout_length
        else:
            half_stickout_width = half_base_width
            base_z = scalar(0)
        
        trapezoid_points = [
            create_v2(-half_stickout_width, base_z),      # Bottom-left (base with stickout)
            create_v2(half_stickout_width, base_z),       # Bottom-right (base with stickout)
            create_v2(half_tip_width, self.length),       # Top-right (tip)
            create_v2(-half_tip_width, self.length)        # Top-left (tip)
        ]
        
        # Rotate transform so that +Y goes to +Z
        # This rotates around X axis by +90° (pi/2 radians)
        x_axis = create_v3(scalar(1), scalar(0), scalar(0))
        rotation_orientation = Orientation.from_axis_angle(x_axis, radians(pi / scalar(2)))
        
        wedge_transform = Transform(
            position=create_v3(scalar(0), scalar(0), scalar(0)),
            orientation=rotation_orientation
        )
        
        # Extrusion extends along Y from -height/2 to height/2
        half_height = self.height / scalar(2)
        
        return ConvexPolygonExtrusion(
            points=trapezoid_points,
            transform=wedge_transform,
            start_distance=-half_height,
            end_distance=half_height
        )


@dataclass(frozen=True)
class CSGAccessory(Accessory):
    """Generic accessory represented as local-space positive CSG plus a global transform."""

    transform: Transform
    positive_csg: CutCSG

    def get_csg_local(self) -> CutCSG:
        return self.positive_csg


# TODO you should build this out, maybe do any LocatedTimberFeature
@dataclass(frozen=True)
class Sticker(Accessory):
    """
    Just a marking used for debugging (ball at center + shaft in local +Z).
    """
    transform: Transform
    size: Numeric = inches(1)

    def get_csg_local(self) -> CutCSG:
        # Ball diameter = size, shaft diameter = size/2, shaft length = 2*size
        ball_radius = self.size / scalar(2)
        shaft_radius = self.size / scalar(4)
        shaft_length = self.size * scalar(2)
        axis_z = create_v3(scalar(0), scalar(0), scalar(1))
        origin = create_v3(scalar(0), scalar(0), scalar(0))
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
            start_distance=scalar(0),
            end_distance=shaft_length,
        )
        return SolidUnion(children=[ball, shaft])
        
@dataclass(frozen=True)
class Joint:
    cuttings: Dict[str, Cutting]
    ticket: JointTicket
    jointAccessories: Dict[str, Accessory] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A cutting that removes nothing contributes no CSG node, so a joint
        # whose cuttings all remove nothing would cut no timber at all.
        assert any(
            cutting.get_negative_csg_local() is not None
            for cutting in self.cuttings.values()
        ), f"Joint '{self.ticket.path}' has no cutting that removes anything"

    def is_decorative(self) -> bool:
        return len(self.cuttings) == 1

    def with_order(
        self,
        order: Union[
            int,
            Mapping[str, int],
            Iterable[Tuple[Union[str, "PerfectTimberWithin", "Accessory"], int]],
        ],
    ) -> "Joint":
        """Return a copy of this joint with assembly order(s) assigned.

        Assembly freedoms and suborders are authored by the cut functions;
        the order is the frame-level plan and is assigned here, after cutting
        (smaller order = extracted earlier during disassembly).

        with_order(n): sets order=n on every cutting and accessory, keeping
        their suborders, so intra-joint sequencing (peg pops before the tenon
        slides) is preserved within step n.

        with_order({key: n, ...}) or with_order([(member, n), ...]): sets
        Ordering(n, 0) on each named member — referenced by cutting/accessory
        string key, or by the timber / accessory object itself (a timber
        reference applies to every cutting holding it; use the pair-list form
        for object references, which are unhashable). Unnamed members keep
        their current ordering. Raises ValueError for unknown references, or
        when the new orderings break the strict precedence the cut function
        expressed via suborders (any member pair previously strictly ordered
        must remain strictly ordered).

        Assign orders BEFORE building the Frame: this rebuilds the member
        objects (dataclasses.replace, preserving timber references), so a
        Frame built earlier would still hold the previous orderings.
        """
        if isinstance(order, int):
            new_cuttings = {
                key: replace(cutting, assembly_ordering=Ordering(order, cutting.assembly_ordering.suborder))
                for key, cutting in self.cuttings.items()
            }
            new_accessories = {
                key: replace(accessory, assembly_ordering=Ordering(order, accessory.assembly_ordering.suborder))
                for key, accessory in self.jointAccessories.items()
            }
            return Joint(cuttings=new_cuttings, ticket=self.ticket, jointAccessories=new_accessories)

        # Per-member form. Members are addressed as ("cutting"|"accessory", key).
        def resolve(reference) -> List[Tuple[str, str]]:
            if isinstance(reference, str):
                if reference in self.cuttings:
                    return [("cutting", reference)]
                if reference in self.jointAccessories:
                    return [("accessory", reference)]
                raise ValueError(
                    f"with_order: unknown member key '{reference}'; this joint has cuttings "
                    f"{sorted(self.cuttings)} and accessories {sorted(self.jointAccessories)}"
                )
            timber_matches = [("cutting", key) for key, cutting in self.cuttings.items() if cutting.timber is reference]
            if timber_matches:
                return timber_matches
            accessory_matches = [("accessory", key) for key, accessory in self.jointAccessories.items() if accessory is reference]
            if accessory_matches:
                return accessory_matches
            reference_name = getattr(getattr(reference, "ticket", None), "path", repr(type(reference)))
            raise ValueError(f"with_order: '{reference_name}' is not a timber or accessory of this joint")

        old_orderings: Dict[Tuple[str, str], Ordering] = {
            ("cutting", key): cutting.assembly_ordering for key, cutting in self.cuttings.items()
        }
        old_orderings.update(
            (("accessory", key), accessory.assembly_ordering) for key, accessory in self.jointAccessories.items()
        )

        order_pairs: List[Tuple[Union[str, "PerfectTimberWithin", "Accessory"], int]]
        if isinstance(order, Mapping):
            order_pairs = [(str(key), int(value)) for key, value in cast(Mapping[str, int], order).items()]
        else:
            order_pairs = [(reference, int(member_order)) for reference, member_order in order]
        new_orderings = dict(old_orderings)
        for reference, member_order in order_pairs:
            for member_id in resolve(reference):
                new_orderings[member_id] = Ordering(member_order, 0)

        # The cut function's suborders express required sequencing; explicit
        # per-member orders must not invert or collapse it.
        member_ids = list(old_orderings)
        for first in member_ids:
            for second in member_ids:
                if old_orderings[first] < old_orderings[second] and not new_orderings[first] < new_orderings[second]:
                    raise ValueError(
                        f"with_order: '{first[1]}' must be extracted before '{second[1]}' "
                        f"(orderings {old_orderings[first].label()} < {old_orderings[second].label()}), "
                        f"but the new orders place them at {new_orderings[first].label()} "
                        f"vs {new_orderings[second].label()}"
                    )

        new_cuttings = {
            key: replace(cutting, assembly_ordering=new_orderings[("cutting", key)])
            for key, cutting in self.cuttings.items()
        }
        new_accessories = {
            key: replace(accessory, assembly_ordering=new_orderings[("accessory", key)])
            for key, accessory in self.jointAccessories.items()
        }
        return Joint(cuttings=new_cuttings, ticket=self.ticket, jointAccessories=new_accessories)

def make_compound_joint(joints: List[Joint], ticket: JointTicket) -> Joint:
    """
    Create a compound joint that combines multiple joints together.

    The cuttings and accessories from all joints are merged into a single Joint object.
    Numeric suffixes are added to accessory and cutting keys if there are conflicts.
    The tickets of the input joints are ignored.

    Args:
        joints: List of Joint objects to combine
        ticket: JointTicket for the compound joint
    """
    def _add_with_unique_key(target: dict, key: str, value) -> None:
        if key not in target:
            target[key] = value
            return
        suffix = 2
        while f"{key}_{suffix}" in target:
            suffix += 1
        target[f"{key}_{suffix}"] = value

    merged_cuttings: Dict[str, Cutting] = {}
    merged_accessories: Dict[str, Accessory] = {}
    for joint in joints:
        for key, cutting in joint.cuttings.items():
            _add_with_unique_key(merged_cuttings, key, cutting)
        for key, accessory in joint.jointAccessories.items():
            _add_with_unique_key(merged_accessories, key, accessory)

    return Joint(cuttings=merged_cuttings, ticket=ticket, jointAccessories=merged_accessories)

def _timber_path_of(timber: 'PerfectTimberWithin') -> str:
    """A timber's authored name, however it carries one."""
    ticket = getattr(timber, "ticket", None)
    path = getattr(ticket, "path", None)
    if isinstance(path, str):
        return path
    return getattr(timber, "name", None) or type(timber).__name__


@dataclass(frozen=True)
class Frame:
    """
    Represents a complete timber frame structure with all cut timbers and accessories.
    
    In traditional timber framing, a 'frame' is the complete structure ready for raising.
    This class encapsulates all the timbers that have been cut with their joints,
    plus any accessories like pegs, wedges, or drawbores.
    
    Attributes:
        cut_timbers: List of CutTimber objects representing all timbers in the frame
        accessories: List of Accessory objects (already in global space)
        name: Optional name for this frame (e.g., "Oscar's Shed", "Main Frame")
    """
    cut_timbers: List[CutTimber]
    accessories: List[Accessory] = field(default_factory=list)
    name: Optional[str] = None
    source_joints: Optional[List] = field(default=None, compare=False, hash=False, repr=False)
    footprints: List[Footprint] = field(default_factory=list)
    # Drawings the frame asks for. The drawings file may override these and add
    # its own; see docs/drawing-mode-plan.md.
    drawings: List[Drawing] = field(default_factory=list)
    # The numbers this frame was built from, if it was built from any. Declared
    # inside the builder and handed back here, which is how kigumi learns what
    # it may adjust without a module-level declaration to go looking for.
    kiwari: Optional['Kiwari'] = field(default=None, compare=False)

    def resolve_timber_path(self, path: 'TimberPath') -> List['ResolvedTimberPath']:
        """Which timbers a name refers to, in this frame.

        A list, because a name may match several: paths are not required to be
        unique, and pretending one always means one timber would quietly pick
        whichever came first. Where it does match several, the reference stops
        being stable -- each is then told apart by the order the frame built
        them, so inserting another above them moves every reference below. That
        is worth saying out loud rather than discovering later, so it warns.
        """
        from .identity import ResolvedTimberPath

        wanted = str(path)
        matches = [
            ResolvedTimberPath(path=wanted, occurrence=occurrence)
            for occurrence, _ in enumerate(
                cut for cut in self.cut_timbers
                if _timber_path_of(cut.timber) == wanted
            )
        ]
        if len(matches) > 1:
            warnings.warn(
                f"{len(matches)} timbers share the path {wanted!r}. They can only be told "
                "apart by the order they were built in, so adding another above them will "
                "move anything that refers to them -- a drawing, or a measurement. Give "
                "them distinct ticket paths to keep those references stable."
            )
        return matches

    def timber_paths(self) -> List['TimberPath']:
        """Every name in the frame, in order, duplicates included."""
        from .identity import TimberPath

        return [TimberPath(_timber_path_of(cut.timber)) for cut in self.cut_timbers]

    @classmethod
    def from_joints(cls, joints: List[Joint],
                    additional_unjointed_timbers: Optional[List[PerfectTimberWithin]] = None,
                    name: Optional[str] = None,
                    kiwari: Optional['Kiwari'] = None) -> 'Frame':
        """
        Create a Frame from a list of joints and optional additional unjointed timbers.
        
        This constructor extracts all cut timbers and accessories from the joints,
        and combines cut timbers that share the same underlying timber reference.
        
        Args:
            joints: List of Joint objects
            additional_unjointed_timbers: Optional list of PerfectTimberWithin objects that don't
                                         participate in any joints (default: empty list)
            name: Optional name for the frame
            kiwari: The numbers the frame was built from, if it takes any
            
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
        
        # Dictionary to group Cutting objects by their underlying Timber reference (identity)
        # Key: id(timber), Value: List of Cutting objects
        timber_ref_to_cuttings: Dict[int, List[Cutting]] = {}
        timber_ref_to_timber: Dict[int, PerfectTimberWithin] = {}

        # Extract cuttings from all joints
        for joint in joints:
            for cutting in joint.cuttings.values():
                timber_id = id(cutting.timber)
                timber_ref_to_timber[timber_id] = cutting.timber
                if timber_id not in timber_ref_to_cuttings:
                    timber_ref_to_cuttings[timber_id] = []
                timber_ref_to_cuttings[timber_id].append(cutting)
        
        # Check for name conflicts
        # Build a mapping from name to list of timber references
        name_to_timber_refs: Dict[str, List[PerfectTimberWithin]] = {}
        for timber_id, timber in timber_ref_to_timber.items():
            timber_name = timber.ticket.path
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
        for timber_id, cutting_list in timber_ref_to_cuttings.items():
            timber = timber_ref_to_timber[timber_id]

            # Collect all cuts from all joints for this timber
            all_cuts: List[Cutting] = []
            all_cuts.extend(cutting_list)
            
            # Create a single merged CutTimber
            merged_cut_timber = CutTimber(
                timber,
                cuts=all_cuts,
                joints=_joints_touching_timber(joints, timber),
            )
            merged_cut_timbers.append(merged_cut_timber)
        
        # Add additional unjointed timbers as CutTimbers with no cuts
        for timber in additional_unjointed_timbers:
            merged_cut_timbers.append(CutTimber(timber, cuts=[], joints=[]))
        
        # Collect all accessories from all joints
        all_accessories: List[Accessory] = []
        for joint in joints:
            all_accessories.extend(joint.jointAccessories.values())
        
        # Create and return the Frame
        return cls(
            cut_timbers=merged_cut_timbers,
            accessories=all_accessories,
            name=name,
            source_joints=list(joints),
            kiwari=kiwari,
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
        if not self.cut_timbers:
            raise ValueError("Cannot compute bounding box for empty frame (no cut timbers)")
        
        # Get bounding prism for each cut timber
        bounding_prisms = [ct.get_perfect_timber_within_bounding_box_prism() for ct in self.cut_timbers]
        
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
                    min_x = min(min_x, global_corner[0])
                    max_x = max(max_x, global_corner[0])
                    min_y = min(min_y, global_corner[1])
                    max_y = max(max_y, global_corner[1])
                    min_z = min(min_z, global_corner[2])
                    max_z = max(max_z, global_corner[2])
        
        min_corner = Matrix([min_x, min_y, min_z])
        max_corner = Matrix([max_x, max_y, max_z])
        
        return (min_corner, max_corner)
    


class KumikiArrangementError(ValueError):
    """Raised when a timber arrangement or joint parameter fails a validation check.

    Unlike AssertionError, this survives `python -O` and is safe for callers to
    catch specifically when handling invalid joint/arrangement configurations.
    """


def require_check(err: Optional[str]):
    if err is not None:
        raise KumikiArrangementError(err)


def add_milestone(name: str):
    """Emit a milestone marker for the viewer loading screen.

    Writes a JSON protocol message to the real stdout pipe so the viewer
    extension can display progress during script execution.  No-ops when
    not running inside the Kigumi extension (checks KIGUMI_VIEWER_MILESTONES
    environment variable).
    """
    import os, sys, json as _json  # noqa: E401 — lazy imports to avoid burdening the core module
    if not os.environ.get("KIGUMI_VIEWER_MILESTONES"):
        return
    stdout = sys.__stdout__
    assert stdout is not None
    _json.dump({"type": "milestone", "name": name}, stdout)
    stdout.write("\n")
    stdout.flush()


def solve_frame_assembly(
    frame: Frame,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Optional[AssemblySolution]:
    """Solve the disassembly sequence for a frame's source joints.

    Adapts the frame into the abstract assembly graph of kumiki/assembly.py —
    one AssemblyMember per distinct timber/accessory (keyed by ticket
    kumiki_id, positioned at the timber centroid) and one AssemblyJoint per
    source joint — then delegates to solve_assembly.

    Returns None when no member of any source joint has an assembly freedom.
    """
    source_joints = list(frame.source_joints or [])
    has_any_freedom = any(
        cutting.assembly_freedom is not None
        for joint in source_joints
        for cutting in joint.cuttings.values()
    ) or any(
        accessory.assembly_freedom is not None
        for joint in source_joints
        for accessory in joint.jointAccessories.values()
    )
    if not has_any_freedom:
        return None

    members: Dict[int, AssemblyMember] = {}

    def register_timber(timber: PerfectTimberWithin) -> int:
        key = timber.ticket.kumiki_id
        if key not in members:
            centroid = (
                timber.get_bottom_position_global()
                + timber.get_length_direction_global() * timber.length / 2
            )
            corners = [
                [float(giraffe_evalf(corner_position[axis, 0])) for axis in range(3)]
                for corner_position in (
                    timber.get_corner_position_global(corner) for corner in TimberCorner
                )
            ]
            bbox = AssemblyBoundingBox(
                min_x=min(c[0] for c in corners), max_x=max(c[0] for c in corners),
                min_y=min(c[1] for c in corners), max_y=max(c[1] for c in corners),
                min_z=min(c[2] for c in corners), max_z=max(c[2] for c in corners),
            )
            members[key] = AssemblyMember(key=key, name=timber.ticket.path, position=centroid, bbox=bbox)
        return key

    def register_accessory(accessory: Accessory) -> int:
        key = accessory.ticket.kumiki_id
        if key not in members:
            transform = getattr(accessory, "transform", None)
            position = transform.position if transform is not None else create_v3(0, 0, 0)
            # Accessory extents are not modeled yet; a small box at the
            # transform position lets the clear-out pass shove parked pegs.
            px, py, pz = (float(giraffe_evalf(position[axis, 0])) for axis in range(3))
            radius = 0.02
            bbox = AssemblyBoundingBox(
                min_x=px - radius, max_x=px + radius,
                min_y=py - radius, max_y=py + radius,
                min_z=pz - radius, max_z=pz + radius,
            )
            members[key] = AssemblyMember(key=key, name=accessory.ticket.path, position=position, bbox=bbox)
        return key

    def add_spec(specs: Dict[int, JointMemberSpec], key: int,
                 freedom: Optional[AssemblyFreedom], ordering: Ordering) -> None:
        existing = specs.get(key)
        if existing is None:
            specs[key] = JointMemberSpec(freedom=freedom, ordering=ordering)
            return
        # The same member can appear under several cutting keys of one
        # (compound) joint; its escape DOFs are the union of all of them and
        # the earliest ordering wins.
        if existing.freedom is not None and freedom is not None:
            combined = AssemblyFreedom.combine(existing.freedom, freedom)
        else:
            combined = existing.freedom if freedom is None else freedom
        specs[key] = JointMemberSpec(freedom=combined, ordering=min(existing.ordering, ordering))

    assembly_joints: List[AssemblyJoint] = []
    for joint in source_joints:
        specs: Dict[int, JointMemberSpec] = {}
        for cutting in joint.cuttings.values():
            add_spec(specs, register_timber(cutting.timber), cutting.assembly_freedom, cutting.assembly_ordering)
        for accessory in joint.jointAccessories.values():
            add_spec(specs, register_accessory(accessory), accessory.assembly_freedom, accessory.assembly_ordering)
        joint_name = joint.ticket.get_name()
        if joint_name == "[no-name]":
            joint_name = joint.ticket.joint_type or "joint"
        assembly_joints.append(AssemblyJoint(name=joint_name, members=specs))

    return solve_assembly(list(members.values()), assembly_joints, should_cancel=should_cancel)
