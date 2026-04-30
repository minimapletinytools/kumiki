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
        s = Stickout.symmetric(Rational(1, 5))  # Both sides extend 0.2m from centerline
        
        # No stickout
        s = Stickout.nostickout()  # Both sides are 0
        
        # Asymmetric stickout
        s = Stickout(Rational(1, 10), Rational(2, 5))  # Left extends 0.1m, right extends 0.4m from centerline
        
        # Stickout from outside faces
        s = Stickout(Rational(1, 10), Rational(1, 5), StickoutReference.OUTSIDE, StickoutReference.OUTSIDE)
    """
    stickout1: Numeric = Integer(0)
    stickout2: Numeric = Integer(0)
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
        return cls(Integer(0), Integer(0))


# ============================================================================
# Timber Creation Functions
# ============================================================================

def create_timber(bottom_position: V3, length: Numeric, size: V2, 
                  length_direction: Direction3D, width_direction: Direction3D, ticket: Optional[Union[TimberTicket, str]] = None) -> Timber:
    """
    Creates a timber at bottom_position with given dimensions and rotates it 
    to the length_direction and width_direction
    
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
    length_direction = create_v3(Integer(0), Integer(0), Integer(1))
    
    # Align timber face direction with outgoing boundary side
    # Face direction is in the XY plane along the outgoing side
    width_direction = create_v3(outgoing_dir_normalized[0], outgoing_dir_normalized[1], Integer(0))
    
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

    from sympy import Rational
    if location_type == FootprintLocation.INSIDE:
        # Center-origin timber: move center inward by half size in both axes.
        offset_x = timber_width / Rational(2) * outgoing_dir_normalized[0] + timber_depth / Rational(2) * prev_dir_normalized[0]
        offset_y = timber_width / Rational(2) * outgoing_dir_normalized[1] + timber_depth / Rational(2) * prev_dir_normalized[1]
        bottom_position = create_v3(corner_x + offset_x, corner_y + offset_y, Integer(0))

    elif location_type == FootprintLocation.OUTSIDE:
        # Center-origin timber: move center outward by half size in both axes.
        offset_x = -timber_width / Rational(2) * outgoing_dir_normalized[0] - timber_depth / Rational(2) * prev_dir_normalized[0]
        offset_y = -timber_width / Rational(2) * outgoing_dir_normalized[1] - timber_depth / Rational(2) * prev_dir_normalized[1]
        bottom_position = create_v3(corner_x + offset_x, corner_y + offset_y, Integer(0))

    else:  # CENTER
        # Center of bottom face lies on the boundary corner.
        bottom_position = create_v3(corner_x, corner_y, Integer(0))
    
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
    length_direction = create_v3(Integer(0), Integer(0), Integer(1))
    
    # Face direction is parallel to the boundary side
    width_direction = create_v3(side_dir_normalized[0], side_dir_normalized[1], Integer(0))
    
    # Calculate bottom position based on location type
    if location_type == FootprintLocation.CENTER:
        # Center of bottom face is on the point
        # No offset needed since timber local origin is at center of bottom face
        bottom_position = create_v3(point_x, point_y, Integer(0))
        
    elif location_type == FootprintLocation.INSIDE:
        # One edge of bottom face lies on boundary side
        # Center of that edge is at the point
        # Post extends inside (in direction of inward normal)
        # Offset the center by half depth in the inward direction
        from sympy import Rational
        bottom_position = create_v3(point_x + inward_x * timber_depth / Rational(2), 
                                         point_y + inward_y * timber_depth / Rational(2), 
                                         Integer(0))
        
    else:  # OUTSIDE
        # One edge of bottom face lies on boundary side
        # Center of that edge is at the point
        # Post extends outside (opposite of inward normal)
        # Offset the center by half depth in the outward direction
        from sympy import Rational
        bottom_position = create_v3(point_x - inward_x * timber_depth / Rational(2), 
                                         point_y - inward_y * timber_depth / Rational(2), 
                                         Integer(0))
    
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
    width_direction = create_v3(Integer(0), Integer(0), Integer(1))
    
    # The timber's orientation will be:
    #   X-axis (width/size[0]) = width_direction = (0, 0, 1) = vertical (up)
    #   Y-axis (height/size[1]) = length × face = perpendicular to boundary in XY plane
    #   Z-axis (length) = length_direction = along boundary side
    # Therefore, size[1] is the dimension perpendicular to the boundary
    timber_height = size[1]
    
    # Calculate bottom position based on location type
    # Start at the start_point on the boundary side - keep exact
    bottom_position = create_v3(start_point[0], start_point[1], Integer(0))
    
    # Apply offset based on location type
    if location_type == FootprintLocation.INSIDE:
        # Position so one edge lies on the boundary side, timber extends inward
        # Move the centerline inward by half the timber height (perpendicular dimension)
        from sympy import Rational
        bottom_position = bottom_position + inward_normal * (timber_height / Rational(2))
    elif location_type == FootprintLocation.OUTSIDE:
        # Position so one edge lies on the boundary side, timber extends outward
        # Move the centerline outward by half the timber height (perpendicular dimension)
        from sympy import Rational
        bottom_position = bottom_position - inward_normal * (timber_height / Rational(2))
    # For CENTER, no offset needed - centerline is already on the boundary side
    
    return create_timber(bottom_position, length, size, length_direction, width_direction, ticket=ticket)

def stretch_timber(timber: Timber, end: TimberReferenceEnd, overlap_length: Numeric, 
                  extend_length: Numeric) -> Timber:
    """
    Creates a new timber extending the original timber by a given length.

    The original timber is conceptually discarded and replaced with a new timber that is the original timber plus the extension.

    Args:
        end: The end of the timber to extend
        overlap_length: Length of timber to overlap with existing timber
        extend_length: Length of timber to extend beyond the end of the original timber (does not include the overlap length)
    """
    assert isinstance(end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(end).__name__}"
    # Calculate new position based on end
    if end == TimberReferenceEnd.TOP:
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
    bottom_ticket = ticket1 if ticket1 is not None else f"{timber.ticket.name}_bottom"
    top_ticket = ticket2 if ticket2 is not None else f"{timber.ticket.name}_top"
    
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

def join_timbers(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin, 
                location_on_timber1: Numeric,
                location_on_timber2: Optional[Numeric] = None,
                lateral_offset: Numeric = Integer(0),
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
                       Defaults to Integer(0) (no offset).
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
        # Project location_on_timber1 to timber2's Z axis
        pos2 = Matrix([pos1[0], pos1[1], timber2.get_bottom_position_global()[2] + location_on_timber1])
    
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
        
        if dot_product < Rational(1, 2):  # < 0.5, meaning more perpendicular than parallel
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
    if lateral_offset != Integer(0):
        # Calculate offset direction (cross product of length vectors)
        offset_dir = normalize_vector(cross_product(timber1.get_length_direction_global(), length_direction))
    
    # Calculate the bottom position (start of timber)
    # Start from pos1 and move backward by stickout1 (always centerline)
    bottom_pos = pos1 - length_direction * stickout.stickout1
    
    # Apply offset to bottom position as well (if any offset was applied to center)
    if lateral_offset != Integer(0):
        bottom_pos += offset_dir * lateral_offset
    
    return create_timber(bottom_pos, timber_length, size, length_direction, width_direction, ticket=ticket)


def join_plane_aligned_on_place_aligned_timbers(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin,
                                                location_on_timber1: Numeric, location_on_timber2: Numeric,
                                                stickout: Stickout,
                                                size: V2,
                                                # lateral offset (in the axis perpendicular to the face parallel plane) from feature_to_mark_on_joining_timber
                                                lateral_offset_from_timber1: Numeric = Integer(0),
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
def join_face_aligned_on_face_aligned_timbers(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin,
                                                location_on_timber1: Numeric,
                                                stickout: Stickout,
                                                size: V2,
                                                lateral_offset_from_timber1: Numeric = Integer(0),
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
                        Defaults to Integer(0).
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
    #location_on_timber2 = max(Integer(0), min(timber2.length, location_on_timber2))
    
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
    longitudinal_offset = Rational(0)
    lateral_offset_adjustment = Rational(0)
    
    # Convert TimberFeature enum to geometric object if provided
    feature_geometry = None
    if feature_to_mark_on_joining_timber is not None:
        # Create a temporary timber to measure the feature on
        # This timber has the same cross-section and orientation as the final joining timber
        temp_timber_center = pos1  # Arbitrary position for temp timber
        temp_timber = create_timber(
            bottom_position=temp_timber_center,
            length=Rational(1),  # Arbitrary length
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
        from kumiki.rule import safe_compare, Comparison, safe_dot_product
        width_dot = safe_dot_product(plane_normal, width_direction)
        height_dot = safe_dot_product(plane_normal, height_direction)
        
        # Determine which axis has the strongest alignment (should be close to ±1)
        if Abs(width_dot) > Abs(height_dot):
            # Normal is aligned with width_direction (RIGHT/LEFT faces)
            if safe_compare(width_dot, 0, Comparison.GT):
                # RIGHT face (normal = +width_direction)
                longitudinal_offset = size[0] / 2
                lateral_offset_adjustment = Rational(0)
            else:
                # LEFT face (normal = -width_direction)
                longitudinal_offset = -size[0] / 2
                lateral_offset_adjustment = Rational(0)
        else:
            # Normal is aligned with height_direction (FRONT/BACK faces)
            if safe_compare(height_dot, 0, Comparison.GT):
                # FRONT face (normal = +height_direction)
                longitudinal_offset = Rational(0)
                lateral_offset_adjustment = size[1] / 2
            else:
                # BACK face (normal = -height_direction)
                longitudinal_offset = Rational(0)
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
        longitudinal_offset = Rational(0)
    
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
        centerline_stickout1 = stickout.stickout1 + perpendicular_size / Rational(2)
    elif stickout.stickoutReference1 == StickoutReference.OUTSIDE:
        # OUTSIDE: Extends from the face away from timber2
        # Subtract half the perpendicular size
        centerline_stickout1 = stickout.stickout1 - perpendicular_size / Rational(2)
    
    if stickout.stickoutReference2 == StickoutReference.INSIDE:
        # INSIDE: Extends from the face closest to timber1
        centerline_stickout2 = stickout.stickout2 + perpendicular_size / Rational(2)
    elif stickout.stickoutReference2 == StickoutReference.OUTSIDE:
        # OUTSIDE: Extends from the face away from timber1
        centerline_stickout2 = stickout.stickout2 - perpendicular_size / Rational(2)
    
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


@dataclass(frozen=True)
class ButtJointTimberArrangement:
    butt_timber: Timber
    receiving_timber: Timber
    butt_timber_end: TimberReferenceEnd
    front_face_on_butt_timber: Optional[TimberLongFace] = None

    # this is totally silly. please delete me. We're not doing any hard computations in here...
    _memo: Dict[str, Any] = field(default_factory=dict, repr=False)

    def compute_normalized_timber_cross_product(self) -> Direction3D:
        """Compute the normalized cross product of the butt timber and receiving timber length directions."""
        key = "normalized_timber_cross_product"
        if self._memo.get(key) is not None:
            return self._memo[key]
        result = normalize_vector(cross_product(self.butt_timber.get_length_direction_global(), self.receiving_timber.get_length_direction_global()))
        self._memo[key] = result
        return result

    def check_types_valid(self) -> Optional[str]:
        """Return None if all types are valid, otherwise an error message for use in assert."""
        if not isinstance(self.butt_timber, Timber):
            return f"butt_timber must be Timber, got {type(self.butt_timber).__name__}"
        if not isinstance(self.receiving_timber, Timber):
            return f"receiving_timber must be Timber, got {type(self.receiving_timber).__name__}"
        if not isinstance(self.butt_timber_end, TimberReferenceEnd):
            return f"butt_timber_end must be TimberReferenceEnd, got {type(self.butt_timber_end).__name__}"
        if self.front_face_on_butt_timber is not None and not isinstance(self.front_face_on_butt_timber, TimberLongFace):
            return f"front_face_on_butt_timber must be TimberLongFace or None, got {type(self.front_face_on_butt_timber).__name__}"
        return None

    def __post_init__(self):
        require_check(self.check_types_valid())

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


@dataclass(frozen=True)
class DoubleButtJointTimberArrangement:
    """Two butt timbers meeting a single receiving timber.

    Arrangements:
    - Opposing: butt_timber_1 and butt_timber_2 point in opposite cardinal directions
      (antiparallel, like spokes from either side of the receiving timber).
    - Orthogonal: butt_timber_1 and butt_timber_2 point in perpendicular cardinal directions
      (90° apart, like an L at the receiving timber).
    """
    butt_timber_1: Timber
    butt_timber_2: Timber
    receiving_timber: Timber
    butt_timber_1_end: TimberReferenceEnd
    butt_timber_2_end: TimberReferenceEnd
    front_face_on_butt_timber_1: Optional[TimberLongFace] = None

    def check_types_valid(self) -> Optional[str]:
        """Return None if all types are valid, otherwise an error message for use in assert."""
        if not isinstance(self.butt_timber_1, Timber):
            return f"butt_timber_1 must be Timber, got {type(self.butt_timber_1).__name__}"
        if not isinstance(self.butt_timber_2, Timber):
            return f"butt_timber_2 must be Timber, got {type(self.butt_timber_2).__name__}"
        if not isinstance(self.receiving_timber, Timber):
            return f"receiving_timber must be Timber, got {type(self.receiving_timber).__name__}"
        if not isinstance(self.butt_timber_1_end, TimberReferenceEnd):
            return f"butt_timber_1_end must be TimberReferenceEnd, got {type(self.butt_timber_1_end).__name__}"
        if not isinstance(self.butt_timber_2_end, TimberReferenceEnd):
            return f"butt_timber_2_end must be TimberReferenceEnd, got {type(self.butt_timber_2_end).__name__}"
        if self.front_face_on_butt_timber_1 is not None and not isinstance(self.front_face_on_butt_timber_1, TimberLongFace):
            return (
                "front_face_on_butt_timber_1 must be TimberLongFace or None, "
                f"got {type(self.front_face_on_butt_timber_1).__name__}"
            )
        return None

    def __post_init__(self):
        require_check(self.check_types_valid())

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
        approach_dir1 = -dir1 if self.butt_timber_1_end == TimberReferenceEnd.TOP else dir1
        approach_dir2 = -dir2 if self.butt_timber_2_end == TimberReferenceEnd.TOP else dir2
        
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


@dataclass(frozen=True)
class TripleButtJointTimberArrangement:
    """Three butt timbers meeting a single receiving timber.

    main_butt_timber_1 and main_butt_timber_2 form an opposing pair (antiparallel).
    awk_timber is the third butt timber pointing in a third cardinal direction.
    """
    main_butt_timber_1: Timber
    main_butt_timber_2: Timber
    awk_timber: Timber
    receiving_timber: Timber
    main_butt_timber_1_end: TimberReferenceEnd
    main_butt_timber_2_end: TimberReferenceEnd
    awk_timber_end: TimberReferenceEnd

    def check_types_valid(self) -> Optional[str]:
        """Return None if all types are valid, otherwise an error message for use in assert."""
        if not isinstance(self.main_butt_timber_1, Timber):
            return f"main_butt_timber_1 must be Timber, got {type(self.main_butt_timber_1).__name__}"
        if not isinstance(self.main_butt_timber_2, Timber):
            return f"main_butt_timber_2 must be Timber, got {type(self.main_butt_timber_2).__name__}"
        if not isinstance(self.awk_timber, Timber):
            return f"awk_timber must be Timber, got {type(self.awk_timber).__name__}"
        if not isinstance(self.receiving_timber, Timber):
            return f"receiving_timber must be Timber, got {type(self.receiving_timber).__name__}"
        if not isinstance(self.main_butt_timber_1_end, TimberReferenceEnd):
            return f"main_butt_timber_1_end must be TimberReferenceEnd, got {type(self.main_butt_timber_1_end).__name__}"
        if not isinstance(self.main_butt_timber_2_end, TimberReferenceEnd):
            return f"main_butt_timber_2_end must be TimberReferenceEnd, got {type(self.main_butt_timber_2_end).__name__}"
        if not isinstance(self.awk_timber_end, TimberReferenceEnd):
            return f"awk_timber_end must be TimberReferenceEnd, got {type(self.awk_timber_end).__name__}"
        return None

    def __post_init__(self):
        require_check(self.check_types_valid())

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


@dataclass(frozen=True)
class QuadrupleButtJointTimberArrangement:
    """Four butt timbers meeting a single receiving timber, covering all four cardinal directions.

    main_butt_timber_1 and main_butt_timber_2 form one opposing pair (antiparallel).
    awk_1 and awk_2 form the second opposing pair (antiparallel, on the perpendicular axis).
    """
    main_butt_timber_1: Timber
    main_butt_timber_2: Timber
    awk_1: Timber
    awk_2: Timber
    receiving_timber: Timber
    main_butt_timber_1_end: TimberReferenceEnd
    main_butt_timber_2_end: TimberReferenceEnd
    awk_1_end: TimberReferenceEnd
    awk_2_end: TimberReferenceEnd

    def check_types_valid(self) -> Optional[str]:
        """Return None if all types are valid, otherwise an error message for use in assert."""
        if not isinstance(self.main_butt_timber_1, Timber):
            return f"main_butt_timber_1 must be Timber, got {type(self.main_butt_timber_1).__name__}"
        if not isinstance(self.main_butt_timber_2, Timber):
            return f"main_butt_timber_2 must be Timber, got {type(self.main_butt_timber_2).__name__}"
        if not isinstance(self.awk_1, Timber):
            return f"awk_1 must be Timber, got {type(self.awk_1).__name__}"
        if not isinstance(self.awk_2, Timber):
            return f"awk_2 must be Timber, got {type(self.awk_2).__name__}"
        if not isinstance(self.receiving_timber, Timber):
            return f"receiving_timber must be Timber, got {type(self.receiving_timber).__name__}"
        if not isinstance(self.main_butt_timber_1_end, TimberReferenceEnd):
            return f"main_butt_timber_1_end must be TimberReferenceEnd, got {type(self.main_butt_timber_1_end).__name__}"
        if not isinstance(self.main_butt_timber_2_end, TimberReferenceEnd):
            return f"main_butt_timber_2_end must be TimberReferenceEnd, got {type(self.main_butt_timber_2_end).__name__}"
        if not isinstance(self.awk_1_end, TimberReferenceEnd):
            return f"awk_1_end must be TimberReferenceEnd, got {type(self.awk_1_end).__name__}"
        if not isinstance(self.awk_2_end, TimberReferenceEnd):
            return f"awk_2_end must be TimberReferenceEnd, got {type(self.awk_2_end).__name__}"
        return None

    def __post_init__(self):
        require_check(self.check_types_valid())

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


@dataclass(frozen=True)
class SpliceJointTimberArrangement:
    timber1: Timber
    timber2: Timber
    timber1_end: TimberReferenceEnd
    timber2_end: TimberReferenceEnd 
    front_face_on_timber1: Optional[TimberLongFace] = None

    def check_types_valid(self) -> Optional[str]:
        """Return None if all types are valid, otherwise an error message for use in assert."""
        if not isinstance(self.timber1, Timber):
            return f"timber1 must be Timber, got {type(self.timber1).__name__}"
        if not isinstance(self.timber2, Timber):
            return f"timber2 must be Timber, got {type(self.timber2).__name__}"
        if not isinstance(self.timber1_end, TimberReferenceEnd):
            return f"timber1_end must be TimberReferenceEnd, got {type(self.timber1_end).__name__}"
        if not isinstance(self.timber2_end, TimberReferenceEnd):
            return f"timber2_end must be TimberReferenceEnd, got {type(self.timber2_end).__name__}"
        if self.front_face_on_timber1 is not None and not isinstance(self.front_face_on_timber1, TimberLongFace):
            return f"front_face_on_timber1 must be TimberLongFace or None, got {type(self.front_face_on_timber1).__name__}"
        return None

    def __post_init__(self):
        require_check(self.check_types_valid())

    def check_face_aligned_and_parallel_axis(self) -> Optional[str]:
        """Return None if timbers are face-aligned and have parallel length axes, else an error message."""
        if not are_timbers_face_aligned(self.timber1, self.timber2):
            return "Timbers must be face-aligned"
        if not are_timbers_parallel(self.timber1, self.timber2):
            return "Timbers must have parallel length axes"
        return None


@dataclass(frozen=True)
class CornerJointTimberArrangement:
    timber1: Timber
    timber2: Timber
    timber1_end: TimberReferenceEnd
    timber2_end: TimberReferenceEnd
    front_face_on_timber1: Optional[TimberLongFace] = None

    def check_types_valid(self) -> Optional[str]:
        """Return None if all types are valid, otherwise an error message for use in assert."""
        if not isinstance(self.timber1, Timber):
            return f"timber1 must be Timber, got {type(self.timber1).__name__}"
        if not isinstance(self.timber2, Timber):
            return f"timber2 must be Timber, got {type(self.timber2).__name__}"
        if not isinstance(self.timber1_end, TimberReferenceEnd):
            return f"timber1_end must be TimberReferenceEnd, got {type(self.timber1_end).__name__}"
        if not isinstance(self.timber2_end, TimberReferenceEnd):
            return f"timber2_end must be TimberReferenceEnd, got {type(self.timber2_end).__name__}"
        if self.front_face_on_timber1 is not None and not isinstance(self.front_face_on_timber1, TimberLongFace):
            return f"front_face_on_timber1 must be TimberLongFace or None, got {type(self.front_face_on_timber1).__name__}"
        return None

    def __post_init__(self):
        require_check(self.check_types_valid())

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


@dataclass(frozen=True)
class CrossJointTimberArrangement:
    timber1: Timber
    timber2: Timber
    front_face_on_timber1: Optional[TimberLongFace] = None

    def check_types_valid(self) -> Optional[str]:
        """Return None if all types are valid, otherwise an error message for use in assert."""
        if not isinstance(self.timber1, Timber):
            return f"timber1 must be Timber, got {type(self.timber1).__name__}"
        if not isinstance(self.timber2, Timber):
            return f"timber2 must be Timber, got {type(self.timber2).__name__}"
        if self.front_face_on_timber1 is not None and not isinstance(self.front_face_on_timber1, TimberLongFace):
            return f"front_face_on_timber1 must be TimberLongFace or None, got {type(self.front_face_on_timber1).__name__}"
        return None

    def __post_init__(self):
        require_check(self.check_types_valid())

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


@dataclass(frozen=True)
class BraceJointTimberArrangement:
    timber1: Timber
    timber2: Timber
    brace_timber: Timber
    timber1_end: TimberReferenceEnd
    timber2_end: TimberReferenceEnd
    front_face_on_timber1: Optional[TimberLongFace] = None

    def check_types_valid(self) -> Optional[str]:
        """Return None if all types are valid, otherwise an error message for use in assert."""
        if not isinstance(self.timber1, Timber):
            return f"timber1 must be Timber, got {type(self.timber1).__name__}"
        if not isinstance(self.timber2, Timber):
            return f"timber2 must be Timber, got {type(self.timber2).__name__}"
        if not isinstance(self.brace_timber, Timber):
            return f"brace_timber must be Timber, got {type(self.brace_timber).__name__}"
        if not isinstance(self.timber1_end, TimberReferenceEnd):
            return f"timber1_end must be TimberReferenceEnd, got {type(self.timber1_end).__name__}"
        if not isinstance(self.timber2_end, TimberReferenceEnd):
            return f"timber2_end must be TimberReferenceEnd, got {type(self.timber2_end).__name__}"
        if self.front_face_on_timber1 is not None and not isinstance(self.front_face_on_timber1, TimberLongFace):
            return f"front_face_on_timber1 must be TimberLongFace or None, got {type(self.front_face_on_timber1).__name__}"
        return None

    def __post_init__(self):
        require_check(self.check_types_valid())


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
