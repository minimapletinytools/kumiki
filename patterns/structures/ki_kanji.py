# Last checked on kumiki 0.9.1
"""The kanji 木 ("tree, wood") as a timber frame, standing in the XZ plane.

A 4x4 post is the vertical stroke. Two 4x5 beams form the horizontal stroke, meeting at the
post in a splined opposing double butt joint with square pegs. Two 4x6 side strokes fall away
from the post at 45 degrees below the beam, each in a mortise and tenon with one round peg.
The beams' tops arch down to their tips; the side strokes' tops are scooped so they sweep up.
"""

from typing import Optional

from kumiki import *
from kumiki.csg.pathcsg import Path as ProfilePath


POST_SIZE = create_v2(inches(4), inches(4))
BEAM_SIZE = create_v2(inches(4), inches(5))   # 4" through the frame (Y), 5" tall (Z)
SIDE_STROKE_SIZE = create_v2(inches(4), inches(6))   # 4" through the frame (Y), 6" in its plane

POST_HEIGHT = inches(48)
BEAM_CENTER_HEIGHT = inches(33)
BEAM_LENGTH = inches(22)                       # post centerline to beam tip
SIDE_STROKE_LENGTH = inches(24)                # post centerline to stroke tip
SIDE_STROKE_ANGLE = degrees(45)                # below horizontal
# Where each side stroke's centerline meets the post's centerline: low enough that its top
# edge clears the beam's underside.
SIDE_STROKE_ROOT_HEIGHT = BEAM_CENTER_HEIGHT - BEAM_SIZE[1] / 2 - inches(3, 2)

BEAM_CROWN_DROP = inches(3, 2)                 # how far the beam top falls from post to tip
SIDE_STROKE_TENON_WIDTH = inches(7, 2)         # in the frame's plane, flush with the stroke's underside
SIDE_STROKE_PEG_FROM_SHOULDER = inches(1)
# Deepest at the peg, measured from the post centerline along the stroke.
SIDE_STROKE_SCOOP_DEEPEST_AT = POST_SIZE[0] / 2 / cos(SIDE_STROKE_ANGLE) + SIDE_STROKE_PEG_FROM_SHOULDER
# As deep as it can go there without cutting into the tenon.
SIDE_STROKE_SCOOP_DEPTH = SIDE_STROKE_SIZE[1] - SIDE_STROKE_TENON_WIDTH
POST_TOP_RADIUS = inches(6)


def _top_long_face(timber: Timber) -> TimberLongFace:
    return timber.get_closest_oriented_long_face_from_global_direction(create_v3(0, 0, 1))


def _short_edge(end: TimberEnd, face: TimberLongFace) -> TimberShortEdge:
    return TimberShortEdge[f"{end.name}_{face.name}"]


def _crown_cut(timber: Timber, end: TimberEnd, run: Numeric, drop: Numeric) -> Joint:
    """Return a cut that curves `timber`'s top face down by `drop` at `end`, flat again `run` in."""
    radius = (run * run + drop * drop) / (2 * drop)
    center = create_v2(run, radius)
    # From the point `drop` below the top at the end, around to the point level with the top `run` in.
    start_angle = atan2(drop - radius, -run)
    arc = ArcSegment(center=center, radius=radius, start_angle=start_angle, sweep_angle=-pi / 2 - start_angle)
    return cut_practice_path_extrusion_corner_end_decoration(
        timber=timber,
        cut_corner=_short_edge(end, _top_long_face(timber)),
        cut_path=[arc],
    )


def _scoop_cut(timber: Timber, deepest_at: Numeric, depth: Numeric) -> Joint:
    """Return a cut that hollows `timber`'s top face in one arc, `depth` deep, rising to the TOP end.

    `deepest_at` is the distance from the BOTTOM end to the arc's lowest point.
    """
    half_chord = timber.length - deepest_at
    radius = (half_chord * half_chord + depth * depth) / (2 * depth)
    top_face = _top_long_face(timber).to.face()
    up = timber.get_face_direction_global(top_face)
    top_at_middle = (
        timber.get_bottom_position_global()
        + timber.get_length_direction_global() * deepest_at
        + up * timber.get_size_in_face_normal_axis(top_face) / 2
    )
    along = timber.get_length_direction_global()
    across = top_face.rotate_about(TimberFace.TOP)
    across_dir = timber.get_face_direction_global(across)

    # Profile in (along, up) from the top face's middle: the arc below, closed by a box above.
    center = create_v2(0, radius - depth)
    start_angle = atan2(-center[1], -half_chord)
    arc = ArcSegment(center=center, radius=radius, start_angle=start_angle,
                     sweep_angle=atan2(-center[1], half_chord) - start_angle)
    above = timber.get_half_rough_size_in_face_normal_axis(top_face) + inches(1)
    corners = [arc.end, create_v2(half_chord, above), create_v2(-half_chord, above), arc.start]
    loop = ProfilePath([arc] + [StraightSegment(p, q) for p, q in zip(corners, corners[1:])])
    if safe_compare(loop.signed_area(), 0, Comparison.LT):
        loop = loop.reversed()
    scoop = PathExtrusion(
        path=loop,
        transform=Transform(position=top_at_middle, orientation=Orientation(Matrix([
            [along[i], up[i], across_dir[i]] for i in range(3)
        ]))),
        start_distance=-timber.get_half_rough_size_in_face_normal_axis(across.get_opposite_face()),
        end_distance=timber.get_half_rough_size_in_face_normal_axis(across),
        label=CutCSGLabel("scoop_arc"),
    )
    cutting = Cutting(
        timber=timber,
        negative_csg=adopt_csg(None, timber.transform, scoop),
        label=CutCSGLabel("scoop_decoration"),
    )
    return Joint(cuttings={timber.ticket.path: cutting}, ticket=JointTicket(joint_type="scoop_decoration"))


@frame
def ki_kanji(k: Optional[Kiwari] = None) -> Frame:
    post = create_axis_aligned_timber(
        bottom_position=create_v3(0, 0, 0),
        length=POST_HEIGHT,
        size=POST_SIZE,
        length_direction=TimberFace.TOP,
        width_direction=TimberFace.RIGHT,
        ticket=TimberTicket(path="post", tags=("vertical stroke",)),
    )

    # Each beam's TOP end is at the post's centerline.
    def beam(side: int, name: str) -> Timber:
        return create_axis_aligned_timber(
            bottom_position=create_v3(side * BEAM_LENGTH, 0, BEAM_CENTER_HEIGHT),
            length=BEAM_LENGTH,
            size=BEAM_SIZE,
            length_direction=TimberFace.LEFT if side > 0 else TimberFace.RIGHT,
            width_direction=TimberFace.FRONT,
            ticket=TimberTicket(path=name, tags=("horizontal stroke",)),
        )

    beam_W = beam(-1, "beam_W")
    beam_E = beam(1, "beam_E")

    # Each side stroke's BOTTOM end is at the post's centerline; it runs down and out.
    def side_stroke(side: int, name: str) -> Timber:
        return create_timber(
            length=SIDE_STROKE_LENGTH,
            size=SIDE_STROKE_SIZE,
            bottom_position=create_v3(0, 0, SIDE_STROKE_ROOT_HEIGHT),
            length_direction=create_v3(side * cos(SIDE_STROKE_ANGLE), 0, -sin(SIDE_STROKE_ANGLE)),
            width_direction=create_v3(0, 1, 0),
            ticket=TimberTicket(path=name, tags=("side stroke",)),
        )

    stroke_W = side_stroke(-1, "side_stroke_W")
    stroke_E = side_stroke(1, "side_stroke_E")

    # Spline slot faces down, so the beams' curved tops stay unbroken.
    beam_joint = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
        arrangement=DoubleButtJointTimberArrangement(
            receiving_timber=post,
            butt_timber_1=beam_W,
            butt_timber_1_end=TimberEnd.TOP,
            butt_timber_2=beam_E,
            butt_timber_2_end=TimberEnd.TOP,
            front_face_on_butt_timber_1=TimberLongFace.RIGHT,   # faces +Y; pegs go in from here
        ),
        slot_facing_end_on_receiving_timber=TimberEnd.BOTTOM,
        slot_thickness=inches(1),
        slot_depth=inches(2),
        spline_length=inches(14),
        spline_extra_depth=inches(1, 2),
        slot_symmetric_extra_length=inches(1, 8),
        peg_parameters=SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(3), scalar(0))],
            size=inches(5, 8),
        ),
    )

    # Mortises are bored square to the post face and the tenons cropped to them; each stops
    # short of the post's centerline so the two from opposite faces never meet.
    tenon_length = inches(4)
    mortise_depth = inches(7, 4)

    def side_stroke_joint(stroke: Timber) -> Joint:
        # Shift the tenon along the stroke's local Y so it is flush with the underside.
        underside = _top_long_face(stroke).to.face().get_opposite_face()
        flush_offset = (SIDE_STROKE_SIZE[1] - SIDE_STROKE_TENON_WIDTH) / 2
        tenon_y = flush_offset if underside == TimberFace.FRONT else -flush_offset
        return cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=post,
                butt_timber=stroke,
                butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.RIGHT,
            ),
            tenon_length=tenon_length,
            tenon_width_relative_to_joint=SIDE_STROKE_TENON_WIDTH,
            tenon_height_relative_to_joint=inches(3, 2),
            tenon_position=create_v2(0, tenon_y),
            mortise_depth=mortise_depth,
            bore_mortise_perpendicular_to_face=True,
            peg_parameters=SimplePegParameters(
                shape=PegShape.ROUND,
                peg_positions=[(SIDE_STROKE_PEG_FROM_SHOULDER, scalar(0))],
                size=inches(5, 8),
                tenon_hole_offset=mm(2),
            ),
        )

    decorations = [
        _crown_cut(beam_W, TimberEnd.BOTTOM, BEAM_LENGTH - POST_SIZE[0] / 2, BEAM_CROWN_DROP),
        _crown_cut(beam_E, TimberEnd.BOTTOM, BEAM_LENGTH - POST_SIZE[0] / 2, BEAM_CROWN_DROP),
        _scoop_cut(stroke_W, SIDE_STROKE_SCOOP_DEEPEST_AT, SIDE_STROKE_SCOOP_DEPTH),
        _scoop_cut(stroke_E, SIDE_STROKE_SCOOP_DEEPEST_AT, SIDE_STROKE_SCOOP_DEPTH),
        cut_practice_rounded_end_decoration(
            timber=post,
            rounded_face=TimberFace.FRONT,
            rounded_end=TimberFace.TOP,
            radius=POST_TOP_RADIUS,
            distance_from_end=POST_TOP_RADIUS,
        ),
    ]

    joints = [beam_joint, side_stroke_joint(stroke_W), side_stroke_joint(stroke_E), *decorations]
    return Frame.from_joints(joints, name="ki kanji", kiwari=k)
