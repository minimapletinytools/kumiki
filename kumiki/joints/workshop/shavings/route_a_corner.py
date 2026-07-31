
# helpers for corner joints consisting of a profile extruded along the corner joint's axis on both timbers

from kumiki.rule import V3, V2
from kumiki.construction import CornerJointTimberArrangement
from kumiki.cutcsg import ConvexPolygonExtrusion
from typing import List, Tuple
from kumiki.timber import Cutting

# PLACEHOLDERS

def find_point_corner_position(arrangement: CornerJointTimberArrangement) -> V3:
    # returns the pointy corner position of timber1 on front_face_on_timber1
    pass

def set_normal_corner_joint_end_cuts_on_cutting(arrangement : CornerJointTimberArrangement, cutting: Cutting) -> Cutting:
    # set the end cuts the same way you would in plain_miter_joint
    pass

def route_profile(arrangement: CornerJointTimberArrangement, profile: List[V2]) -> Tuple[ConvexPolygonExtrusion, ConvexPolygonExtrusion]:
    # I guess profile should be relative to the pointy corner. The orientation is based as if you were looking in the timber1_end direction and standing on front_face_on_timber1 with normal coordinates.
    #marking_space = 
    pass
