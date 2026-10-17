"""Whether something under the pointer in a drawing's view is behind material.

A feature is behind material when its line of sight -- from where it was found, toward the
camera -- passes through the inside of a solid. Exact, from the CSG: the line is cropped to the
solid (cropcsg), and each piece it keeps is material, or the solid's surface if the piece only
grazes it.

Only the inside counts. A line of sight running exactly along a face seen edge-on lies on the
surface, which hides nothing -- a peg's cap seen edge-on, or the near edge of a flank, is seen.
Edges stacked along the view are a different question, answered from the candidates themselves:
see picking.split_hidden.

Carried over from PR #82 (branch `visibility`), which tested a whole feature's visibility for
measuring. Picking only asks about the place under the pointer, which is this.
"""

from typing import List

from ..csg.cropcsg import crop_line_to_segments_on_csg
from ..geometry import Line
from ..rule import create_v3

#: Material nearer the place than this is the surface it lies on, not something in front of it.
NUDGE = 1e-5
#: How far the line of sight is followed toward the camera. Only has to pass every solid.
REACH = 1e3


def sight_is_blocked(root, place: List[float], toward_camera: List[float]) -> bool:
    """Whether material lies between *place* and the camera, in *root*'s own space.

    A tree cropping cannot describe is not called blocking: what cannot be decided is seen.
    """
    norm = sum(c * c for c in toward_camera) ** 0.5
    if norm == 0:
        return False
    direction = [c / norm for c in toward_camera]
    line = Line(direction=create_v3(*direction), point=create_v3(*place))
    pieces = crop_line_to_segments_on_csg(line, root, seed_reach=REACH, near=create_v3(*place))
    for piece in pieces or []:
        start = [float(piece.start[i]) for i in range(3)]
        end = [float(piece.end[i]) for i in range(3)]
        ahead = lambda point: sum((point[i] - place[i]) * direction[i] for i in range(3))
        # Toward the camera from the place, by more than its own surface.
        if max(ahead(start), ahead(end)) <= NUDGE:
            continue
        # Of what is ahead, the middle: inside the solid, or only on its surface?
        lo, hi = max(min(ahead(start), ahead(end)), NUDGE), max(ahead(start), ahead(end))
        middle = create_v3(*(place[i] + direction[i] * (lo + hi) / 2 for i in range(3)))
        if root.contains_point(middle) and not root.is_point_on_boundary(middle):
            return True
    return False
