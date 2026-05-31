"""
Canonical example timber arrangements for joint demonstrations.

Contains factory functions that create standard 4"x5"x4' timber arrangements
used by the example scripts. The joint arrangement dataclasses themselves
live in construction.py.
"""

from typing import Optional, Tuple
from dataclasses import dataclass
from sympy import Integer

from kumiki.timber import (
    Timber, TimberReferenceEnd, TimberLongFace,
    timber_from_directions, normalize_vector,
    RoundTimber, MeshTimber, RegularPolygonTimber,
)
from kumiki.rule import (
    V2, V3, Numeric, create_v2, create_v3, inches, radians,
)
from kumiki.construction import (
    ButtJointTimberArrangement,
    DoubleButtJointTimberArrangement,
    SpliceJointTimberArrangement,
    CornerJointTimberArrangement,
    CrossJointTimberArrangement,
    BraceJointTimberArrangement,
)


# Standard dimensions for canonical example joints: 4" x 5" x 4'
_CANONICAL_EXAMPLE_TIMBER_WIDTH = inches(4)    # X dimension (inches)
_CANONICAL_EXAMPLE_TIMBER_HEIGHT = inches(5)   # Y dimension (inches)
_CANONICAL_EXAMPLE_TIMBER_LENGTH = inches(48)  # 4 feet = 48 inches
_CANONICAL_EXAMPLE_TIMBER_SIZE = create_v2(_CANONICAL_EXAMPLE_TIMBER_WIDTH, _CANONICAL_EXAMPLE_TIMBER_HEIGHT)


CanonicalSquareNominalHalfSizes = Tuple[Numeric, Numeric, Numeric, Numeric]
CanonicalExampleTimber = Timber | MeshTimber | RoundTimber | RegularPolygonTimber


@dataclass(frozen=True)
class PerfectTimberConfig:
    pass


@dataclass(frozen=True)
class RoundTimberConfig:
    diameter: Numeric


@dataclass(frozen=True)
class NominalTimberConfig:
    half_sizes: CanonicalSquareNominalHalfSizes


CanonicalExampleTimberConfig = PerfectTimberConfig | RoundTimberConfig | NominalTimberConfig


def _resolve_canonical_timber_dimensions(
    timber_size: Optional[V2],
    timber_length: Optional[Numeric],
) -> Tuple[V2, Numeric]:
    resolved_size = timber_size if timber_size is not None else _CANONICAL_EXAMPLE_TIMBER_SIZE
    resolved_length = timber_length if timber_length is not None else _CANONICAL_EXAMPLE_TIMBER_LENGTH
    return resolved_size, resolved_length


def _resolve_canonical_timber_config(
    timber_config: Optional[CanonicalExampleTimberConfig],
) -> CanonicalExampleTimberConfig:
    return timber_config if timber_config is not None else PerfectTimberConfig()


def _create_configurable_example_timber(
    *,
    length: Numeric,
    size: V2,
    bottom_position: V3,
    length_direction: V3,
    width_direction: V3,
    ticket: str,
    timber_config: CanonicalExampleTimberConfig,
) -> CanonicalExampleTimber:
    base_timber = timber_from_directions(
        length=length,
        size=size,
        bottom_position=bottom_position,
        length_direction=length_direction,
        width_direction=width_direction,
        ticket=ticket,
    )

    if isinstance(timber_config, PerfectTimberConfig):
        return base_timber

    if isinstance(timber_config, NominalTimberConfig):
        right_half, left_half, front_half, back_half = timber_config.half_sizes
        return Timber(
            length=length,
            size=size,
            transform=base_timber.transform,
            ticket=base_timber.ticket,
            nominal_half_sizes=(create_v2(right_half, left_half), create_v2(front_half, back_half)),
        )

    if isinstance(timber_config, RoundTimberConfig):
        return RoundTimber(
            length=length,
            size=size,
            transform=base_timber.transform,
            ticket=base_timber.ticket,
            diameter=timber_config.diameter,
        )

    raise ValueError(f"Unsupported timber config '{timber_config}'")


def create_canonical_example_butt_joint_timbers(
    position: Optional[V3] = None,
    timber_size: Optional[V2] = None,
    timber_length: Optional[Numeric] = None,
    timber_config: Optional[CanonicalExampleTimberConfig] = None,
) -> ButtJointTimberArrangement:
    """
    Create a canonical butt joint timber arrangement. 
    All canonical example joints are 4"x5"x4' timbers.
    The receiving timber is in the X axis direction with its center point at the position.
    The butt timber is in the Y axis direction with its center point at the position.
    Both timbers have their RIGHT face pointing in the +Z direction.
    
    Args:
        position: Center position of the joint. Defaults to origin.
    """
    if position is None:
        position = create_v3(Integer(0), Integer(0), Integer(0))
    resolved_size, resolved_length = _resolve_canonical_timber_dimensions(timber_size, timber_length)
    resolved_timber_config = _resolve_canonical_timber_config(timber_config)
    
    # Receiving timber: runs along X axis, center at position
    # Center at position means bottom_position is at position - length/2 in length direction
    receiving_bottom = position + create_v3(-resolved_length / Integer(2), Integer(0), Integer(0))
    receiving_timber = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=receiving_bottom,
        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),  # +X direction
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),   # RIGHT face points in +Z
        ticket="receiving_timber",
        timber_config=resolved_timber_config,
    )
    
    # Butt timber: runs along Y axis, center at position
    # The butt timber's top end meets the receiving timber
    butt_bottom = position + create_v3(Integer(0), -resolved_length / Integer(2), Integer(0))
    butt_timber = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=butt_bottom,
        length_direction=create_v3(Integer(0), Integer(1), Integer(0)),  # +Y direction
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),   # RIGHT face points in +Z
        ticket="butt_timber",
        timber_config=resolved_timber_config,
    )
    
    return ButtJointTimberArrangement(
        butt_timber=butt_timber,
        receiving_timber=receiving_timber,
        butt_timber_end=TimberReferenceEnd.TOP,
        front_face_on_butt_timber=TimberLongFace.RIGHT
    )


def create_canonical_example_splice_joint_timbers(
    position: Optional[V3] = None,
    timber_size: Optional[V2] = None,
    timber_length: Optional[Numeric] = None,
    timber_config: Optional[CanonicalExampleTimberConfig] = None,
) -> SpliceJointTimberArrangement:
    """
    Create a canonical splice joint timber arrangement. 
    All canonical example joints are 4"x5"x4' timbers.
    timber1 is to the left of the position and timber2 is to the right of the position.
    both timbers have their centerlines intersecting the position.
    both timbers have their RIGHT face pointing in the +Z direction.
    
    Args:
        position: Center position of the joint. Defaults to origin.
    """
    if position is None:
        position = create_v3(Integer(0), Integer(0), Integer(0))
    resolved_size, resolved_length = _resolve_canonical_timber_dimensions(timber_size, timber_length)
    resolved_timber_config = _resolve_canonical_timber_config(timber_config)
    
    # timber1: to the left of position (runs in +X direction from left)
    # Centerline intersects position means the TOP end is at position
    timber1_bottom = position + create_v3(-resolved_length, Integer(0), Integer(0))
    timber1 = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=timber1_bottom,
        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),  # +X direction
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),   # RIGHT face points in +Z
        ticket="timber1",
        timber_config=resolved_timber_config,
    )
    
    # timber2: to the right of position (runs in +X direction from position)
    # Centerline intersects position means the BOTTOM end is at position
    timber2_bottom = position
    timber2 = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=timber2_bottom,
        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),  # +X direction
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),   # RIGHT face points in +Z
        ticket="timber2",
        timber_config=resolved_timber_config,
    )
    
    return SpliceJointTimberArrangement(
        timber1=timber1,
        timber2=timber2,
        timber1_end=TimberReferenceEnd.TOP,
        timber2_end=TimberReferenceEnd.BOTTOM,
        front_face_on_timber1=TimberLongFace.RIGHT
    )


def create_canonical_example_corner_joint_timbers(
    corner_angle: Optional[Numeric] = None,
    position: Optional[V3] = None,
    timber_size: Optional[V2] = None,
    timber_length: Optional[Numeric] = None,
    timber_config: Optional[CanonicalExampleTimberConfig] = None,
) -> CornerJointTimberArrangement:
    """
    Create a canonical corner joint timber arrangement at an angle.
    All canonical example joints are 4"x5"x4' timbers.
    timber1 points in the +Y direction and has its bottom point at the position.
    timber2 has its bottom point at the position and is rotated CLOCKWISE around the +Z axis by the given angle (that is to say +90deg would be pointing in the +X direction)
    both timbers have their RIGHT face pointing in the +Z direction.
    
    Args:
        corner_angle: Angle in radians for timber2 rotation. Defaults to pi/2 (90 degrees).
        position: Bottom position where timbers meet. Defaults to origin.
    """
    from sympy import sin, cos, pi
    
    # Default to 90 degrees (pi/2 radians)
    if corner_angle is None:
        corner_angle = radians(pi / Integer(2))
    
    if position is None:
        position = create_v3(Integer(0), Integer(0), Integer(0))
    resolved_size, resolved_length = _resolve_canonical_timber_dimensions(timber_size, timber_length)
    resolved_timber_config = _resolve_canonical_timber_config(timber_config)
    
    # timber1: points in +Y direction, bottom at position
    timber1 = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=position,
        length_direction=create_v3(Integer(0), Integer(1), Integer(0)),  # +Y direction
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),   # RIGHT face points in +Z
        ticket="timber1",
        timber_config=resolved_timber_config,
    )
    
    # timber2: rotated CLOCKWISE around +Z axis by corner_angle from +Y direction
    # Clockwise rotation by angle θ: (0,1,0) -> (sin(θ), cos(θ), 0)
    # At θ=90°: sin(90°)=1, cos(90°)=0 -> (1, 0, 0) = +X direction ✓
    timber2_length_direction = create_v3(sin(corner_angle), cos(corner_angle), Integer(0))
    timber2 = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=position,
        length_direction=timber2_length_direction,
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),   # RIGHT face points in +Z
        ticket="timber2",
        timber_config=resolved_timber_config,
    )
    
    return CornerJointTimberArrangement(
        timber1=timber1,
        timber2=timber2,
        timber1_end=TimberReferenceEnd.BOTTOM,
        timber2_end=TimberReferenceEnd.BOTTOM,
        front_face_on_timber1=TimberLongFace.RIGHT
    )


def create_canonical_example_right_angle_corner_joint_timbers(
    position: Optional[V3] = None,
    timber_size: Optional[V2] = None,
    timber_length: Optional[Numeric] = None,
    timber_config: Optional[CanonicalExampleTimberConfig] = None,
) -> CornerJointTimberArrangement:
    """
    Create a canonical corner joint timber arrangement at a right angle (90 degrees).
    All canonical example joints are 4"x5"x4' timbers.
    timber1 points in the +Y direction and has its bottom point at the position.
    timber2 points in the +X direction and has its bottom point at the position.
    both timbers have their RIGHT face pointing in the +Z direction.
    
    Args:
        position: Bottom position where timbers meet. Defaults to origin.
    """
    from sympy import pi
    return create_canonical_example_corner_joint_timbers(
        corner_angle=radians(pi / Integer(2)),
        position=position,
        timber_size=timber_size,
        timber_length=timber_length,
        timber_config=timber_config,
    )


def create_canonical_example_cross_joint_timbers(
    lateral_offset: Numeric = Integer(0),
    position: Optional[V3] = None,
    timber_size: Optional[V2] = None,
    timber_length: Optional[Numeric] = None,
    timber_config: Optional[CanonicalExampleTimberConfig] = None,
) -> CrossJointTimberArrangement:
    """
    Create a canonical cross joint timber arrangement.
    All canonical example joints are 4"x5"x4' timbers.
    timber1 points in the +X direction and has its centerpoint at the position.
    timber2 points in the +Y direction and has its centerpoint at the position + lateral_offset in the +Z direction.
    both timbers have their RIGHT face pointing in the +Z direction.
    
    Args:
        lateral_offset: Vertical offset for timber2 in +Z direction. Defaults to 0.
        position: Center position of the joint. Defaults to origin.
    """
    if position is None:
        position = create_v3(Integer(0), Integer(0), Integer(0))
    resolved_size, resolved_length = _resolve_canonical_timber_dimensions(timber_size, timber_length)
    resolved_timber_config = _resolve_canonical_timber_config(timber_config)
    
    # timber1: points in +X direction, centerpoint at position
    # If centerpoint is at position and length is L, bottom is at position + (-L/2, 0, 0)
    timber1_bottom = position + create_v3(-resolved_length / Integer(2), Integer(0), Integer(0))
    timber1 = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=timber1_bottom,
        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),  # +X direction
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),   # RIGHT face points in +Z
        ticket="timber1",
        timber_config=resolved_timber_config,
    )
    
    # timber2: points in +Y direction, centerpoint at position + (0, 0, lateral_offset)
    # If centerpoint is at position + (0, 0, lateral_offset) and length is L, bottom is at position + (0, -L/2, lateral_offset)
    timber2_bottom = position + create_v3(Integer(0), -resolved_length / Integer(2), lateral_offset)
    timber2 = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=timber2_bottom,
        length_direction=create_v3(Integer(0), Integer(1), Integer(0)),  # +Y direction
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),   # RIGHT face points in +Z
        ticket="timber2",
        timber_config=resolved_timber_config,
    )
    
    return CrossJointTimberArrangement(
        timber1=timber1,
        timber2=timber2
    )


def create_canonical_example_brace_joint_timbers(
    position: Optional[V3] = None,
    timber_size: Optional[V2] = None,
    timber_length: Optional[Numeric] = None,
    timber_config: Optional[CanonicalExampleTimberConfig] = None,
) -> BraceJointTimberArrangement:
    """
    Create a canonical brace joint timber arrangement.
    All canonical example joints are 4"x5"x4' timbers.
    
    Creates a corner joint (two 90-degree timbers) plus a third brace timber
    that connects the midpoints of the two corner timbers.
    
    timber1 points in the +Y direction and has its bottom point at the position.
    timber2 points in the +X direction and has its bottom point at the position.
    Both timbers have their RIGHT face pointing in the +Z direction.
    
    The brace timber connects the midpoints of timber1 and timber2,
    running diagonally from timber1's midpoint to timber2's midpoint.
    The brace timber is aligned in the same plane as the corner timbers
    (RIGHT face pointing in +Z direction).
    
    Args:
        position: Bottom position where corner timbers meet. Defaults to origin.
    """
    from sympy import sqrt
    
    if position is None:
        position = create_v3(Integer(0), Integer(0), Integer(0))
    resolved_size, resolved_length = _resolve_canonical_timber_dimensions(timber_size, timber_length)
    resolved_timber_config = _resolve_canonical_timber_config(timber_config)
    
    # Create the two corner timbers (same as right angle corner joint)
    corner_arrangement = create_canonical_example_right_angle_corner_joint_timbers(
        position=position,
        timber_size=resolved_size,
        timber_length=resolved_length,
        timber_config=resolved_timber_config,
    )
    timber1 = corner_arrangement.timber1
    timber2 = corner_arrangement.timber2
    
    # Calculate midpoints of timber1 and timber2
    # timber1 midpoint: position + (length/2) * (0, 1, 0) = position + (0, length/2, 0)
    timber1_midpoint = position + create_v3(
        Integer(0),
        resolved_length / Integer(2),
        Integer(0)
    )
    
    # timber2 midpoint: position + (length/2) * (1, 0, 0) = position + (length/2, 0, 0)
    timber2_midpoint = position + create_v3(
        resolved_length / Integer(2),
        Integer(0),
        Integer(0)
    )
    
    # Calculate brace direction (from timber1 midpoint to timber2 midpoint)
    brace_direction_vector = timber2_midpoint - timber1_midpoint
    # Normalize the direction
    brace_length_direction = normalize_vector(brace_direction_vector)
    
    # Calculate the length of the brace (distance between midpoints)
    # Distance = sqrt((length/2)^2 + (length/2)^2) = length / sqrt(2)
    brace_length = resolved_length / sqrt(Integer(2))
    
    # Create the brace timber
    # Bottom position is at timber1's midpoint
    # Length direction points from timber1 midpoint to timber2 midpoint
    # RIGHT face points in +Z direction (same plane as corner timbers)
    brace_timber = _create_configurable_example_timber(
        length=brace_length,
        size=resolved_size,
        bottom_position=timber1_midpoint,
        length_direction=brace_length_direction,
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # RIGHT face points in +Z
        ticket="brace_timber",
        timber_config=resolved_timber_config,
    )
    
    return BraceJointTimberArrangement(
        timber1=timber1,
        timber2=timber2,
        brace_timber=brace_timber,
        timber1_end=corner_arrangement.timber1_end,
        timber2_end=corner_arrangement.timber2_end,
        front_face_on_timber1=corner_arrangement.front_face_on_timber1
    )


def create_canonical_example_opposing_double_butt_joint_timbers(
    position: Optional[V3] = None,
    timber_size: Optional[V2] = None,
    timber_length: Optional[Numeric] = None,
    timber_config: Optional[CanonicalExampleTimberConfig] = None,
) -> DoubleButtJointTimberArrangement:
    """
    Create a canonical opposing double butt joint timber arrangement.
    All canonical example joints are 4"x5"x4' timbers.
    The receiving timber (post) runs along the X axis with its center at the position.
    butt_timber_1 runs along +Y with its TOP end meeting the post center.
    butt_timber_2 runs along -Y with its TOP end meeting the post center (antiparallel).
    All timbers have their RIGHT face pointing in the +Z direction.

    Args:
        position: Center position of the joint. Defaults to origin.
    """
    if position is None:
        position = create_v3(Integer(0), Integer(0), Integer(0))
    resolved_size, resolved_length = _resolve_canonical_timber_dimensions(timber_size, timber_length)
    resolved_timber_config = _resolve_canonical_timber_config(timber_config)

    # Receiving timber (post): runs along X axis, center at position
    receiving_bottom = position + create_v3(-resolved_length / Integer(2), Integer(0), Integer(0))
    receiving_timber = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=receiving_bottom,
        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),
        ticket="receiving_timber",
        timber_config=resolved_timber_config,
    )

    # butt_timber_1: runs along +Y, TOP end meets post center
    butt1_bottom = position + create_v3(Integer(0), -resolved_length / Integer(2), Integer(0))
    butt_timber_1 = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=butt1_bottom,
        length_direction=create_v3(Integer(0), Integer(1), Integer(0)),
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),
        ticket="butt_timber_1",
        timber_config=resolved_timber_config,
    )

    # butt_timber_2: runs along -Y, TOP end meets post center (antiparallel to butt_timber_1)
    butt2_bottom = position + create_v3(Integer(0), resolved_length / Integer(2), Integer(0))
    butt_timber_2 = _create_configurable_example_timber(
        length=resolved_length,
        size=resolved_size,
        bottom_position=butt2_bottom,
        length_direction=create_v3(Integer(0), Integer(-1), Integer(0)),
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),
        ticket="butt_timber_2",
        timber_config=resolved_timber_config,
    )

    return DoubleButtJointTimberArrangement(
        butt_timber_1=butt_timber_1,
        butt_timber_2=butt_timber_2,
        receiving_timber=receiving_timber,
        butt_timber_1_end=TimberReferenceEnd.TOP,
        butt_timber_2_end=TimberReferenceEnd.TOP,
        front_face_on_butt_timber_1=TimberLongFace.RIGHT,
    )
