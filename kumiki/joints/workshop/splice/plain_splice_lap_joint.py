"""
Kumiki - Plain splice lap joint construction function
"""

from typing import Optional

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from ..shavings import chop_lap_on_timber_ends


def cut_plain_splice_lap_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
    lap_length: Numeric,
    top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Numeric,
    lap_depth: Optional[Numeric] = None,
) -> Joint:
    """
    Creates a splice lap joint between two parallel timber ends with interlocking relief cuts.

    One timber has material removed from the specified face; the other has material
    removed from the opposite face. Timbers must be parallel and face-aligned.

        arrangement.front_face_on_timber1
        v           |--------| lap_length
    ╔════════════════════════╗╔══════╗  -
    ║timber1                 ║║      ║  | lap_depth
    ║               ╔════════╝║      ║  -
    ║               ║╔════════╝      ║
    ║               ║║ timber2       ║
    ╚═══════════════╝╚═══════════════╝
                    ^ top_lap_shoulder_position_from_top_lap_shoulder_timber_end

    Args:
        arrangement: Splice joint arrangement with timber1, timber2, timber1_end, timber2_end,
                     and optionally front_face_on_timber1 (the lap cut face on timber1).
                     If front_face_on_timber1 is None, defaults to FRONT face.
                     Timbers must be parallel and face-aligned.
        lap_length: Length of the lap region along the timber length.
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Distance from the
            timber1 end to the shoulder, measured inward along the timber.
        lap_depth: Depth of material to remove perpendicular to the face. If None,
            defaults to half the timber thickness in the face normal axis.

    Returns:
        Joint object containing the two CutTimbers with lap cuts.
    """
    top_lap_timber = arrangement.timber1
    top_lap_timber_end = arrangement.timber1_end
    bottom_lap_timber = arrangement.timber2
    bottom_lap_timber_end = arrangement.timber2_end
    top_lap_timber_face = arrangement.front_face_on_timber1 if arrangement.front_face_on_timber1 is not None else TimberLongFace.FRONT

    if lap_depth is None:
        if top_lap_timber_face == TimberLongFace.LEFT or top_lap_timber_face == TimberLongFace.RIGHT:
            lap_depth = top_lap_timber.size[1] / scalar(2)
        else:
            lap_depth = min(top_lap_timber.size[0], top_lap_timber.size[1]) / scalar(2)

    (top_lap_prism, top_end_cut), (bottom_lap_prism, bottom_end_cut) = chop_lap_on_timber_ends(
        top_lap_timber=top_lap_timber,
        top_lap_timber_end=top_lap_timber_end,
        bottom_lap_timber=bottom_lap_timber,
        bottom_lap_timber_end=bottom_lap_timber_end,
        top_lap_timber_face=top_lap_timber_face,
        lap_length=lap_length,
        lap_depth=lap_depth,
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end=top_lap_shoulder_position_from_top_lap_shoulder_timber_end,
    )

    top_end_cut_distance_from_bottom = (
        top_end_cut.offset
        if top_lap_timber_end == TimberEnd.TOP
        else -top_end_cut.offset
    )
    bottom_end_cut_distance_from_bottom = (
        bottom_end_cut.offset
        if bottom_lap_timber_end == TimberEnd.TOP
        else -bottom_end_cut.offset
    )

    lap_face_normal_global = top_lap_timber.get_face_direction_global(top_lap_timber_face.to.face())
    lap_thickness = top_lap_timber.get_size_in_face_normal_axis(top_lap_timber_face)

    cut_top = Cutting(
        timber=top_lap_timber,
        maybe_top_end_cut_distance_from_bottom=top_end_cut_distance_from_bottom if top_lap_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=top_end_cut_distance_from_bottom if top_lap_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=top_lap_prism,
        assembly_freedom=AssemblyFreedom.translation(lap_face_normal_global, freed_after=lap_thickness),
        label=CutCSGLabel("splice_lap_cut"),
    )

    cut_bottom = Cutting(
        timber=bottom_lap_timber,
        maybe_top_end_cut_distance_from_bottom=bottom_end_cut_distance_from_bottom if bottom_lap_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=bottom_end_cut_distance_from_bottom if bottom_lap_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=bottom_lap_prism,
        assembly_freedom=AssemblyFreedom.translation(-lap_face_normal_global, freed_after=lap_thickness),
        label=CutCSGLabel("splice_lap_cut"),
    )

    return Joint(
        cuttings={"top_lap_timber": cut_top, "bottom_lap_timber": cut_bottom},
        ticket=JointTicket(joint_type="plain_splice_lap"),
        jointAccessories={},
    )
