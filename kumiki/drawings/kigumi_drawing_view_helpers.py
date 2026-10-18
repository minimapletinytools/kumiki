"""Camera helpers for kigumi's drawing views: which way each view looks, and how much of the model
it shows. World space, as lists of floats; the runner turns these into viewports.
"""

import math
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Sequence, Tuple

from ..viewer.rule_at_home import FloatList3

if TYPE_CHECKING:
    from ..timber import CutTimber

#: Leaves a margin around the model rather than framing it edge to edge.
DRAWING_EXTENT_PADDING = 1.15
#: A perspective view wants more room around the piece than an elevation does.
PREVIEW_EXTENT_PADDING = 1.6
# Where the preview search may look from. Every compass direction, and a few heights above the
# horizon -- never level with it or straight down, where an upright camera has no up left.
_PREVIEW_AZIMUTH_STEPS = 24
_PREVIEW_ELEVATIONS_DEG = (20.0, 35.0, 50.0)
# Where a single piece is looked at from, in its own frame: off to one side, above, and a little
# towards one end, so a long face, a short face and an end are all in view.
_PIECE_LOOK_IN_BOX = (0.38, 0.86, -0.55)


@dataclass(frozen=True)
class CameraFrame:
    """Which way a camera looks, and which way is across and up its screen. right x up == -look,
    the frame of a camera looking down its own -Z, which keeps the view from coming out mirrored."""
    right: FloatList3
    up: FloatList3
    look: FloatList3

    def as_dict(self) -> Dict[str, FloatList3]:
        return {"right": self.right, "up": self.up, "look": self.look}


def _cross(a: FloatList3, b: FloatList3) -> FloatList3:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def normalize(vec: FloatList3) -> FloatList3:
    """At length one; a zero vector is taken as up."""
    length = math.sqrt(sum(component * component for component in vec))
    return [component / length for component in vec] if length > 0 else [0.0, 0.0, 1.0]


def camera_looking_at_face(normal: FloatList3, along: FloatList3) -> CameraFrame:
    """Square-on to a face, with `along` (a timber's length) across the screen. The camera sits
    outside the face along its outward normal and looks back at it."""
    return CameraFrame(right=list(along), up=_cross(normal, along), look=[-component for component in normal])


def camera_frame_looking(look: FloatList3) -> CameraFrame:
    """Looking along `look`, kept upright: `up` is world Z with the part along the view taken out,
    which stops a three-quarter view arriving on its side."""
    forward = normalize(look)
    world_up = [0.0, 0.0, 1.0]
    along = sum(world_up[i] * forward[i] for i in range(3))
    up = normalize([world_up[i] - along * forward[i] for i in range(3)])
    return CameraFrame(right=normalize(_cross(forward, up)), up=up, look=forward)


def frame_from_look_and_up(look: FloatList3, up_hint: FloatList3) -> CameraFrame:
    """Looking along `look`, as close to `up_hint` as it can; upright when the hint is along the
    view, where it says nothing about which way is up."""
    forward = normalize(look)
    along = sum(up_hint[i] * forward[i] for i in range(3))
    up = [up_hint[i] - along * forward[i] for i in range(3)]
    if sum(component * component for component in up) < 1e-9:
        return camera_frame_looking(look)
    up = normalize(up)
    return CameraFrame(right=normalize(_cross(forward, up)), up=up, look=forward)


# --- what a view is fitted to -----------------------------------------------------------------

def cut_extent(cut_timber: 'CutTimber', stock_length: float) -> Tuple[float, float]:
    """Where the finished piece starts and ends along its own length.

    A timber with an end joint is not cut to length first, so its stock is not the piece that gets
    drawn: framing a view on the stock leaves the piece off centre by whatever the joint took off.
    """
    try:
        prism = cut_timber.get_perfect_timber_within_bounding_box_prism()
        start = float(prism.start_distance) if prism.start_distance is not None else 0.0
        end = float(prism.end_distance) if prism.end_distance is not None else stock_length
        return start, end
    except Exception as exc:
        warnings.warn(f"could not measure cut extent: {exc}")
        return 0.0, stock_length


def _floats(vec) -> FloatList3:
    return [float(vec[i, 0]) for i in range(3)]


def timber_world_corners(cut_timber: 'CutTimber') -> List[FloatList3]:
    """The 8 corners of a timber's finished piece, in world space."""
    timber = cut_timber.timber
    origin = _floats(timber.get_bottom_position_global())
    along = _floats(timber.get_length_direction_global())
    across = _floats(timber.get_width_direction_global())
    up = _floats(timber.get_height_direction_global())
    half_width = float(timber.size[0]) / 2.0
    half_height = float(timber.size[1]) / 2.0
    return [[origin[axis] + along[axis] * distance + across[axis] * width + up[axis] * height for axis in range(3)]
            for distance in cut_extent(cut_timber, float(timber.length))
            for width in (-half_width, half_width) for height in (-half_height, half_height)]


def world_bounds(cut_timbers: Sequence['CutTimber']) -> Tuple[FloatList3, FloatList3]:
    """(centre, half_size) of the finished pieces, world-aligned; a unit box if there are none."""
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for cut_timber in cut_timbers:
        for corner in timber_world_corners(cut_timber):
            for axis in range(3):
                lows[axis] = min(lows[axis], corner[axis])
                highs[axis] = max(highs[axis], corner[axis])
    if any(low == float("inf") for low in lows):
        return [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]
    return ([(lows[axis] + highs[axis]) / 2.0 for axis in range(3)],
            [(highs[axis] - lows[axis]) / 2.0 for axis in range(3)])


def view_extent(half_size: FloatList3, right: FloatList3, up: FloatList3, aspect: float = 1.0) -> float:
    """Half-height that fits a world-aligned box in a view with these screen axes.

    The viewer widens the frustum from the half-height by the viewport's aspect, so the width the
    box needs is divided by that aspect before the two are compared.
    """
    def projected(axis: FloatList3) -> float:
        return sum(abs(axis[i]) * half_size[i] for i in range(3))

    safe_aspect = aspect if aspect > 0 else 1.0
    needed = max(projected(up), projected(right) / safe_aspect)
    return max(0.001, needed * DRAWING_EXTENT_PADDING)


class OrientedBox(NamedTuple):
    """A box in the world: where it is, which way it lies, and how big it is.

    Not an axis-aligned bounding box. A single timber has its own axes and is usually not square to
    the world; orienting a view around its true box is the difference between seeing the piece and
    seeing the space it takes up.
    """

    centre: FloatList3
    axes: Tuple[FloatList3, FloatList3, FloatList3]
    half_sizes: Tuple[float, float, float]

    def reach(self, direction: FloatList3) -> float:
        """How far the box extends along a direction, from its centre."""
        return sum(abs(sum(direction[i] * self.axes[axis][i] for i in range(3))) * self.half_sizes[axis]
                   for axis in range(3))

    def silhouette_area(self, look: FloatList3) -> float:
        """How much of the box a viewer sees looking along `look`: each face pair's area, scaled by
        how squarely it faces the camera."""
        a, b, c = self.half_sizes
        areas = (4 * b * c, 4 * a * c, 4 * a * b)
        return sum(abs(sum(look[i] * self.axes[axis][i] for i in range(3))) * areas[axis] for axis in range(3))

    @property
    def longest_axis(self) -> int:
        return max(range(3), key=lambda axis: self.half_sizes[axis])


def world_box(centre: FloatList3, half_size: FloatList3) -> OrientedBox:
    """The world-aligned box a group of members occupies."""
    return OrientedBox(centre=centre, axes=([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]),
                       half_sizes=(half_size[0], half_size[1], half_size[2]))


def timber_box(cut_timber: 'CutTimber') -> OrientedBox:
    """One timber's own box: its axes, its section, and its cut extent (not its stock)."""
    timber = cut_timber.timber
    along = _floats(timber.get_length_direction_global())
    across = _floats(timber.get_width_direction_global())
    up = _floats(timber.get_height_direction_global())
    origin = _floats(timber.get_bottom_position_global())
    start, finish = cut_extent(cut_timber, float(timber.length))
    middle = (start + finish) / 2.0
    return OrientedBox(centre=[origin[i] + along[i] * middle for i in range(3)], axes=(along, across, up),
                       half_sizes=((finish - start) / 2.0, float(timber.size[0]) / 2.0, float(timber.size[1]) / 2.0))


def preview_extent(box: OrientedBox, frame: CameraFrame, aspect: float) -> float:
    """How much of the world the preview has to hold, at this angle."""
    needed = max(box.reach(frame.up), box.reach(frame.right) / aspect)
    return max(0.001, needed * PREVIEW_EXTENT_PADDING)


# --- preview orientation strategies -----------------------------------------------------------
#
# Two, because what makes a good angle depends on what is being drawn. `orient_by_search` is a
# guess-and-check and may not survive; both take an OrientedBox and the viewport's aspect, so either
# can be dropped without touching what calls it.

def _preview_look_candidates() -> List[FloatList3]:
    candidates: List[FloatList3] = []
    for elevation_deg in _PREVIEW_ELEVATIONS_DEG:
        elevation = math.radians(elevation_deg)
        for step in range(_PREVIEW_AZIMUTH_STEPS):
            azimuth = 2 * math.pi * step / _PREVIEW_AZIMUTH_STEPS
            # Looking down from above, so the z part is negative.
            candidates.append([math.cos(azimuth) * math.cos(elevation), math.sin(azimuth) * math.cos(elevation),
                               -math.sin(elevation)])
    return candidates


def orient_by_search(box: OrientedBox, aspect: float, preserve_up: bool = True) -> CameraFrame:
    """Try a few dozen angles and keep the one that shows the piece best.

    What is maximized is how long the box's longest axis appears once the view is sized to fit it.
    How much of the viewport the silhouette fills would always be won by looking down the length of
    the piece, which fits beautifully and shows nothing. Two angles that show it equally long are
    told apart by which shows more of it, so a square-on view loses to a three-quarter one.

    With `preserve_up` the candidates are upright, so world +Z stays up the screen: a frame read at
    a tilt is harder to follow than one drawn slightly smaller.

    There is very likely a closed form. Guessing and checking is fine: a few dozen candidates against
    one box, once per drawing, and the scoring can be changed by reading it.
    """
    longest = box.half_sizes[box.longest_axis]
    axis = box.axes[box.longest_axis]
    best_frame = camera_frame_looking([-1.0, 1.0, -0.75])
    best_length = -1.0
    best_area = -1.0
    for look in _preview_look_candidates():
        frames = [camera_frame_looking(look)]
        if not preserve_up:
            # Also allow the piece's own length to be the screen's up: a long timber in a tall
            # viewport, with the world on its side.
            frames.append(frame_from_look_and_up(look, axis))
        for frame in frames:
            extent = preview_extent(box, frame, aspect)
            across = sum(frame.right[i] * axis[i] for i in range(3)) * longest
            up_screen = sum(frame.up[i] * axis[i] for i in range(3)) * longest
            on_screen = math.sqrt(across * across + up_screen * up_screen) / extent
            area = box.silhouette_area(normalize(look))
            # Within a couple of percent counts as the same length, and then the view that shows
            # more of the piece wins.
            if on_screen > best_length * 1.02 or (on_screen > best_length * 0.98 and area > best_area):
                best_length = max(best_length, on_screen)
                best_area = area
                best_frame = frame
    return best_frame


def orient_from_box(box: OrientedBox, aspect: float) -> CameraFrame:
    """Look at a box from a fixed three-quarter angle in its own frame.

    For a single piece the box is the timber, so the angle that shows it well is the same every
    time in its own axes: a post and a brace at forty degrees get the same view of themselves. The
    piece is laid along whichever way the viewport is longer.
    """
    length, across, up = box.axes
    look = normalize([length[i] * _PIECE_LOOK_IN_BOX[0] + across[i] * _PIECE_LOOK_IN_BOX[1]
                      + up[i] * _PIECE_LOOK_IN_BOX[2] for i in range(3)])
    longest = box.axes[box.longest_axis]
    # A tall viewport wants the piece standing up in it, a wide one wants it lying down.
    return frame_from_look_and_up(look, longest if aspect < 1 else up)
