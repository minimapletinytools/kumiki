"""
Kumiki - Timber construction functions
Contains functions for creating and manipulating timbers
"""

import warnings
from kumiki.timber import *
from kumiki.rule import *
from kumiki.measuring import *
from kumiki.timber_shavings import *
from kumiki.ticket import TimberTicket
from typing import Dict, Any
# TODO switch to warnings.deprecated when upgrading to Python 3.13
from typing_extensions import deprecated


# ============================================================================
# Joint Construction Data Structures
# ============================================================================
class StickoutReference(Enum):
    """
    Defines how stickout is measured relative to timber connection points.
    
    CENTER_LINE: Stickout measured from centerline of the timber (default)
        joined timber
        | |
        |||===== created timber
        | |
    
    INSIDE: Stickout measured from inside face of the timber
        joined timber
        | |
        | |===== created timber
        | |
    
    OUTSIDE: Stickout measured from outside face of the timber
        joined timber
        | |
        |====== created timber
        | |
    """
    CENTER_LINE = 1
    INSIDE = 2
    OUTSIDE = 3

# TODO this is really only needed for JoinTimbers so move it near that function
# TODO rename to ButtStickout or something like that...
@dataclass(frozen=True)
class Stickout:
    """
    Defines how much a timber extends beyond connection points.
    
    For symmetric stickout, set stickout1 = stickout2.
    For asymmetric stickout, use different values.
    Default is no stickout (0, 0) from CENTER_LINE.
    
    StickoutReference modes:
    
    CENTER_LINE: Stickout measured from centerline of the joined timber
        joined timber
        | |
        |||===== created timber
        | |
    
    INSIDE: Stickout measured from inside face of the joined timber
        joined timber
        | |
        | |===== created timber
        | |
    
    OUTSIDE: Stickout measured from outside face of the joined timber
        joined timber
        | |
        |====== created timber
        | |
    
    Args:
        stickout1: Extension beyond the first connection point (default: 0)
        stickout2: Extension beyond the second connection point (default: 0)
        stickoutReference1: How stickout1 is measured (default: CENTER_LINE)
        stickoutReference2: How stickout2 is measured (default: CENTER_LINE)
    
    Examples:
        # Symmetric stickout from centerline
        s = Stickout.symmetric(scalar(1, 5))  # Both sides extend 0.2m from centerline
        
        # No stickout
        s = Stickout.nostickout()  # Both sides are 0
        
        # Asymmetric stickout
        s = Stickout(scalar(1, 10), scalar(2, 5))  # Left extends 0.1m, right extends 0.4m from centerline
        
        # Stickout from outside faces
        s = Stickout(scalar(1, 10), scalar(1, 5), StickoutReference.OUTSIDE, StickoutReference.OUTSIDE)
    """
    stickout1: Numeric = scalar(0)
    stickout2: Numeric = scalar(0)
    # TODO don't make these optional types just make them default to CENTER_LINE
    stickoutReference1: Optional['StickoutReference'] = None
    stickoutReference2: Optional['StickoutReference'] = None
    
    def __post_init__(self):
        """Set default stickout references if not provided."""
        if self.stickoutReference1 is None:
            object.__setattr__(self, 'stickoutReference1', StickoutReference.CENTER_LINE)
        if self.stickoutReference2 is None:
            object.__setattr__(self, 'stickoutReference2', StickoutReference.CENTER_LINE)
    
    @classmethod
    def symmetric(cls, value: Numeric, reference: Optional['StickoutReference'] = None) -> 'Stickout':
        """
        Create a symmetric stickout where both sides extend by the same amount.
        
        Args:
            value: The stickout distance for both sides
            reference: How stickout is measured (default: CENTER_LINE)
            
        Returns:
            Stickout instance with stickout1 = stickout2 = value
        """
        if reference is None:
            reference = StickoutReference.CENTER_LINE
        return cls(value, value, reference, reference)
    
    @classmethod
    def nostickout(cls) -> 'Stickout':
        """
        Create a stickout with no extension on either side.
        
        Returns:
            Stickout instance with stickout1 = stickout2 = 0
        """
        return cls(scalar(0), scalar(0))


# ============================================================================
# Timber Creation Functions
# ============================================================================


def create_timber(bottom_position: V3, length: Numeric, size: V2, 
                  length_direction: Direction3D, width_direction: Direction3D, ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    """
    Creates a timber at bottom_position with given dimensions and rotates it 
    to the length_direction and width_direction

    AGENT NOTE: AVOID this function if possible, prefer methods like join_timber, attach_timber, create_*_timber_on_footprint, or even create_axis_aligned_timber, which are more robust and easier to use.
    
    Args:
        bottom_position: Position of the bottom point of the timber
        length: Length of the timber
        size: Cross-sectional size (width, height)
        length_direction: Direction vector for the timber's length axis
        width_direction: Direction vector for the timber's width axis
        ticket: Optional ticket for this timber (can be Ticket object or string name, used for rendering/debugging)
    """
    return timber_from_directions(length, size, bottom_position, length_direction, width_direction, ticket=ticket)

def create_axis_aligned_timber(bottom_position: V3, length: Numeric, size: V2,
                              length_direction: TimberFace, width_direction: Optional[TimberFace] = None, 
                              ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    """
    Creates an axis-aligned timber using TimberFace to reference directions
    in the world coordinate system.

    AGENT NOTE: AVOID this function if possible, prefer methods like join_timber, attach_face/plane_aligned_timber, create_*_timber_on_footprint, or even create_axis_aligned_timber, which are more robust and easier to use.
    
    Args:
        bottom_position: Position of the bottom point of the timber
        length: Length of the timber
        size: Cross-sectional size (width, height)
        length_direction: Direction for the timber's length axis
        width_direction: Optional direction for the timber's width axis.
                        If not provided, defaults to RIGHT (+X) unless length_direction
                        is RIGHT, in which case TOP (+Z) is used.
        ticket: Optional ticket for this timber (can be Ticket object or string name, used for rendering/debugging)
    
    Returns:
        New timber with the specified axis-aligned orientation
    """
    # Convert TimberFace to direction vectors
    length_vec = length_direction.get_direction()
    
    # Determine width direction if not provided
    if width_direction is None:
        # Default to RIGHT (+X) unless length is in +X direction
        if length_direction == TimberFace.RIGHT:
            width_direction = TimberFace.TOP
        else:
            width_direction = TimberFace.RIGHT
    
    if length_direction == TimberFace.BOTTOM:
        # print a warning, this is usually not what you want
        warnings.warn("Creating an axis-aligned timber with length_direction == BOTTOM. This is usually not what you want. Consider using length_direction == TOP instead.")
    
    width_vec = width_direction.get_direction()
    
    return create_timber(bottom_position, length, size, length_vec, width_vec, ticket=ticket)

def create_vertical_timber_on_footprint_corner(footprint: Footprint, corner_index: int, 
                                               length: Numeric, location_type: FootprintLocation,
                                               size: V2, ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    """
    Creates a vertical timber (post) on a footprint boundary corner.
    
    The post is positioned on an orthogonal boundary corner (where two boundary sides 
    are perpendicular) according to the location type:
    
    Location types:
    - INSIDE: Post has one vertex of bottom face on the boundary corner, with 2 edges 
              aligned with the 2 boundary sides, post extends inside the boundary
    - OUTSIDE: Post positioned with opposite vertex on the boundary corner, extends outside
    - CENTER: Post center is on the boundary corner, with 2 edges parallel to boundary sides
    
    Args:
        footprint: The footprint to place the timber on
        corner_index: Index of the boundary corner
        length: Length of the vertical timber (height)
        location_type: Where to position the timber relative to the boundary corner
        size: Timber size (width, depth) as a 2D vector
        ticket: Optional ticket for this timber (can be Ticket object or string name, used for rendering/debugging)
        
    Returns:
        Timber positioned vertically on the footprint boundary corner
    """
    # Get the boundary corner point
    corner = footprint.corners[corner_index]
    
    # Get the two boundary sides meeting at this corner
    # Previous side: from corner_index-1 to corner_index
    # Next side: from corner_index to corner_index+1
    n_corners = len(footprint.corners)
    prev_corner = footprint.corners[(corner_index - 1) % n_corners]
    next_corner = footprint.corners[(corner_index + 1) % n_corners]
    
    # Calculate direction vectors for the two sides
    # Keep as exact values - don't convert to float
    outgoing_dir = Matrix([next_corner[0] - corner[0], 
                          next_corner[1] - corner[1]])
    
    # Normalize the direction vector
    from sympy import sqrt
    outgoing_len_sq = outgoing_dir[0]**2 + outgoing_dir[1]**2
    outgoing_len = sqrt(outgoing_len_sq)
    outgoing_dir_normalized = outgoing_dir / outgoing_len
    
    # Timber dimensions - keep as exact values from size parameter
    timber_width = size[0]   # Face direction (X-axis of timber)
    timber_depth = size[1]   # Height direction (Y-axis of timber)
    
    # Vertical direction (length)
    length_direction = create_v3(scalar(0), scalar(0), scalar(1))
    
    # Align timber face direction with outgoing boundary side
    # Face direction is in the XY plane along the outgoing side
    width_direction = create_v3(outgoing_dir_normalized[0], outgoing_dir_normalized[1], scalar(0))
    
    # Calculate bottom position based on location type
    # Keep corner coordinates exact
    corner_x = corner[0]
    corner_y = corner[1]
    
    # For orthogonal corners, the two in-boundary axes are:
    # 1) outgoing side direction (corner -> next_corner)
    # 2) previous side direction from corner (corner -> prev_corner)
    prev_dir = Matrix([prev_corner[0] - corner[0], prev_corner[1] - corner[1]])
    prev_len_sq = prev_dir[0]**2 + prev_dir[1]**2
    prev_len = sqrt(prev_len_sq)
    prev_dir_normalized = prev_dir / prev_len

    if location_type == FootprintLocation.INSIDE:
        # Center-origin timber: move center inward by half size in both axes.
        offset_x = timber_width / scalar(2) * outgoing_dir_normalized[0] + timber_depth / scalar(2) * prev_dir_normalized[0]
        offset_y = timber_width / scalar(2) * outgoing_dir_normalized[1] + timber_depth / scalar(2) * prev_dir_normalized[1]
        bottom_position = create_v3(corner_x + offset_x, corner_y + offset_y, scalar(0))

    elif location_type == FootprintLocation.OUTSIDE:
        # Center-origin timber: move center outward by half size in both axes.
        offset_x = -timber_width / scalar(2) * outgoing_dir_normalized[0] - timber_depth / scalar(2) * prev_dir_normalized[0]
        offset_y = -timber_width / scalar(2) * outgoing_dir_normalized[1] - timber_depth / scalar(2) * prev_dir_normalized[1]
        bottom_position = create_v3(corner_x + offset_x, corner_y + offset_y, scalar(0))

    else:  # CENTER
        # Center of bottom face lies on the boundary corner.
        bottom_position = create_v3(corner_x, corner_y, scalar(0))
    
    return create_timber(bottom_position, length, size, length_direction, width_direction, ticket=ticket)

def create_vertical_timber_on_footprint_side(footprint: Footprint, side_index: int, 
                                            distance_along_side: Numeric,
                                            length: Numeric, location_type: FootprintLocation, 
                                            size: V2, ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    """
    Creates a vertical timber (post) positioned at a point along a footprint boundary side.
    
    The post is placed at a specified distance along the boundary side from the starting corner.
    
    Location types:
    - INSIDE: One edge of bottom face lies on boundary side, center of edge at the point, post extends inside
    - OUTSIDE: One edge of bottom face lies on boundary side, center of edge at the point, post extends outside
    - CENTER: Center of bottom face is on the point, 2 edges of bottom face parallel to boundary side
    
    Args:
        footprint: The footprint to place the timber on
        side_index: Index of the boundary side (from corner[side_index] to corner[side_index+1])
        distance_along_side: Distance from the starting corner along the side (0 = at start corner)
        length: Length of the vertical timber (height)
        location_type: Where to position the timber relative to the boundary side
        size: Timber size (width, depth) as a 2D vector
        ticket: Optional ticket for this timber (can be Ticket object or string name, used for rendering/debugging)
        
    Returns:
        Timber positioned vertically at the specified point on the footprint boundary side
    """
    # Get the boundary side endpoints
    start_corner = footprint.corners[side_index]
    end_corner = footprint.corners[(side_index + 1) % len(footprint.corners)]
    
    # Calculate direction along the boundary side - keep exact
    side_dir = Matrix([end_corner[0] - start_corner[0], 
                       end_corner[1] - start_corner[1]])
    
    # Normalize the direction vector
    from sympy import sqrt
    side_len_sq = side_dir[0]**2 + side_dir[1]**2
    side_len = sqrt(side_len_sq)
    side_dir_normalized = side_dir / side_len
    
    # Calculate the point along the side
    point_x = start_corner[0] + side_dir_normalized[0] * distance_along_side
    point_y = start_corner[1] + side_dir_normalized[1] * distance_along_side
    
    # Calculate inward normal (perpendicular to side, pointing inward)
    # For a 2D vector (dx, dy), the perpendicular is (-dy, dx) or (dy, -dx)
    # We need to determine which one points inward
    perp_x = -side_dir_normalized[1]  # Left perpendicular
    perp_y = side_dir_normalized[0]
    
    # Test if this perpendicular points inward
    test_point = Matrix([point_x + perp_x * OFFSET_TEST_POINT,
                        point_y + perp_y * OFFSET_TEST_POINT])
    
    if footprint.contains_point(test_point):
        # Left perpendicular points inward
        inward_x = perp_x
        inward_y = perp_y
    else:
        # Right perpendicular points inward
        inward_x = side_dir_normalized[1]
        inward_y = -side_dir_normalized[0]
    
    # Timber dimensions - keep as exact values from size parameter
    timber_width = size[0]   # Width in face direction (parallel to boundary side)
    timber_depth = size[1]   # Depth perpendicular to boundary side
    
    # Vertical direction (length)
    length_direction = create_v3(scalar(0), scalar(0), scalar(1))
    
    # Face direction is parallel to the boundary side
    width_direction = create_v3(side_dir_normalized[0], side_dir_normalized[1], scalar(0))
    
    # Calculate bottom position based on location type
    if location_type == FootprintLocation.CENTER:
        # Center of bottom face is on the point
        # No offset needed since timber local origin is at center of bottom face
        bottom_position = create_v3(point_x, point_y, scalar(0))
        
    elif location_type == FootprintLocation.INSIDE:
        # One edge of bottom face lies on boundary side
        # Center of that edge is at the point
        # Post extends inside (in direction of inward normal)
        # Offset the center by half depth in the inward direction
        bottom_position = create_v3(point_x + inward_x * timber_depth / scalar(2), 
                                         point_y + inward_y * timber_depth / scalar(2), 
                                         scalar(0))
        
    else:  # OUTSIDE
        # One edge of bottom face lies on boundary side
        # Center of that edge is at the point
        # Post extends outside (opposite of inward normal)
        # Offset the center by half depth in the outward direction
        bottom_position = create_v3(point_x - inward_x * timber_depth / scalar(2), 
                                         point_y - inward_y * timber_depth / scalar(2), 
                                         scalar(0))
    
    return create_timber(bottom_position, length, size, length_direction, width_direction, ticket=ticket)

def create_horizontal_timber_on_footprint(footprint: Footprint, corner_index: int,
                                        location_type: FootprintLocation, 
                                        size: V2,
                                        length: Optional[Numeric] = None, ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    """
    Creates a horizontal timber (mudsill) on the footprint boundary side.
    
    The mudsill runs from corner_index to corner_index + 1 along the boundary side.
    With the face ends of the mudsill timber starting/ending on the footprint corners.
    
    Location types:
    - INSIDE: One edge of the timber lies on the boundary side, timber is on the inside
    - OUTSIDE: One edge of the timber lies on the boundary side, timber is on the outside
    - CENTER: The centerline of the timber lies on the boundary side
    
    Args:
        footprint: The footprint to place the timber on
        corner_index: Index of the starting boundary corner
        location_type: Where to position the timber relative to the boundary side
        size: Timber size (width, height) as a 2D vector
        length: Length of the timber (optional; if not provided, uses boundary side length)
        ticket: Optional ticket for this timber (can be Ticket object or string name, used for rendering/debugging)
        
    Returns:
        Timber positioned on the footprint boundary side
    """
    # Get the footprint points
    start_point = footprint.corners[corner_index]
    end_point = footprint.corners[(corner_index + 1) % len(footprint.corners)]
        
    length_direction = normalize_vector(Matrix([end_point[0] - start_point[0], end_point[1] - start_point[1], 0]))

    # Calculate length from boundary side if not provided
    if length is None:
        from sympy import sqrt
        dx = end_point[0] - start_point[0]
        dy = end_point[1] - start_point[1]
        length = sqrt(dx**2 + dy**2)
    
    # Get the inward normal from the footprint
    inward_normal = footprint.get_inward_normal(corner_index)
    
    # Face direction is up (Z+)
    width_direction = create_v3(scalar(0), scalar(0), scalar(1))
    
    # The timber's orientation will be:
    #   X-axis (width/size[0]) = width_direction = (0, 0, 1) = vertical (up)
    #   Y-axis (height/size[1]) = length × face = perpendicular to boundary in XY plane
    #   Z-axis (length) = length_direction = along boundary side
    # Therefore, size[1] is the dimension perpendicular to the boundary
    timber_height = size[1]
    
    # Calculate bottom position based on location type
    # Start at the start_point on the boundary side - keep exact
    bottom_position = create_v3(start_point[0], start_point[1], scalar(0))
    
    # Apply offset based on location type
    if location_type == FootprintLocation.INSIDE:
        # Position so one edge lies on the boundary side, timber extends inward
        # Move the centerline inward by half the timber height (perpendicular dimension)
        bottom_position = bottom_position + inward_normal * (timber_height / scalar(2))
    elif location_type == FootprintLocation.OUTSIDE:
        # Position so one edge lies on the boundary side, timber extends outward
        # Move the centerline outward by half the timber height (perpendicular dimension)
        bottom_position = bottom_position - inward_normal * (timber_height / scalar(2))
    # For CENTER, no offset needed - centerline is already on the boundary side
    
    return create_timber(bottom_position, length, size, length_direction, width_direction, ticket=ticket)

def stretch_timber(timber: Timber, end: TimberEnd, overlap_length: Numeric, 
                  extend_length: Numeric) -> Timber:
    """
    Creates a new timber extending the original timber by a given length.

    The original timber is conceptually discarded and replaced with a new timber that is the original timber plus the extension.

    Args:
        end: The end of the timber to extend
        overlap_length: Length of timber to overlap with existing timber
        extend_length: Length of timber to extend beyond the end of the original timber (does not include the overlap length)
    """
    assert isinstance(end, TimberEnd), f"expected TimberEnd, got {type(end).__name__}"
    # Calculate new position based on end
    if end == TimberEnd.TOP:
        # Extend from top
        extension_vector = timber.get_length_direction_global() * (timber.length - overlap_length)
        new_bottom_position = timber.get_bottom_position_global() + extension_vector
    else:  # BOTTOM
        # Extend from bottom
        extension_vector = timber.get_length_direction_global() * extend_length
        new_bottom_position = timber.get_bottom_position_global() - extension_vector
    
    # Create new timber with extended length
    new_length = timber.length + extend_length + overlap_length
    
    return timber_from_directions(new_length, timber.size, new_bottom_position, 
                                   timber.get_length_direction_global(), timber.get_width_direction_global())

# TODO add some sorta splice stickout parameter
def split_timber(
    timber: Timber, 
    distance_from_bottom: Numeric,
    ticket1: Optional[Union[TimberTicket, str]] = None,
    ticket2: Optional[Union[TimberTicket, str]] = None
) -> Tuple[Timber, Timber]:
    """
    Split a timber into two timbers at the specified distance from the bottom.
    
    The original timber is conceptually discarded and replaced with two new timbers:
    - The first timber extends from the original bottom to the split point
    - The second timber extends from the split point to the original top
    
    Both timbers maintain the same cross-sectional size and orientation as the original.
    You will often follow this with a splice joint to join the two timbers together.
    
    Args:
        timber: The timber to split
        distance_from_bottom: Distance along the timber's length where to split (0 < distance < timber.length)
        ticket1: Optional ticket for the bottom timber (defaults to "{original_name}_bottom")
        ticket2: Optional ticket for the top timber (defaults to "{original_name}_top")
        
    Returns:
        Tuple of (bottom_timber, top_timber) where:
        - bottom_timber starts at the same position as the original
        - top_timber starts at the top end of bottom_timber
        
    Example:
        If a timber has length 10 and is split at distance 3:
        - bottom_timber has length 3, same origin as original
        - top_timber has length 7, origin at distance 3 from original origin
    """
    # Validate input
    assert 0 < distance_from_bottom < timber.length, \
        f"Split distance {distance_from_bottom} must be between 0 and {timber.length}"
    
    # Determine tickets for the split timbers
    bottom_ticket = ticket1 if ticket1 is not None else f"{timber.ticket.path}/bottom"
    top_ticket = ticket2 if ticket2 is not None else f"{timber.ticket.path}/top"
    
    # Create first timber (bottom part)
    bottom_timber = timber_from_directions(
        length=distance_from_bottom,
        size=create_v2(timber.size[0], timber.size[1]),
        bottom_position=timber.get_bottom_position_global(),
        length_direction=timber.get_length_direction_global(),
        width_direction=timber.get_width_direction_global(),
        ticket=bottom_ticket
    )
    
    # Calculate the bottom position of the second timber
    # It's at the top of the first timber
    top_of_first = timber.get_bottom_position_global() + distance_from_bottom * timber.get_length_direction_global()
    
    # Create second timber (top part)
    top_timber = timber_from_directions(
        length=timber.length - distance_from_bottom,
        size=create_v2(timber.size[0], timber.size[1]),
        bottom_position=top_of_first,
        length_direction=timber.get_length_direction_global(),
        width_direction=timber.get_width_direction_global(),
        ticket=top_ticket
    )
    
    return (bottom_timber, top_timber)

def attach_timber(
    original_timber: TimberLike,
    size: V2, 
    attached_timber_direction: Direction3D,
    attached_timber_length: Numeric,
    attached_timber_opposite_length: Numeric = scalar(0),
    attached_timber_width_direction: Optional[Direction3D] = None,
    attached_timber_end_that_points_towards_original_timber: TimberEnd = TimberEnd.BOTTOM,
    original_timber_end_to_measure_from_for_length_position: TimberEnd = TimberEnd.BOTTOM,
    length_position_measurement: Numeric = scalar(0),
    lateral_offset: Numeric = scalar(0),
    ticket: Optional[Union[TimberTicket, str]] = None,
):
    """
    NOTE this function is perhaps not so useful in practice, it's mainly here for completeness. Perhaps there are some cases where it's a better alternative to create_timber

    Creates a timber that is attached to ``original_timber``.

    The original timber is referred to as "original_timber" and the new timber as "attached_timber". 

    ## Positioning

    The attached timber's ``attached_timber_end_that_points_towards_original_timber`` end position is ``length_position_measurement`` away from 
    ``original_timber_end_to_measure_from_for_length_position`` and then ``lateral_offset`` away from the centerline of the original timber, 
    measured in the direction 
    length axis of the original timber CROSS length axis of the created attached timber

    ## Orientation

    The attached timber's orientation is such that its length axis is in the attached_timber_direction direction
    and its right face best aligns with ``attached_timber_right_direction``.
    if ``attached_timber_right_direction`` is None then the direction of the TOP face of the original timber is used instead.

    Returns:
        The new attached timber, face-aligned with and positioned relative to the original timber.
    """
    # ---- type checks ----
    assert isinstance(original_timber, PerfectTimberWithin), \
        f"original_timber must be a timber (PerfectTimberWithin), got {type(original_timber).__name__}"
    assert isinstance(attached_timber_end_that_points_towards_original_timber, TimberEnd), \
        f"attached_timber_end_that_points_towards_original_timber must be TimberEnd, got {type(attached_timber_end_that_points_towards_original_timber).__name__}"
    assert isinstance(original_timber_end_to_measure_from_for_length_position, TimberEnd), \
        f"original_timber_end_to_measure_from_for_length_position must be TimberEnd, got {type(original_timber_end_to_measure_from_for_length_position).__name__}"

    # point_dir is the direction the attached timber points; length_dir is its +length (bottom->top),
    # which flips when the TOP end is the one sitting against the original timber.
    point_dir = normalize_vector(attached_timber_direction)
    if attached_timber_end_that_points_towards_original_timber == TimberEnd.BOTTOM:
        length_dir = point_dir
    else:
        length_dir = -point_dir

    # ---- reference point: a position on the original timber's centerline, then offset laterally ----
    if original_timber_end_to_measure_from_for_length_position == TimberEnd.BOTTOM:
        reference = locate_position_on_centerline_from_bottom(original_timber, length_position_measurement).position
    else:  # TOP
        reference = locate_position_on_centerline_from_top(original_timber, length_position_measurement).position

    if lateral_offset != scalar(0):
        # lateral direction = original length axis CROSS the attached timber's length axis
        original_length_dir = original_timber.get_length_direction_global()
        assert not are_vectors_parallel(length_dir, original_length_dir), \
            "lateral_offset requires the attached timber to not be parallel to the original timber's length"
        lateral_dir = normalize_vector(cross_product(original_length_dir, length_dir))
        reference = reference + lateral_dir * lateral_offset

    # ---- extend along the pointing direction and build the timber ----
    attached_total_length = attached_timber_length + attached_timber_opposite_length
    assert safe_compare(attached_total_length, scalar(0), Comparison.GT), \
        "attached timber total length (attached_timber_length + attached_timber_opposite_length) must be positive"

    center = reference + point_dir * (attached_timber_length - attached_timber_opposite_length) / scalar(2)
    bottom_position = center - length_dir * (attached_total_length / scalar(2))

    # default the width direction to the original timber's length (its TOP face direction)
    width_direction = attached_timber_width_direction if attached_timber_width_direction is not None \
        else original_timber.get_length_direction_global()

    return create_timber(
        bottom_position=bottom_position,
        length=attached_total_length,
        size=size,
        length_direction=length_dir,
        width_direction=width_direction,
        ticket=ticket,
    )


def attach_plane_aligned_timber(
    original_timber: TimberLike,
    size: V2, # always width, height in the local coordinates of the created attached timber
    original_timber_long_face_that_attached_timber_points_to: TimberLongFace,
    attached_timber_angle: Numeric, # angle between the length axis of the original timber and attached timber, note that this flips depending on attached_timber_end_that_points_towards_original_timber
    attached_timber_length_or_target: Union[Numeric, TimberLike],
    attached_timber_stickout: Stickout = Stickout.nostickout(),
    attached_timber_end_that_points_towards_original_timber: TimberEnd = TimberEnd.BOTTOM,
    original_timber_end_to_measure_from_for_length_position: TimberEnd = TimberEnd.BOTTOM,
    attached_timber_long_face_to_measure_to_for_length_position: Union[TimberLongFace, TimberCenterline] = TimberCenterline.CENTERLINE,
    length_position_measurement: Numeric = scalar(0),
    original_timber_face_to_measure_from_for_lateral_position: Union[TimberFace, TimberCenterline] = TimberCenterline.CENTERLINE,
    attached_timber_long_face_to_measure_to_for_lateral_position: Union[TimberLongFace, TimberCenterline] = TimberCenterline.CENTERLINE,
    lateral_position_measurement: Numeric = scalar(0),
    ticket: Optional[Union[TimberTicket, str]] = None,
) -> Timber:
    """
    Creates a timber that is plane-aligned with and attached to ``original_timber`` at an angle.

    Generalizes :func:`attach_face_aligned_timber`: the attached timber's length axis lies in the
    plane spanned by the original timber's length axis and the normal of
    ``original_timber_long_face_that_attached_timber_points_to`` (the face it points out of), making
    an angle of ``attached_timber_angle`` with the original timber's length axis. The attached
    timber stays plane-aligned with the original (two of its long faces remain parallel to the
    original's lateral faces). ``attach_face_aligned_timber`` is the ``attached_timber_angle == pi/2``
    (perpendicular) case.

    ``attached_timber_end_that_points_towards_original_timber`` chooses which end of the attached
    timber sits on the original-timber side; note that this flips the realized angle to
    ``pi - attached_timber_angle``.

    ## Extents

    ``attached_timber_length_or_target`` places the target end (the end pointing away from the
    original timber):
    - a numeric length extends the timber along its (tilted) length axis, measured from the
      original timber's centerline.
    - a timber extends the attached timber until its centerline just touches the target timber's
      reference feature selected by ``attached_timber_stickout.stickoutReference2``, taken on the
      target's silhouette projected onto the plane spanned by the original timber's length axis
      and the attach direction: its CENTER_LINE, or the near (INSIDE) / far (OUTSIDE) boundary of
      the silhouette (for a target plane-aligned with that plane these are its long faces; for a
      rotated target, its projected corner edges). If the target's centerline is parallel to the
      lateral axis it projects to a single point, which is dropped perpendicularly onto the
      attached timber's length axis. ``stickout2`` then extends the target end beyond that
      feature. ``stickout2`` is ignored (with a warning if set) when a numeric length is given
      instead.

    ``attached_timber_stickout`` places the start end (the end that attaches to the original
    timber): the start end is where the attached timber's centerline just touches the original
    timber's feature selected by ``stickoutReference1`` — its CENTER_LINE (default), the INSIDE
    face (the face the attached timber points out of), or the OUTSIDE face (the opposite face) —
    extended by ``stickout1`` beyond it.

    Everything else follows attach_face_aligned_timber:
    - the length-position is measured along the original timber's length axis from
      ``original_timber_end_to_measure_from_for_length_position`` to
      ``attached_timber_long_face_to_measure_to_for_length_position`` (or orthogonally to its centerline).
    - the lateral-position is measured along the lateral axis from
      ``original_timber_face_to_measure_from_for_lateral_position`` to
      ``attached_timber_long_face_to_measure_to_for_lateral_position`` (or orthogonally to its centerline).

    All measurements are taken from the perfect timber within of the original and attached timber.

    Returns:
        The new attached timber, plane-aligned with and positioned relative to the original timber.
    """
    # ---- type checks ----
    assert isinstance(original_timber, PerfectTimberWithin), \
        f"original_timber must be a timber (PerfectTimberWithin), got {type(original_timber).__name__}"
    assert isinstance(original_timber_long_face_that_attached_timber_points_to, TimberLongFace), \
        f"original_timber_long_face_that_attached_timber_points_to must be TimberLongFace, got {type(original_timber_long_face_that_attached_timber_points_to).__name__}"
    assert isinstance(attached_timber_length_or_target, (PerfectTimberWithin, Expr, int)), \
        f"attached_timber_length_or_target must be a numeric length or a timber (PerfectTimberWithin), got {type(attached_timber_length_or_target).__name__}"
    assert isinstance(attached_timber_stickout, Stickout), \
        f"attached_timber_stickout must be Stickout, got {type(attached_timber_stickout).__name__}"
    assert isinstance(attached_timber_end_that_points_towards_original_timber, TimberEnd), \
        f"attached_timber_end_that_points_towards_original_timber must be TimberEnd, got {type(attached_timber_end_that_points_towards_original_timber).__name__}"
    assert isinstance(original_timber_end_to_measure_from_for_length_position, TimberEnd), \
        f"original_timber_end_to_measure_from_for_length_position must be TimberEnd, got {type(original_timber_end_to_measure_from_for_length_position).__name__}"
    assert isinstance(attached_timber_long_face_to_measure_to_for_length_position, (TimberLongFace, TimberCenterline)), \
        f"attached_timber_long_face_to_measure_to_for_length_position must be TimberLongFace or TimberCenterline, got {type(attached_timber_long_face_to_measure_to_for_length_position).__name__}"
    assert isinstance(original_timber_face_to_measure_from_for_lateral_position, (TimberFace, TimberCenterline)), \
        f"original_timber_face_to_measure_from_for_lateral_position must be TimberFace or TimberCenterline, got {type(original_timber_face_to_measure_from_for_lateral_position).__name__}"
    assert isinstance(attached_timber_long_face_to_measure_to_for_lateral_position, (TimberLongFace, TimberCenterline)), \
        f"attached_timber_long_face_to_measure_to_for_lateral_position must be TimberLongFace or TimberCenterline, got {type(attached_timber_long_face_to_measure_to_for_lateral_position).__name__}"

    # ---- orthonormal basis from the original timber's perfect-timber-within ----
    # a = attach direction (out of the chosen long face), l = original length axis, t = lateral axis.
    # The attached timber lives in the a-l plane; t is the shared (plane-aligned) lateral normal.
    a = original_timber.get_face_direction_global(original_timber_long_face_that_attached_timber_points_to)
    l = original_timber.get_length_direction_global()
    t = cross_product(a, l)

    # ---- attached timber length axis (tilted within the a-l plane) ----
    # point_dir points out of the chosen face at attached_timber_angle from the original length; it
    # is the direction the attached timber extends, independent of which end faces the original.
    point_dir = cos(attached_timber_angle) * l + sin(attached_timber_angle) * a
    if attached_timber_end_that_points_towards_original_timber == TimberEnd.BOTTOM:
        length_dir = point_dir
    else:  # the TOP end sits on the original-timber side, so +length points back toward it
        length_dir = -point_dir
    # in-plane cross-section axis: perpendicular to length_dir within the a-l plane.
    # (reduces to +l when attached_timber_angle == pi/2, matching attach_face_aligned_timber)
    p = sin(attached_timber_angle) * l - cos(attached_timber_angle) * a

    # ---- derive the cross-section orientation from the named measure-to faces ----
    # The attached timber's two cross-section axes are p (in the a-l plane) and t (lateral):
    #   - the length-position face has its normal along p (its position is read along the length l)
    #   - the lateral-position face has its normal along t (parallel to the original's lateral faces)
    # A long face on RIGHT/LEFT lies on the width (X) axis; FRONT/BACK lies on the height (Y) axis,
    # so the only decision is whether the width axis runs along p or along t.
    def _is_width_axis(face: TimberLongFace) -> bool:
        return face in (TimberLongFace.RIGHT, TimberLongFace.LEFT)

    width_axis_along_p: Optional[bool] = None
    if isinstance(attached_timber_long_face_to_measure_to_for_length_position, TimberLongFace):
        width_axis_along_p = _is_width_axis(attached_timber_long_face_to_measure_to_for_length_position)
    if isinstance(attached_timber_long_face_to_measure_to_for_lateral_position, TimberLongFace):
        lateral_wants_width_along_p = not _is_width_axis(attached_timber_long_face_to_measure_to_for_lateral_position)
        if width_axis_along_p is None:
            width_axis_along_p = lateral_wants_width_along_p
        else:
            assert width_axis_along_p == lateral_wants_width_along_p, (
                "attached_timber_long_face_to_measure_to_for_length_position and "
                "attached_timber_long_face_to_measure_to_for_lateral_position imply conflicting cross-section "
                "orientations (they must reference perpendicular faces of the attached timber)"
            )
    if width_axis_along_p is None:
        # neither face named (both CENTERLINE): default the width axis to the in-plane (p) axis
        width_axis_along_p = True

    width_dir = p if width_axis_along_p else t
    height_dir = normalize_vector(cross_product(length_dir, width_dir))

    def _attached_long_face_normal_and_half(face: TimberLongFace) -> Tuple[Direction3D, Numeric]:
        """Outward global normal and center-to-face half size for a long face of the attached timber."""
        if face == TimberLongFace.RIGHT:
            return width_dir, size[0] / scalar(2)
        elif face == TimberLongFace.LEFT:
            return -width_dir, size[0] / scalar(2)
        elif face == TimberLongFace.FRONT:
            return height_dir, size[1] / scalar(2)
        else:  # BACK
            return -height_dir, size[1] / scalar(2)

    O = original_timber.get_bottom_position_global()

    # ---- length-position-axis coordinate (along l) ----
    # Measure from the chosen end of the original timber, going into the timber.
    end_face = original_timber_end_to_measure_from_for_length_position
    end_l = get_center_point_on_face_global(end_face, original_timber).dot(l)
    if end_face == TimberEnd.TOP:
        target_l = end_l - length_position_measurement  # into the timber from the top is -l
    else:  # BOTTOM
        target_l = end_l + length_position_measurement  # into the timber from the bottom is +l
    if isinstance(attached_timber_long_face_to_measure_to_for_length_position, TimberLongFace):
        len_normal, len_half = _attached_long_face_normal_and_half(attached_timber_long_face_to_measure_to_for_length_position)
        center_l = target_l - len_normal.dot(l) * len_half
    else:  # CENTERLINE
        center_l = target_l

    # ---- lateral-position-axis coordinate (along t) ----
    if isinstance(original_timber_face_to_measure_from_for_lateral_position, TimberFace):
        orig_lat_normal = normalize_vector(original_timber.get_face_direction_global(original_timber_face_to_measure_from_for_lateral_position))
        assert are_vectors_parallel(orig_lat_normal, t), (
            "original_timber_face_to_measure_from_for_lateral_position must be a lateral face of the original timber "
            "(perpendicular to original_timber_long_face_that_attached_timber_points_to and to the length)"
        )
        from_t = get_center_point_on_face_global(original_timber_face_to_measure_from_for_lateral_position, original_timber).dot(t)
        into_sign_t = -orig_lat_normal.dot(t)  # positive measurement goes into the original timber
    else:  # CENTERLINE
        from_t = O.dot(t)
        into_sign_t = scalar(1)
    target_t = from_t + lateral_position_measurement * into_sign_t
    if isinstance(attached_timber_long_face_to_measure_to_for_lateral_position, TimberLongFace):
        lat_normal, lat_half = _attached_long_face_normal_and_half(attached_timber_long_face_to_measure_to_for_lateral_position)
        assert are_vectors_parallel(lat_normal, t), (
            "attached_timber_long_face_to_measure_to_for_lateral_position must be a lateral face (perpendicular to "
            "original_timber_long_face_that_attached_timber_points_to)"
        )
        center_t = target_t - lat_normal.dot(t) * lat_half
    else:  # CENTERLINE
        center_t = target_t

    # ---- resolve the timber's extent along its centerline ----
    # Parametrize the attached centerline by s (in units of point_dir), with s = 0 where it
    # crosses the plane through the original timber's centerline with normal a. The start end
    # (the end that attaches to the original timber) sits at s = -opposite_length and the target
    # end at s = attached_timber_length.

    # start end: where the centerline touches the stickoutReference1 feature of the original
    # timber, extended by stickout1 beyond it (in -point_dir).
    if attached_timber_stickout.stickoutReference1 == StickoutReference.CENTER_LINE:
        start_reference_s = scalar(0)
    else:
        sin_attach = point_dir.dot(a)  # sin(attached_timber_angle)
        assert safe_compare(sin_attach, scalar(0), Comparison.GT), \
            "INSIDE/OUTSIDE stickoutReference1 requires attached_timber_angle strictly between 0 and pi (the attached timber must point out of the original timber's face)"
        # center-to-face depth of the original timber along the attach direction
        half_depth_along_a = get_center_point_on_face_global(
            original_timber_long_face_that_attached_timber_points_to, original_timber).dot(a) - O.dot(a)
        if attached_timber_stickout.stickoutReference1 == StickoutReference.INSIDE:
            start_reference_s = half_depth_along_a / sin_attach
        else:  # OUTSIDE: the face opposite the one the attached timber points out of
            start_reference_s = -half_depth_along_a / sin_attach
    opposite_length = attached_timber_stickout.stickout1 - start_reference_s


    if isinstance(attached_timber_length_or_target, PerfectTimberWithin):
        # target end: where the centerline touches the stickoutReference2 feature of the target
        # timber, extended by stickout2 beyond it (in +point_dir). The feature is the target's
        # centerline -- or the near (INSIDE) / far (OUTSIDE) boundary of its silhouette --
        # projected onto the a-l plane. Projected along t, each feature is a plane {x . m = d}
        # with m . t == 0, so intersecting the attached centerline with the plane equals
        # intersecting it with the projected feature.
        target_timber = attached_timber_length_or_target
        target_length_dir = target_timber.get_length_direction_global()
        if are_vectors_parallel(target_length_dir, t):
            # the target's centerline is parallel to the lateral axis, so it projects to a single
            # *point* on the a-l plane: drop that point perpendicularly onto the attached timber's
            # length axis, i.e. touch the plane through the target's centerline with normal
            # point_dir (the perpendicular foot is where the centerline crosses that plane)
            m = point_dir
        else:
            m = normalize_vector(cross_product(target_length_dir, t))
        crossing_rate = point_dir.dot(m)
        d = target_timber.get_bottom_position_global().dot(m)
        if attached_timber_stickout.stickoutReference2 != StickoutReference.CENTER_LINE:
            assert safe_compare(crossing_rate, scalar(0), Comparison.NE), \
                "attached timber runs parallel to the target timber's projection, so INSIDE/OUTSIDE stickoutReference2 cannot be resolved"
            # near/far silhouette boundary: the projected centerline offset by the largest
            # cross-section corner offset along m. For a target plane-aligned with the a-l plane
            # this reduces to its long face planes; for a rotated target it is the projected
            # corner-edge boundary.
            silhouette_half_extent = (
                target_timber.size[0] / scalar(2) * Abs(target_timber.get_width_direction_global().dot(m))
                + target_timber.size[1] / scalar(2) * Abs(target_timber.get_height_direction_global().dot(m))
            )
            # INSIDE is the boundary the attached timber reaches first travelling along +point_dir
            approaching_along_m = safe_compare(crossing_rate, scalar(0), Comparison.GT)
            if (attached_timber_stickout.stickoutReference2 == StickoutReference.INSIDE) == approaching_along_m:
                d = d - silhouette_half_extent
            else:
                d = d + silhouette_half_extent

        # The length-position measurement pins the attached timber's *center* at (center_l,
        # center_t), and the center sits at s = (length - opposite_length)/2, so for non-
        # perpendicular angles the centerline's position itself depends on the length being
        # solved for. Substituting the s = 0 point
        #   P0 = (O.a, center_l - (length - opposite_length)/2 * cos_attach, center_t)
        # into the touch condition (d - P0.m) / (point_dir.m) + stickout2 = length and solving
        # the (linear) equation for length gives the closed form below.
        cos_attach = point_dir.dot(l)
        m_l = m.dot(l)
        # P0.m evaluated as if length == opposite_length; the length dependence is folded into
        # the denominator.
        centerline_anchor_dot_m = O.dot(a) * m.dot(a) + center_l * m_l + center_t * m.dot(t)
        denominator = crossing_rate - cos_attach * m_l / scalar(2)
        assert safe_compare(denominator, scalar(0), Comparison.NE), \
            "attached timber's centerline (as positioned by the length-position measurement) never crosses the target feature"
        attached_timber_length = (
            attached_timber_stickout.stickout2 * crossing_rate
            + (d - centerline_anchor_dot_m)
            - opposite_length / scalar(2) * cos_attach * m_l
        ) / denominator
    else:
        attached_timber_length = attached_timber_length_or_target
        if attached_timber_stickout.stickout2 != scalar(0) or attached_timber_stickout.stickoutReference2 != StickoutReference.CENTER_LINE:
            warnings.warn("attached_timber_stickout.stickout2 is ignored when attached_timber_length_or_target is a numeric length; pass a target timber to use it")

    attached_total_length = attached_timber_length + opposite_length
    assert safe_compare(attached_total_length, scalar(0), Comparison.GT), \
        "attached timber total length (attached_timber_length + opposite length from stickout1) must be positive"

    # ---- attach-axis coordinate of the attached timber's center ----
    # The timber extends from s = -opposite_length to s = attached_timber_length along point_dir,
    # so the center's a-coordinate shifts by (length - opposite)/2 times the a-component of point_dir.
    center_a = O.dot(a) + (attached_timber_length - opposite_length) / scalar(2) * point_dir.dot(a)

    # ---- reconstruct the center in global coordinates and build the timber ----
    # (a, l, t) is an orthonormal basis, so a global point equals the sum of its coords times the axes.
    center = center_a * a + center_l * l + center_t * t
    bottom_position = center - length_dir * (attached_total_length / scalar(2))

    return create_timber(
        bottom_position=bottom_position,
        length=attached_total_length,
        size=size,
        length_direction=length_dir,
        width_direction=width_dir,
        ticket=ticket,
    )

def attach_face_aligned_timber(
    original_timber: TimberLike,
    size: V2, # always width, height in the local coordinates of the created attached timber
    original_timber_long_face_that_attached_timber_points_to: TimberLongFace,
    attached_timber_length_or_target: Union[Numeric, TimberLike],
    attached_timber_stickout: Stickout = Stickout.nostickout(),
    attached_timber_end_that_points_towards_original_timber: TimberEnd = TimberEnd.BOTTOM,
    original_timber_end_to_measure_from_for_length_position: TimberEnd = TimberEnd.BOTTOM,
    attached_timber_long_face_to_measure_to_for_length_position: Union[TimberLongFace, TimberCenterline] = TimberCenterline.CENTERLINE,
    length_position_measurement: Numeric = scalar(0),
    original_timber_face_to_measure_from_for_lateral_position: Union[TimberFace, TimberCenterline] = TimberCenterline.CENTERLINE,
    attached_timber_long_face_to_measure_to_for_lateral_position: Union[TimberLongFace, TimberCenterline] = TimberCenterline.CENTERLINE,
    lateral_position_measurement: Numeric = scalar(0),
    ticket: Optional[Union[TimberTicket, str]] = None,
) -> Timber:
    """
    Creates a timber that is face-aligned with and attached to ``original_timber``.

    The original timber is referred to as "original_timber" and the new timber as
    "attached_timber". The attached timber runs perpendicular to the chosen long face of the
    original timber and is fully face-aligned with it.

    All measurements are taken from the perfect timber within of the original and attached timber

    ## Orientation

    The attached timber's length axis runs along the normal of
    ``original_timber_long_face_that_attached_timber_points_to`` (the face it "points to" / sticks
    out of). ``attached_timber_end_that_points_towards_original_timber`` chooses which end
    (TOP/BOTTOM) of the attached timber sits on the original-timber side;

    The attached timber's height and width axis orientation are determined by:
    - attached_timber_long_face_to_measure_to_for_lateral_position
    - attached_timber_long_face_to_measure_to_for_length_position
    so that these faces are parallel to the features on original_timber that they are measured from.

    ## Extents

    ``attached_timber_length_or_target`` places the far end of the attached timber: either a
    numeric length measured from the original timber's centerline, or a timber to extend to (up
    to the feature selected by ``attached_timber_stickout.stickoutReference2``, plus
    ``stickout2`` beyond it). ``attached_timber_stickout`` places the near end relative to the
    original timber's feature selected by ``stickoutReference1`` (CENTER_LINE by default),
    extended by ``stickout1`` beyond it. See :func:`attach_plane_aligned_timber` for details.

    ## Positioning

    The attached timber's position is such that the distance between 
    ``original_timber_end_to_measure_from_for_length_position`` and ``attached_timber_long_face_to_measure_to_for_length_position`` 
    is ``length_position_measurement``, 
    
    and the distance between 
    ``original_timber_face_to_measure_from_for_lateral_position`` and ``attached_timber_long_face_to_measure_to_for_lateral_position`` 
    is ``lateral_position_measurement``.


    Returns:
        The new attached timber, face-aligned with and positioned relative to the original timber.
    """
    # Face-aligned is the perpendicular (pi/2) special case of attach_plane_aligned_timber.
    return attach_plane_aligned_timber(
        original_timber=original_timber,
        size=size,
        original_timber_long_face_that_attached_timber_points_to=original_timber_long_face_that_attached_timber_points_to,
        attached_timber_angle= radians(pi / 2),
        attached_timber_length_or_target=attached_timber_length_or_target,
        attached_timber_stickout=attached_timber_stickout,
        attached_timber_end_that_points_towards_original_timber=attached_timber_end_that_points_towards_original_timber,
        original_timber_end_to_measure_from_for_length_position=original_timber_end_to_measure_from_for_length_position,
        attached_timber_long_face_to_measure_to_for_length_position=attached_timber_long_face_to_measure_to_for_length_position,
        length_position_measurement=length_position_measurement,
        original_timber_face_to_measure_from_for_lateral_position=original_timber_face_to_measure_from_for_lateral_position,
        attached_timber_long_face_to_measure_to_for_lateral_position=attached_timber_long_face_to_measure_to_for_lateral_position,
        lateral_position_measurement=lateral_position_measurement,
        ticket=ticket,
    )
    

def join_timbers(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin, 
                location_on_timber1: Numeric,
                location_on_timber2: Optional[Numeric] = None,
                lateral_offset: Numeric = scalar(0),
                stickout: Stickout = Stickout.nostickout(),
                size: Optional[V2] = None,
                orientation_width_vector: Optional[Direction3D] = None, 
                ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    """
    Joins two timbers by creating a connecting timber from centerline to centerline.
    
    This function creates a timber that connects the centerline of timber1 to the centerline
    of timber2. The joining timber's length direction goes from timber1 to timber2, and its
    position can be laterally offset from this centerline-to-centerline path.
    
    Args:
        timber1: First timber to join (start point)
        timber2: Second timber to join (end point)
        location_on_timber1: Position along timber1's length where the joining timber starts
        location_on_timber2: Optional position along timber2's length where the joining timber ends.
                            If not provided, uses the same Z-height as location_on_timber1.
        lateral_offset: Lateral offset of the joining timber perpendicular to the direct 
                       centerline-to-centerline path. The offset direction is determined by the
                       cross product of timber1's length direction and the joining direction.
                       Defaults to scalar(0) (no offset).
        stickout: How much the joining timber extends beyond each connection point (both sides).
                  Always measured from centerlines in this function.
                  Defaults to Stickout.nostickout() if not provided.
        size: Optional size (width, height) of the joining timber. If not provided,
              determined from timber1's size based on orientation.
        orientation_width_vector: Optional width direction hint for the created timber in global space.
                                 Will be automatically projected onto the normal plane of the length axis of the created timber.
                                This is useful for 
                                 specifying orientation like "face up" for rafters.
                                 If not provided, uses timber1's length direction projected onto
                                 the perpendicular plane.
                                 If the provided vector is parallel to the joining direction, falls back
                                 to timber1's width direction.
        ticket: Optional ticket for this timber (can be Ticket object or string name, used for rendering/debugging)
        
    Returns:
        New timber connecting timber1 and timber2 along their centerlines
    """
    # Calculate position on timber1
    pos1 = locate_position_on_centerline_from_bottom(timber1, location_on_timber1).position
    
    # Calculate position on timber2
    if location_on_timber2 is not None:
        pos2 = locate_position_on_centerline_from_bottom(timber2, location_on_timber2).position
    else:
        # Find the point on timber2's centerline at the same z-height as pos1
        timber2_bottom = timber2.get_bottom_position_global()
        pos2 = Matrix([timber2_bottom[0], timber2_bottom[1], timber2_bottom[2] + location_on_timber1])
    
    # Calculate length direction (from timber1 to timber2)
    length_direction = pos2 - pos1
    length_direction = normalize_vector(length_direction)
    
    # Calculate face direction (width direction for the created timber)
    if orientation_width_vector is not None:
        reference_direction = orientation_width_vector
    else:
        # Default: use timber1's length direction
        reference_direction = timber1.get_length_direction_global()
    
    # Check if reference direction is parallel to the joining direction
    if _are_directions_parallel(reference_direction, length_direction):
        # If parallel, cannot project - use a perpendicular fallback
        if orientation_width_vector is not None:
            warnings.warn(f"orientation_width_vector {orientation_width_vector} is parallel to the joining direction {length_direction}. Using timber1's width direction instead.")
            reference_direction = timber1.get_width_direction_global()
        else:
            warnings.warn("timber1's length direction is parallel to the joining direction. Using timber1's width direction instead.")
            reference_direction = timber1.get_width_direction_global()
    
    # Project reference direction onto the plane perpendicular to the joining direction
    # Formula: v_perp = v - (v·n)n
    dot_product = reference_direction.dot(length_direction)
    width_direction = reference_direction - dot_product * length_direction
    width_direction = normalize_vector(width_direction)
    
    # TODO TEST THIS IT'S PROBABLY WRONG
    # Determine size if not provided
    if size is None:
        # Check the orientation of the created timber relative to timber1
        # Dot product of the created timber's face direction with timber1's length direction
        dot_product = Abs(width_direction.dot(timber1.get_length_direction_global()))
        
        if dot_product < scalar(1, 2):  # < 0.5, meaning more perpendicular than parallel
            # The created timber is joining perpendicular to timber1
            # Its X dimension (width, along width_direction) should match the dimension 
            # of the face it's joining to on timber1, which is timber1's width (size[0])
            size = create_v2(timber1.size[0], timber1.size[1])
        else:
            # For other orientations, use timber1's size as-is
            size = create_v2(timber1.size[0], timber1.size[1])
    
    # Assert that join_timbers only uses CENTER_LINE stickout reference
    assert stickout.stickoutReference1 == StickoutReference.CENTER_LINE, \
        "join_timbers only supports CENTER_LINE stickout reference. Use join_face_aligned_on_face_aligned_timbers for INSIDE/OUTSIDE references."
    assert stickout.stickoutReference2 == StickoutReference.CENTER_LINE, \
        "join_timbers only supports CENTER_LINE stickout reference. Use join_face_aligned_on_face_aligned_timbers for INSIDE/OUTSIDE references."
    
    # Calculate timber length with stickout (always from centerline in join_timbers)
    centerline_distance = vector_magnitude(pos2 - pos1)
    timber_length = centerline_distance + stickout.stickout1 + stickout.stickout2
    
    # Apply lateral offset
    if lateral_offset != scalar(0):
        # Calculate offset direction (cross product of length vectors)
        offset_dir = normalize_vector(cross_product(timber1.get_length_direction_global(), length_direction))
    
    # Calculate the bottom position (start of timber)
    # Start from pos1 and move backward by stickout1 (always centerline)
    bottom_pos = pos1 - length_direction * stickout.stickout1
    
    # Apply offset to bottom position as well (if any offset was applied to center)
    if lateral_offset != scalar(0):
        bottom_pos += offset_dir * lateral_offset
    
    return create_timber(bottom_pos, timber_length, size, length_direction, width_direction, ticket=ticket)


def join_plane_aligned_on_place_aligned_timbers(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin,
                                                location_on_timber1: Numeric, location_on_timber2: Numeric,
                                                stickout: Stickout,
                                                size: V2,
                                                # lateral offset (in the axis perpendicular to the face parallel plane) from feature_to_mark_on_joining_timber
                                                lateral_offset_from_timber1: Numeric = scalar(0),
                                                feature_to_mark_on_joining_timber: Optional[TimberFeature] = None,
                                                # if None, set to some arbitrary face of timber1 on the parallel face plane
                                                orientation_long_face_on_timber1: Optional[TimberLongFace] = None, 
                                                # this face on the created timber will align with orientation_long_face_on_timber1
                                                orientation_long_face_on_timber2: Optional[TimberLongFace] = TimberLongFace.RIGHT,
                                                ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    require_check(None if are_timbers_plane_aligned(timber1, timber2) else "Timbers must be plane-aligned")
    plane_normal = normalize_vector(cross_product(timber1.get_length_direction_global(), timber2.get_length_direction_global()))

    if orientation_long_face_on_timber1 is None:
        orientation_long_face_on_timber1 = timber1.get_closest_oriented_long_face_from_global_direction(plane_normal)
    else:
        require_check(
            None
            if are_vectors_parallel(timber1.get_face_direction_global(orientation_long_face_on_timber1), plane_normal)
            else "orientation_long_face_on_timber1 must point in the aligned plane normal"
        )

    if orientation_long_face_on_timber2 is None:
        orientation_long_face_on_timber2 = TimberLongFace.RIGHT

    aligned_face_direction = timber1.get_face_direction_global(orientation_long_face_on_timber1)

    point1 = locate_position_on_centerline_from_bottom(timber1, location_on_timber1).position
    point2 = locate_position_on_centerline_from_bottom(timber2, location_on_timber2).position
    joining_direction = normalize_vector(point2 - point1)
    lateral_offset_direction = normalize_vector(cross_product(timber1.get_length_direction_global(), joining_direction))
    lateral_offset = lateral_offset_from_timber1
    if safe_compare(lateral_offset_direction.dot(plane_normal), 0, Comparison.LT):
        lateral_offset = -lateral_offset

    if orientation_long_face_on_timber2 == TimberLongFace.RIGHT:
        orientation_width_vector = aligned_face_direction
    elif orientation_long_face_on_timber2 == TimberLongFace.LEFT:
        orientation_width_vector = -aligned_face_direction
    elif orientation_long_face_on_timber2 == TimberLongFace.FRONT:
        orientation_width_vector = cross_product(aligned_face_direction, joining_direction)
    else:
        orientation_width_vector = -cross_product(aligned_face_direction, joining_direction)

    return join_timbers(
        timber1=timber1,
        timber2=timber2,
        location_on_timber1=location_on_timber1,
        location_on_timber2=location_on_timber2,
        lateral_offset=lateral_offset,
        stickout=stickout,
        size=size,
        orientation_width_vector=normalize_vector(orientation_width_vector),
        ticket=ticket,
    )


# TODO this function kinda sucks... awkward to measure to use, yo uneed to locate_face(timber1).mark_distance_from_end_along_centerline().distance or osmething crap like that to set lateral_offset_from_timber1 :(
@deprecated("attach_face_aligned_timber is easier to understand")
def join_face_aligned_on_face_aligned_timbers(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin,
                                                location_on_timber1: Numeric,
                                                stickout: Stickout,
                                                size: V2,
                                                lateral_offset_from_timber1: Numeric = scalar(0),
                                                feature_to_mark_on_joining_timber: Optional[TimberFeature] = None,
                                                orientation_face_on_timber1: Optional[TimberFace] = None, 
                                                ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    """
    Joins two face-aligned timbers with a perpendicular timber.
    
    Args:
        timber1: First timber to join
        timber2: Second timber to join (face-aligned with timber1)
        location_on_timber1: Position along timber1's length where the joining timber attaches
        stickout: How much the joining timber extends beyond each connection point
        size: Cross-sectional size (width, height) of the joining timber
        lateral_offset_from_timber1: Lateral offset from timber1's centerline reference.
                        Defaults to scalar(0).
        feature_to_mark_on_joining_timber: Optional feature on the create timber to use as the reference for the lateral offset.
                                           It is intended for you to use the locate_face or locate_long_edge functions to create a plane or line on a timber.
                                           If not provided, uses the centerline. If a plane is provided, the "origin" of the plane is used for longitudinal positioning (i.e. location_on_timber1). In the case of locate_face, the origin aligns with the center of the created timber.
        orientation_face_on_timber1: Optional face of timber1 to orient against. If provided,
                                     the width direction of the created timber will align with this face on timber1.
                                     If not provided, uses timber1's length direction projected onto
                                     the perpendicular plane.
        ticket: Optional ticket for this timber (can be Ticket object or string name, used for rendering/debugging)
        
    Returns:
        New timber that joins timber1 and timber2
    """
    # Verify that the two timbers are face-aligned
    assert are_timbers_face_aligned(timber1, timber2), \
        "timber1 and timber2 must be face-aligned (share at least one parallel direction)"
    
    # Auto-determine size if not provided
    if size is None:
        # Use timber1's size as the default
        size = timber1.size
    
    # Calculate position on timber1
    pos1 = locate_position_on_centerline_from_bottom(timber1, location_on_timber1).position
    
    # Project pos1 onto timber2's centerline to find location_on_timber2
    # Vector from timber2's bottom to pos1
    to_pos1 = pos1 - timber2.get_bottom_position_global()
    
    # Project this onto timber2's length direction to find the parameter t
    location_on_timber2 = to_pos1.dot(timber2.get_length_direction_global()) / timber2.get_length_direction_global().dot(timber2.get_length_direction_global())
    
    # Intentionally do not clamp the projected location. Callers may rely on
    # measurements beyond timber2's nominal extents.
    #location_on_timber2 = max(scalar(0), min(timber2.length, location_on_timber2))
    
    # Calculate position on timber2 to determine joining direction
    pos2 = locate_position_on_centerline_from_bottom(timber2, location_on_timber2).position
    joining_direction = normalize_vector(pos2 - pos1)
    
    # Convert TimberFace to a direction vector for orientation (if provided)
    orientation_width_vector = orientation_face_on_timber1.get_direction() if orientation_face_on_timber1 is not None else None
    
    # Calculate the width_direction for the joining timber (needed for feature offset calculation)
    if orientation_width_vector is not None:
        reference_direction = orientation_width_vector
    else:
        # Default: use timber1's length direction
        reference_direction = timber1.get_length_direction_global()
    
    # Check if reference direction is parallel to the joining direction
    if _are_directions_parallel(reference_direction, joining_direction):
        # If parallel, use a perpendicular fallback
        reference_direction = timber1.get_width_direction_global()
    
    # Project reference direction onto the plane perpendicular to the joining direction
    dot_product = reference_direction.dot(joining_direction)
    width_direction = reference_direction - dot_product * joining_direction
    width_direction = normalize_vector(width_direction)
    
    # Calculate height direction (perpendicular to both length and width)
    height_direction = normalize_vector(cross_product(joining_direction, width_direction))
    
    # Now convert feature-relative measurements to centerline-relative measurements
    longitudinal_offset = scalar(0)
    lateral_offset_adjustment = scalar(0)
    
    # Convert TimberFeature enum to geometric object if provided
    feature_geometry = None
    if feature_to_mark_on_joining_timber is not None:
        # Create a temporary timber to measure the feature on
        # This timber has the same cross-section and orientation as the final joining timber
        temp_timber_center = pos1  # Arbitrary position for temp timber
        temp_timber = create_timber(
            bottom_position=temp_timber_center,
            length=scalar(1),  # Arbitrary length
            size=size,
            length_direction=joining_direction,
            width_direction=width_direction
        )
        
        # Convert TimberFeature enum to the corresponding geometric object
        if feature_to_mark_on_joining_timber == TimberFeature.CENTERLINE:
            # No offset needed for centerline
            feature_geometry = None
        elif feature_to_mark_on_joining_timber == TimberFeature.TOP_FACE:
            feature_geometry = locate_face(temp_timber, TimberFace.TOP)
        elif feature_to_mark_on_joining_timber == TimberFeature.BOTTOM_FACE:
            feature_geometry = locate_face(temp_timber, TimberFace.BOTTOM)
        elif feature_to_mark_on_joining_timber == TimberFeature.RIGHT_FACE:
            feature_geometry = locate_face(temp_timber, TimberFace.RIGHT)
        elif feature_to_mark_on_joining_timber == TimberFeature.LEFT_FACE:
            feature_geometry = locate_face(temp_timber, TimberFace.LEFT)
        elif feature_to_mark_on_joining_timber == TimberFeature.FRONT_FACE:
            feature_geometry = locate_face(temp_timber, TimberFace.FRONT)
        elif feature_to_mark_on_joining_timber == TimberFeature.BACK_FACE:
            feature_geometry = locate_face(temp_timber, TimberFace.BACK)
        elif feature_to_mark_on_joining_timber == TimberFeature.RIGHT_FRONT_EDGE:
            feature_geometry = locate_long_edge(temp_timber, TimberLongEdge.RIGHT_FRONT)
        elif feature_to_mark_on_joining_timber == TimberFeature.FRONT_LEFT_EDGE:
            feature_geometry = locate_long_edge(temp_timber, TimberLongEdge.FRONT_LEFT)
        elif feature_to_mark_on_joining_timber == TimberFeature.LEFT_BACK_EDGE:
            feature_geometry = locate_long_edge(temp_timber, TimberLongEdge.LEFT_BACK)
        elif feature_to_mark_on_joining_timber == TimberFeature.BACK_RIGHT_EDGE:
            feature_geometry = locate_long_edge(temp_timber, TimberLongEdge.BACK_RIGHT)
        else:
            raise ValueError(f"Unsupported TimberFeature: {feature_to_mark_on_joining_timber}")
    
    if isinstance(feature_geometry, Plane):
        # Feature is a face plane - need to calculate both longitudinal and lateral offsets
        # Determine which face this plane represents by comparing normals using dot product
        
        # Normalize the plane normal for comparison
        plane_normal = normalize_vector(feature_geometry.normal)
        
        # Check dot products to determine which direction the normal points
        # dot product ≈ +1 means same direction, ≈ -1 means opposite direction
        width_dot = safe_dot_product(plane_normal, width_direction)
        height_dot = safe_dot_product(plane_normal, height_direction)
        
        # Determine which axis has the strongest alignment (should be close to ±1)
        if Abs(width_dot) > Abs(height_dot):
            # Normal is aligned with width_direction (RIGHT/LEFT faces)
            if safe_compare(width_dot, 0, Comparison.GT):
                # RIGHT face (normal = +width_direction)
                longitudinal_offset = size[0] / 2
                lateral_offset_adjustment = scalar(0)
            else:
                # LEFT face (normal = -width_direction)
                longitudinal_offset = -size[0] / 2
                lateral_offset_adjustment = scalar(0)
        else:
            # Normal is aligned with height_direction (FRONT/BACK faces)
            if safe_compare(height_dot, 0, Comparison.GT):
                # FRONT face (normal = +height_direction)
                longitudinal_offset = scalar(0)
                lateral_offset_adjustment = size[1] / 2
            else:
                # BACK face (normal = -height_direction)
                longitudinal_offset = scalar(0)
                lateral_offset_adjustment = -size[1] / 2
    
    elif isinstance(feature_geometry, Line):
        # Feature is an edge line - need to calculate lateral offset only
        # The edge position is determined by offsets in both width and height directions
        
        # Create an imaginary centerline at pos1 for comparison
        centerline_point = pos1
        
        # Calculate the offset of the line's point from the centerline
        offset_vector = feature_geometry.point - centerline_point
        
        # Project onto width and height directions to get the edge position
        width_offset = offset_vector.dot(width_direction)
        height_offset = offset_vector.dot(height_direction)
        
        # The lateral offset is the distance in the lateral direction (perpendicular to joining direction)
        # For a joining timber, the lateral direction is typically the cross product of
        # timber1's length direction and the joining direction
        lateral_direction = normalize_vector(cross_product(timber1.get_length_direction_global(), joining_direction))
        
        # Calculate total lateral offset from the edge position
        # The edge has offsets in both width and height directions
        lateral_offset_adjustment = width_offset * width_direction.dot(lateral_direction) + \
                                   height_offset * height_direction.dot(lateral_direction)
        
        # No longitudinal offset for edge lines (they run along the length)
        longitudinal_offset = scalar(0)
    
    # Adjust location_on_timber1 for longitudinal offset (along joining_direction)
    # The longitudinal offset affects where along timber1's length we measure from
    adjusted_location_on_timber1 = location_on_timber1 + longitudinal_offset
    
    # Adjust lateral offset
    adjusted_lateral_offset = lateral_offset_from_timber1 + lateral_offset_adjustment
    
    # Recalculate pos1 with the adjusted location
    pos1 = locate_position_on_centerline_from_bottom(timber1, adjusted_location_on_timber1).position
    
    # Recalculate location_on_timber2 and pos2 based on adjusted pos1
    to_pos1 = pos1 - timber2.get_bottom_position_global()
    location_on_timber2 = to_pos1.dot(timber2.get_length_direction_global()) / timber2.get_length_direction_global().dot(timber2.get_length_direction_global())
    # Intentionally do not clamp the projected location. Keep this consistent
    # with the initial projection above.
    pos2 = locate_position_on_centerline_from_bottom(timber2, location_on_timber2).position
    joining_direction = normalize_vector(pos2 - pos1)
    
    # Determine which dimension of the created timber is perpendicular to the joining direction
    # The created timber will have:
    # - length_direction = joining_direction
    # - width_direction = orientation_width_vector
    # - height_direction = cross(length_direction, width_direction)
    
    # To determine which dimension (width=size[0] or height=size[1]) affects the stickout,
    # we need to see which one is aligned with the joining direction's perpendicular plane
    # For simplicity, we'll use the dot product to determine which axis is more aligned
    
    # Determine perpendicular size for stickout conversion
    # Only needed if stickout references are not CENTER_LINE
    if stickout.stickoutReference1 != StickoutReference.CENTER_LINE or stickout.stickoutReference2 != StickoutReference.CENTER_LINE:
        # Need to determine which dimension is perpendicular
        if orientation_width_vector is not None:
            # The width (size[0]) is along the width_direction
            # The height (size[1]) is along the height_direction (perpendicular to both)
            height_direction = normalize_vector(cross_product(joining_direction, orientation_width_vector))
            
            # Check which dimension is more perpendicular to timber1's length direction
            # This determines which face is "inside" (facing timber1)
            face_dot = Abs(orientation_width_vector.dot(timber1.get_length_direction_global()))
            height_dot = Abs(height_direction.dot(timber1.get_length_direction_global()))
            
            # Use the dimension that's more perpendicular to timber1's length
            if face_dot < height_dot:
                # Face direction is more perpendicular, so width (size[0]) affects inside/outside
                perpendicular_size = size[0]
            else:
                # Height direction is more perpendicular, so height (size[1]) affects inside/outside
                perpendicular_size = size[1]
        else:
            # Without orientation specified, default to using width
            perpendicular_size = size[0]
    else:
        # Not needed for CENTER_LINE stickout
        perpendicular_size = 0
    
    # Convert stickout references to centerline offsets
    centerline_stickout1 = stickout.stickout1
    centerline_stickout2 = stickout.stickout2
    
    if stickout.stickoutReference1 == StickoutReference.INSIDE:
        # INSIDE: Extends from the face closest to timber2
        # Add half the perpendicular size
        centerline_stickout1 = stickout.stickout1 + perpendicular_size / scalar(2)
    elif stickout.stickoutReference1 == StickoutReference.OUTSIDE:
        # OUTSIDE: Extends from the face away from timber2
        # Subtract half the perpendicular size
        centerline_stickout1 = stickout.stickout1 - perpendicular_size / scalar(2)
    
    if stickout.stickoutReference2 == StickoutReference.INSIDE:
        # INSIDE: Extends from the face closest to timber1
        centerline_stickout2 = stickout.stickout2 + perpendicular_size / scalar(2)
    elif stickout.stickoutReference2 == StickoutReference.OUTSIDE:
        # OUTSIDE: Extends from the face away from timber1
        centerline_stickout2 = stickout.stickout2 - perpendicular_size / scalar(2)
    
    # Create a new Stickout with CENTER_LINE reference
    centerline_stickout = Stickout(
        centerline_stickout1,
        centerline_stickout2,
        StickoutReference.CENTER_LINE,
        StickoutReference.CENTER_LINE
    )
    
    # Call join_timbers to do the actual work with adjusted centerline-based parameters
    return join_timbers(
        timber1=timber1,
        timber2=timber2,
        location_on_timber1=adjusted_location_on_timber1,
        stickout=centerline_stickout,
        location_on_timber2=location_on_timber2,
        lateral_offset=adjusted_lateral_offset,
        orientation_width_vector=orientation_width_vector,
        size=size,
        ticket=ticket
    )




# ============================================================================
# Joint Arrangement Data Structures
# ============================================================================



# this class names each of the timbers 
class ArrangementNames(Enum):
    '''
    identifies each of the timbers in the various arrangements, we just use one enum for convenience but we really only want to refer to timbers specific to a certain arrangement when using this class
    '''
    timber1 = "timber1",
    timber2 = "timber2",
    receiving_timber = "receiving_timber",
    butt_timber = "butt_timber",
    butt_timber_1 = "butt_timber_1",
    butt_timber_2 = "butt_timber_2",
    main_butt_timber_1 = "main_butt_timber_1",
    main_butt_timber_2 = "main_butt_timber_2",
    awk_timber = "awk_timber",
    awk_1 = "awk_1",
    awk_2 = "awk_2",
    post_timber = "post_timber",
    cross_timber_1 = "cross_timber_1",
    cross_timber_2 = "cross_timber_2",
    brace_timber = "brace_timber",

@dataclass(frozen=True)
class ButtJointTimberArrangement:
    butt_timber: TimberLike
    receiving_timber: TimberLike
    butt_timber_end: TimberEnd
    front_face_on_butt_timber: Optional[TimberLongFace] = None

    # this is totally silly. please delete me. We're not doing any hard computations in here...
    # I'm leavin git here as an example of a potential optimization we could do.
    _memo: Dict[str, Any] = field(default_factory=dict, repr=False)

    def compute_normalized_timber_cross_product(self) -> Direction3D:
        """Compute the normalized cross product of the butt timber and receiving timber length directions."""
        key = "normalized_timber_cross_product"
        if self._memo.get(key) is not None:
            return self._memo[key]
        result = normalize_vector(cross_product(self.butt_timber.get_length_direction_global(), self.receiving_timber.get_length_direction_global()))
        self._memo[key] = result
        return result

    def check_plane_aligned(self) -> Optional[str]:
        """Return None if timbers are plane-aligned and front face is in plane, else an error message."""
        if not are_timbers_plane_aligned(self.butt_timber, self.receiving_timber):
            return "Timbers must be plane-aligned"
        if self.front_face_on_butt_timber is not None and not are_vectors_parallel(
            self.butt_timber.get_face_direction_global(self.front_face_on_butt_timber),
            self.compute_normalized_timber_cross_product(),
        ):
            return "front_face_on_butt_timber must point in the aligned plane normal"
        return None

    def check_face_aligned_and_orthogonal(self) -> Optional[str]:
        """Return None if timbers are face-aligned and orthogonal, else an error message."""
        if not are_timbers_face_aligned(self.butt_timber, self.receiving_timber):
            return "Timbers must be face-aligned"
        if not are_timbers_orthogonal(self.butt_timber, self.receiving_timber):
            return "Timbers must be orthogonal"
        return None
    
    def check_perfection(self) -> Optional[str]:
        """Return None if both timbers are perfect, else an error message."""
        if not self.butt_timber.is_perfect_timber():
            return "butt_timber must be perfect"
        if not self.receiving_timber.is_perfect_timber():
            return "receiving_timber must be perfect"
        return None


@dataclass(frozen=True)
class DoubleButtJointTimberArrangement:
    """Two butt timbers meeting a single receiving timber.

    Arrangements:
    - Opposing: butt_timber_1 and butt_timber_2 point in opposite cardinal directions
      (antiparallel, like spokes from either side of the receiving timber).
    - Orthogonal: butt_timber_1 and butt_timber_2 point in perpendicular cardinal directions
      (90° apart, like an L at the receiving timber).
    """
    butt_timber_1: TimberLike
    butt_timber_2: TimberLike
    receiving_timber: TimberLike
    butt_timber_1_end: TimberEnd
    butt_timber_2_end: TimberEnd
    front_face_on_butt_timber_1: Optional[TimberLongFace] = None

    def check_face_aligned(self) -> Optional[str]:
        """Return None if all timbers are face-aligned with the receiving timber, else an error message."""
        if not are_timbers_face_aligned(self.butt_timber_1, self.receiving_timber):
            return "butt_timber_1 must be face-aligned with receiving_timber"
        if not are_timbers_face_aligned(self.butt_timber_2, self.receiving_timber):
            return "butt_timber_2 must be face-aligned with receiving_timber"
        return None

    def check_face_aligned_cardinal_and_opposing_butts(self) -> Optional[str]:
        """Return None if:
        - all timbers are face-aligned,
        - each butt timber's length direction is orthogonal to the receiving timber (cardinal),
        - butt_timber_1 and butt_timber_2 are in different cardinal directions, and
        - the pair approaches from opposite directions (antiparallel), accounting for which end of each timber is used.
        """
        err = self.check_face_aligned()
        if err is not None:
            return err
        recv_len = self.receiving_timber.get_length_direction_global()
        dir1 = self.butt_timber_1.get_length_direction_global()
        dir2 = self.butt_timber_2.get_length_direction_global()
        if not _are_directions_perpendicular(dir1, recv_len):
            return "butt_timber_1 length direction must be orthogonal to receiving_timber length direction"
        if not _are_directions_perpendicular(dir2, recv_len):
            return "butt_timber_2 length direction must be orthogonal to receiving_timber length direction"

        if self.front_face_on_butt_timber_1 is not None:
            joint_plane_normal = normalize_vector(cross_product(dir1, recv_len))
            butt_1_face_normal = self.butt_timber_1.get_face_direction_global(
                self.front_face_on_butt_timber_1
            )
            if not are_vectors_parallel(butt_1_face_normal, joint_plane_normal):
                return (
                    "front_face_on_butt_timber_1 must be parallel to the joint plane "
                    "(its normal must be parallel to the joint-plane normal)"
                )
        
        
        # Calculate effective approach directions based on which end of each timber is used
        # If end == TOP, the timber approaches from the -direction
        # If end == BOTTOM, the timber approaches from the +direction
        approach_dir1 = -dir1 if self.butt_timber_1_end == TimberEnd.TOP else dir1
        approach_dir2 = -dir2 if self.butt_timber_2_end == TimberEnd.TOP else dir2
        
        # Pair must approach from opposite directions (antiparallel)
        if not equality_test(approach_dir1.dot(approach_dir2), -1):
            return "butt_timber_1 and butt_timber_2 must approach from opposite directions (antiparallel)"
        return None

    def check_face_aligned_and_orthogonal_butts(self) -> Optional[str]:
        """Return None if all timbers are face-aligned and the two butt timbers are orthogonal
        to each other (length directions perpendicular), else an error message."""
        err = self.check_face_aligned()
        if err is not None:
            return err
        if not are_timbers_orthogonal(self.butt_timber_1, self.butt_timber_2):
            return "butt_timber_1 and butt_timber_2 must be orthogonal to each other"
        return None

    def check_perfection(self) -> Optional[str]:
        """Return None if all timbers are perfect, else an error message."""
        if not self.butt_timber_1.is_perfect_timber():
            return "butt_timber_1 must be perfect"
        if not self.butt_timber_2.is_perfect_timber():
            return "butt_timber_2 must be perfect"
        if not self.receiving_timber.is_perfect_timber():
            return "receiving_timber must be perfect"
        return None


@dataclass(frozen=True)
class TripleButtJointTimberArrangement:
    """Three butt timbers meeting a single receiving timber.

    main_butt_timber_1 and main_butt_timber_2 form an opposing pair (antiparallel).
    awk_timber is the third butt timber pointing in a third cardinal direction.
    """
    main_butt_timber_1: TimberLike
    main_butt_timber_2: TimberLike
    awk_timber: TimberLike
    receiving_timber: TimberLike
    main_butt_timber_1_end: TimberEnd
    main_butt_timber_2_end: TimberEnd
    awk_timber_end: TimberEnd

    def check_face_aligned(self) -> Optional[str]:
        """Return None if all butt timbers are face-aligned with the receiving timber, else an error message."""
        if not are_timbers_face_aligned(self.main_butt_timber_1, self.receiving_timber):
            return "main_butt_timber_1 must be face-aligned with receiving_timber"
        if not are_timbers_face_aligned(self.main_butt_timber_2, self.receiving_timber):
            return "main_butt_timber_2 must be face-aligned with receiving_timber"
        if not are_timbers_face_aligned(self.awk_timber, self.receiving_timber):
            return "awk_timber must be face-aligned with receiving_timber"
        return None

    def check_face_aligned_cardinal_and_opposing_butts(self) -> Optional[str]:
        """Return None if:
        - all timbers are face-aligned,
        - each butt timber's length direction is orthogonal to the receiving timber (cardinal),
        - all three butt timbers are in different cardinal directions, and
        - main_butt_timber_1 and main_butt_timber_2 are antiparallel (pointing towards each other).
        """
        err = self.check_face_aligned()
        if err is not None:
            return err
        recv_len = self.receiving_timber.get_length_direction_global()
        dir_main1 = self.main_butt_timber_1.get_length_direction_global()
        dir_main2 = self.main_butt_timber_2.get_length_direction_global()
        dir_awk = self.awk_timber.get_length_direction_global()
        butt_dirs = [
            ("main_butt_timber_1", dir_main1),
            ("main_butt_timber_2", dir_main2),
            ("awk_timber", dir_awk),
        ]
        for name, d in butt_dirs:
            if not _are_directions_perpendicular(d, recv_len):
                return f"{name} length direction must be orthogonal to receiving_timber length direction"
        # All three must be in different cardinal directions (no two share the same direction)
        pairs = [(butt_dirs[i][0], butt_dirs[i][1], butt_dirs[j][0], butt_dirs[j][1])
                 for i in range(len(butt_dirs)) for j in range(i + 1, len(butt_dirs))]
        for name_i, dir_i, name_j, dir_j in pairs:
            if equality_test(dir_i.dot(dir_j), 1):
                return f"{name_i} and {name_j} must point in different cardinal directions"
        # Main pair must be antiparallel (pointing towards each other)
        if not equality_test(dir_main1.dot(dir_main2), -1):
            return "main_butt_timber_1 and main_butt_timber_2 must be antiparallel (pointing towards each other)"
        return None

    def check_perfection(self) -> Optional[str]:
        """Return None if all timbers are perfect, else an error message."""
        if not self.main_butt_timber_1.is_perfect_timber():
            return "main_butt_timber_1 must be perfect"
        if not self.main_butt_timber_2.is_perfect_timber():
            return "main_butt_timber_2 must be perfect"
        if not self.awk_timber.is_perfect_timber():
            return "awk_timber must be perfect"
        if not self.receiving_timber.is_perfect_timber():
            return "receiving_timber must be perfect"
        return None


@dataclass(frozen=True)
class QuadrupleButtJointTimberArrangement:
    """Four butt timbers meeting a single receiving timber, covering all four cardinal directions.

    main_butt_timber_1 and main_butt_timber_2 form one opposing pair (antiparallel).
    awk_1 and awk_2 form the second opposing pair (antiparallel, on the perpendicular axis).
    """
    main_butt_timber_1: TimberLike
    main_butt_timber_2: TimberLike
    awk_1: TimberLike
    awk_2: TimberLike
    receiving_timber: TimberLike
    main_butt_timber_1_end: TimberEnd
    main_butt_timber_2_end: TimberEnd
    awk_1_end: TimberEnd
    awk_2_end: TimberEnd

    def check_face_aligned(self) -> Optional[str]:
        """Return None if all butt timbers are face-aligned with the receiving timber, else an error message."""
        if not are_timbers_face_aligned(self.main_butt_timber_1, self.receiving_timber):
            return "main_butt_timber_1 must be face-aligned with receiving_timber"
        if not are_timbers_face_aligned(self.main_butt_timber_2, self.receiving_timber):
            return "main_butt_timber_2 must be face-aligned with receiving_timber"
        if not are_timbers_face_aligned(self.awk_1, self.receiving_timber):
            return "awk_1 must be face-aligned with receiving_timber"
        if not are_timbers_face_aligned(self.awk_2, self.receiving_timber):
            return "awk_2 must be face-aligned with receiving_timber"
        return None

    def check_face_aligned_cardinal_and_opposing_butts(self) -> Optional[str]:
        """Return None if:
        - all timbers are face-aligned,
        - each butt timber's length direction is orthogonal to the receiving timber (cardinal),
        - all four butt timbers are in different cardinal directions, and
        - main_butt_timber_1/main_butt_timber_2 are antiparallel and awk_1/awk_2 are antiparallel.
        """
        err = self.check_face_aligned()
        if err is not None:
            return err
        recv_len = self.receiving_timber.get_length_direction_global()
        dir_main1 = self.main_butt_timber_1.get_length_direction_global()
        dir_main2 = self.main_butt_timber_2.get_length_direction_global()
        dir_awk1 = self.awk_1.get_length_direction_global()
        dir_awk2 = self.awk_2.get_length_direction_global()
        butt_dirs = [
            ("main_butt_timber_1", dir_main1),
            ("main_butt_timber_2", dir_main2),
            ("awk_1", dir_awk1),
            ("awk_2", dir_awk2),
        ]
        for name, d in butt_dirs:
            if not _are_directions_perpendicular(d, recv_len):
                return f"{name} length direction must be orthogonal to receiving_timber length direction"
        # All four must be in different cardinal directions (no two share the same direction)
        pairs = [(butt_dirs[i][0], butt_dirs[i][1], butt_dirs[j][0], butt_dirs[j][1])
                 for i in range(len(butt_dirs)) for j in range(i + 1, len(butt_dirs))]
        for name_i, dir_i, name_j, dir_j in pairs:
            if equality_test(dir_i.dot(dir_j), 1):
                return f"{name_i} and {name_j} must point in different cardinal directions"
        # Main pair must be antiparallel
        if not equality_test(dir_main1.dot(dir_main2), -1):
            return "main_butt_timber_1 and main_butt_timber_2 must be antiparallel (pointing towards each other)"
        # Awk pair must be antiparallel
        if not equality_test(dir_awk1.dot(dir_awk2), -1):
            return "awk_1 and awk_2 must be antiparallel (pointing towards each other)"
        return None

    def check_perfection(self) -> Optional[str]:
        """Return None if all timbers are perfect, else an error message."""
        if not self.main_butt_timber_1.is_perfect_timber():
            return "main_butt_timber_1 must be perfect"
        if not self.main_butt_timber_2.is_perfect_timber():
            return "main_butt_timber_2 must be perfect"
        if not self.awk_1.is_perfect_timber():
            return "awk_1 must be perfect"
        if not self.awk_2.is_perfect_timber():
            return "awk_2 must be perfect"
        if not self.receiving_timber.is_perfect_timber():
            return "receiving_timber must be perfect"
        return None

@dataclass(frozen=True)
class CrossCapJointTimberArrangement:
    """A butting post timber "capped" by two crossed timbers.
    """
    post_timber: TimberLike
    post_timber_end: TimberEnd
    cross_timber_1: TimberLike
    cross_timber_2: TimberLike

    def check_face_aligned_and_orthogonal(self) -> Optional[str]:
        if not are_timbers_face_aligned(self.cross_timber_1, self.post_timber):
            return "cross_timber_1 must be face-aligned with post_timber"
        if not are_timbers_face_aligned(self.cross_timber_2, self.post_timber):
            return "cross_timber_2 must be face-aligned with post_timber"
        if not are_timbers_face_aligned(self.cross_timber_1, self.cross_timber_2):
            return "cross_timber_1 and cross_timber_2 must be face-aligned"
        if not are_timbers_orthogonal(self.cross_timber_1, self.cross_timber_2):
            return "cross_timber_1 and cross_timber_2 must be orthogonal"
        if not are_timbers_orthogonal(self.cross_timber_1, self.post_timber):
            return "cross_timber_1 must be orthogonal to post_timber"
        if not are_timbers_orthogonal(self.cross_timber_2, self.post_timber):
            return "cross_timber_2 must be orthogonal to post_timber"
        return None

    def check_perfection(self) -> Optional[str]:
        """Return None if all timbers are perfect, else an error message."""
        if not self.post_timber.is_perfect_timber():
            return "post_timber must be perfect"
        if not self.cross_timber_1.is_perfect_timber():
            return "cross_timber_1 must be perfect"
        if not self.cross_timber_2.is_perfect_timber():
            return "cross_timber_2 must be perfect"
        return None

@dataclass(frozen=True)
class SpliceJointTimberArrangement:
    timber1: TimberLike
    timber2: TimberLike
    timber1_end: TimberEnd
    timber2_end: TimberEnd 
    front_face_on_timber1: Optional[TimberLongFace] = None

    def check_face_aligned_and_parallel_axis(self) -> Optional[str]:
        """Return None if timbers are face-aligned and have parallel length axes, else an error message."""
        if not are_timbers_face_aligned(self.timber1, self.timber2):
            return "Timbers must be face-aligned"
        if not are_timbers_parallel(self.timber1, self.timber2):
            return "Timbers must have parallel length axes"
        return None

    def check_perfection(self) -> Optional[str]:
        """Return None if both timbers are perfect, else an error message."""
        if not self.timber1.is_perfect_timber():
            return "timber1 must be perfect"
        if not self.timber2.is_perfect_timber():
            return "timber2 must be perfect"
        return None


@dataclass(frozen=True)
class CornerJointTimberArrangement:
    timber1: TimberLike
    timber2: TimberLike
    timber1_end: TimberEnd
    timber2_end: TimberEnd
    front_face_on_timber1: Optional[TimberLongFace] = None

    def compute_normalized_timber_cross_product(self) -> Direction3D:
        """Compute the normalized cross product of timber1 and timber2 length directions."""
        return normalize_vector(cross_product(self.timber1.get_length_direction_global(), self.timber2.get_length_direction_global()))

    def check_plane_aligned(self) -> Optional[str]:
        """Return None if timbers are plane-aligned and front face is in plane, else an error message."""
        if not are_timbers_plane_aligned(self.timber1, self.timber2):
            return "Timbers must be plane-aligned"
        if self.front_face_on_timber1 is not None and not are_vectors_parallel(
            self.timber1.get_face_direction_global(self.front_face_on_timber1),
            self.compute_normalized_timber_cross_product(),
        ):
            return "front_face_on_timber1 must point in the aligned plane normal"
        return None

    def check_face_aligned_and_orthogonal(self) -> Optional[str]:
        """Return None if timbers are face-aligned and orthogonal, else an error message."""
        if not are_timbers_face_aligned(self.timber1, self.timber2):
            return "Timbers must be face-aligned"
        if not are_timbers_orthogonal(self.timber1, self.timber2):
            return "Timbers must be orthogonal"
        return None

    def check_perfection(self) -> Optional[str]:
        """Return None if both timbers are perfect, else an error message."""
        if not self.timber1.is_perfect_timber():
            return "timber1 must be perfect"
        if not self.timber2.is_perfect_timber():
            return "timber2 must be perfect"
        return None


@dataclass(frozen=True)
class CrossJointTimberArrangement:
    timber1: TimberLike
    timber2: TimberLike
    front_face_on_timber1: Optional[TimberLongFace] = None

    def compute_normalized_timber_cross_product(self) -> Direction3D:
        """Compute the normalized cross product of timber1 and timber2 length directions."""
        return normalize_vector(cross_product(self.timber1.get_length_direction_global(), self.timber2.get_length_direction_global()))

    def check_plane_aligned(self) -> Optional[str]:
        """Return None if timbers are plane-aligned and front face is in plane, else an error message."""
        if not are_timbers_plane_aligned(self.timber1, self.timber2):
            return "Timbers must be plane-aligned"
        if self.front_face_on_timber1 is not None and not are_vectors_parallel(
            self.timber1.get_face_direction_global(self.front_face_on_timber1),
            self.compute_normalized_timber_cross_product(),
        ):
            return "front_face_on_timber1 must point in the aligned plane normal"
        return None

    def check_face_aligned_and_orthogonal(self) -> Optional[str]:
        """Return None if timbers are face-aligned and orthogonal, else an error message."""
        if not are_timbers_face_aligned(self.timber1, self.timber2):
            return "Timbers must be face-aligned"
        if not are_timbers_orthogonal(self.timber1, self.timber2):
            return "Timbers must be orthogonal"
        return None

    def check_perfection(self) -> Optional[str]:
        """Return None if both timbers are perfect, else an error message."""
        if not self.timber1.is_perfect_timber():
            return "timber1 must be perfect"
        if not self.timber2.is_perfect_timber():
            return "timber2 must be perfect"
        return None


@dataclass(frozen=True)
class BraceJointTimberArrangement:
    timber1: TimberLike
    timber2: TimberLike
    brace_timber: TimberLike
    timber1_end: TimberEnd
    timber2_end: TimberEnd
    front_face_on_timber1: Optional[TimberLongFace] = None

    def check_perfection(self) -> Optional[str]:
        """Return None if all timbers are perfect, else an error message."""
        if not self.timber1.is_perfect_timber():
            return "timber1 must be perfect"
        if not self.timber2.is_perfect_timber():
            return "timber2 must be perfect"
        if not self.brace_timber.is_perfect_timber():
            return "brace_timber must be perfect"
        return None


# =========================================
# internal helpers
# =========================================



def _are_directions_perpendicular(direction1: Direction3D, direction2: Direction3D, tolerance: Optional[Numeric] = None) -> bool:
    """
    Check if two direction vectors are perpendicular (orthogonal).
    
    Args:
        direction1: First direction vector
        direction2: Second direction vector
        tolerance: Optional tolerance for approximate comparison. If None, automatically
                   uses exact comparison for rational values or fuzzy comparison for floats.
    
    Returns:
        True if the directions are perpendicular, False otherwise
    """
    dot_product = direction1.dot(direction2)
    
    if tolerance is None:
        # Use automatic comparison (SymPy .equals() for symbolic, epsilon for floats)
        return zero_test(dot_product)
    else:
        # Use provided tolerance for approximate comparison
        return Abs(dot_product) < tolerance

def _are_directions_parallel(direction1: Direction3D, direction2: Direction3D, tolerance: Optional[Numeric] = None) -> bool:
    """
    Check if two direction vectors are parallel (or anti-parallel).
    
    Args:
        direction1: First direction vector
        direction2: Second direction vector
        tolerance: Optional tolerance for approximate comparison. If None, automatically
                   uses exact comparison for rational values or fuzzy comparison for floats.
    
    Returns:
        True if the directions are parallel, False otherwise
    """
    dot_product = direction1.dot(direction2)
    dot_mag = Abs(dot_product)
    
    if tolerance is None:
        # Use automatic comparison (SymPy .equals() for symbolic, epsilon for floats)
        return equality_test(dot_mag, 1)
    else:
        # Use provided tolerance for approximate comparison
        return Abs(dot_mag - 1) < tolerance
