"""Whether a place in a drawing's view is hidden behind material.

Analytic, over the whole CSG: the line of sight is clipped exactly to the solid (cropcsg), not
sampled. Only the solid's inside hides; a line of sight along its surface does not.
"""

from ..csg.cropcsg import crop_line_to_segments_on_csg
from ..csg.cutcsg import CutCSG
from ..geometry import Line
from ..rule import V3, safe_dot_product, safe_normalize_vector

#: Material nearer the place than this is the surface it lies on, not something in front of it.
NUDGE = 1e-5
#: How far the line of sight is followed toward the camera. Only has to pass every solid.
REACH = 1e3


def sight_is_blocked(root: CutCSG, place: V3, toward_camera: V3) -> bool:
    """Whether the inside of *root* lies between *place* and the camera.

    Args:
        root: the solid that may be in the way, in its own local space.
        place: where the feature is, in that same space.
        toward_camera: the direction from *place* to the camera, in that same space.

    False when *root* cannot be clipped exactly (a curved primitive other than a cylinder).
    """
    direction = safe_normalize_vector(toward_camera)
    pieces = crop_line_to_segments_on_csg(Line(direction=direction, point=place), root, seed_reach=REACH, near=place)
    for piece in pieces or []:
        ahead = sorted(float(safe_dot_product(end - place, direction)) for end in (piece.start, piece.end))
        if ahead[1] <= NUDGE:
            continue
        middle = place + direction * ((max(ahead[0], NUDGE) + ahead[1]) / 2)
        if root.contains_point(middle) and not root.is_point_on_boundary(middle):
            return True
    return False
