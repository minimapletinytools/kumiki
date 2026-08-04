
# helpers for corner joints consisting of a profile extruded along the corner joint's axis on both timbers

from kumiki.measuring import MarkingSpace
from kumiki.rule import V3, V2
from kumiki.construction import CornerJointTimberArrangement
from kumiki.cutcsg import ConvexPolygonExtrusion
from typing import List, Tuple
from kumiki.timber import Cutting

# PLACEHOLDERS

def find_corner_marking_space(arrangement: CornerJointTimberArrangement) -> MarkingSpace:
    # returns the pointy corner position of timber1 on front_face_on_timber1
    # the orientation is looking in the timber1_end direction and standing on front_face_on_timber1
    assert False, "not implemented yet"


def set_normal_corner_joint_end_cuts_on_cutting(arrangement : CornerJointTimberArrangement, cutting: Cutting) -> Cutting:
    # set the end cuts the same way you would in plain_miter_joint
    assert False, "not implemented yet"

def route_profile(arrangement: CornerJointTimberArrangement, profile: List[V2]) -> Tuple[ConvexPolygonExtrusion, ConvexPolygonExtrusion]:

    # check if both timbers are perfect and warn if not
    # first determine if the last point in the profile is flush with either board i.e. -profile[-1].y and -profile[-2].y >= timber2.get_size_in_face_normal_axis(get_closest_oriented_face(y))
    # also +/-profile[-1].x and +/-profile[-2].x >= timber1.get_size_in_face_normal_axis(get_closest_oriented_face(x) (negative sign if is_timber2_left_of_timber1 is true, else positive sign)
    # actually may as well generalize that check to the last n point sin the profile!

    #draw the profile on timber1, to complete the profile, you go from the last point in the profile (profile[-1]) on timber1 to (0, profile[-1].y) and then (0,0), and then for timber2 its (proflie[-1].x, 0) and then (0,0), this will complete the profile
    # make the profile convex with decompose_simple_polygon_into_convex_pieces
    # extrude the profile on timber 1 to the face opposite of front_face_on_timber1
    # similar extrude the profile on timber2 across the entire dimension (you will need to figure this out as it may not align with timber1)

    assert False, "not implemented yet"


def double_rabbet_profile() -> List[V2]:
    # returns a profile for a double rabbet joint
    assert False, "not implemented yet"