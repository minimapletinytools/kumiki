"""
Kumiki - Plain butt joint construction functions
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional, Union

from kumiki.timber import (
    AssemblyFreedom,
    Cutting,
    Joint,
    JointTicket,
    TimberEnd,
    TimberFace,
    SomeTimberFace,
    PerfectTimberWithin,
)
from kumiki.timber_shavings import are_timbers_face_aligned
from kumiki.construction import ButtJointTimberArrangement
from kumiki.rule import (
    Comparison,
    Numeric,
    safe_compare,
    safe_dot_product,
    safe_transform_vector,
    are_vectors_parallel,
    scalar,
)
from kumiki.measuring import (
    locate_top_center_position,
    locate_bottom_center_position,
    get_center_point_on_face_global,
)
from kumiki.cutcsg import CutCSGLabel, HalfSpace
from ..shavings.relief import (
    warn_if_arrangement_timbers_imperfect,
    ButtJointScribeReliefConfig,
    apply_scribe_relief_if_configured,
)


def _get_face_center_position(timber: PerfectTimberWithin, face: SomeTimberFace):
    """Calculate the center position of a timber face."""
    return get_center_point_on_face_global(face, timber)


def cut_plain_butt_joint(
    arrangement: ButtJointTimberArrangement,
    relief: Union[None, ButtJointScribeReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
) -> Joint:
    """
    Creates a butt joint where the butt timber is cut flush with the face of the receiving timber.

    The butt timber's end is trimmed along the plane of the best-matching long face of the
    receiving timber. The receiving timber otherwise isn't cut, aside from any scribe relief.

    Works for any non-parallel angle between the timbers, including oblique 3D angles.
    The cut plane follows the actual receiving face geometry rather than being perpendicular
    to the butt timber's axis, so the mating face is always flush.

    Args:
        arrangement: Butt joint arrangement with butt_timber, receiving_timber, butt_timber_end.
        relief: Scribe-relief configuration for imperfect timbers. Defaults to scribing the
            butt timber onto the receiving timber. Pass None to skip scribe relief entirely.

    Returns:
        Joint object containing the cut butt timber and uncut receiving timber.

    Raises:
        AssertionError: If the timbers are parallel.
    """
    receiving_timber = arrangement.receiving_timber
    butt_timber = arrangement.butt_timber
    butt_end = arrangement.butt_timber_end

    warn_if_arrangement_timbers_imperfect(arrangement)

    assert not are_vectors_parallel(
        receiving_timber.get_length_direction_global(),
        butt_timber.get_length_direction_global(),
    ), "Timbers cannot be parallel for a butt joint"

    # Get the direction of the butt end (pointing outward from the timber body)
    if butt_end == TimberEnd.TOP:
        butt_direction = butt_timber.get_length_direction_global()
    else:
        butt_direction = -butt_timber.get_length_direction_global()

    # Find the long face of the receiving timber that faces the incoming butt timber.
    # We pass -butt_direction because the face we want has its outward normal pointing
    # toward the butt timber (i.e., opposite to the butt travel direction).
    receiving_face = receiving_timber.get_closest_oriented_long_face_from_global_direction(-butt_direction)
    receiving_face_dir_global = receiving_timber.get_face_direction_global(receiving_face)

    # A point on the receiving face plane (use face center)
    face_center = _get_face_center_position(receiving_timber, receiving_face)

    # Orient the cut-plane normal to point in the direction material is removed
    # (i.e., away from the butt timber body, toward the receiving timber).
    # The receiving face normal points toward the butt, so flip it.
    dot_check = safe_dot_product(receiving_face_dir_global, butt_direction)
    if safe_compare(dot_check, 0, Comparison.GT):
        cut_normal_global = receiving_face_dir_global
    else:
        cut_normal_global = -receiving_face_dir_global

    # Convert cut plane to butt timber local coordinates
    local_normal = safe_transform_vector(butt_timber.orientation.matrix.T, cut_normal_global)
    local_offset = (
        safe_dot_product(cut_normal_global, face_center)
        - safe_dot_product(cut_normal_global, butt_timber.get_bottom_position_global())
    )
    end_cut_distance_from_bottom = safe_dot_product(
        face_center - butt_timber.get_bottom_position_global(),
        butt_timber.get_length_direction_global(),
    )

    end_cut = HalfSpace(normal=local_normal, offset=local_offset)

    cut_no_relief = Cutting(
        timber=butt_timber,
        maybe_top_end_cut_distance_from_bottom=end_cut_distance_from_bottom if butt_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=end_cut_distance_from_bottom if butt_end == TimberEnd.BOTTOM else None,
        negative_csg=end_cut,
        label=CutCSGLabel("butt_cross_cut"),
    )
    receiving_cut_no_relief = Cutting(timber=receiving_timber)

    cut, receiving_cut = apply_scribe_relief_if_configured(
        relief=relief,
        butt_cut=cut_no_relief,
        receiving_cut=receiving_cut_no_relief,
    )

    # Assembly: a plain butt has no mechanical engagement, so it is free after
    # 0 travel. Disassembly code adds its own visual-separation padding on top
    # of freed_after, so no nominal travel is needed here.
    joint = Joint(
        cuttings={
            "receiving_timber": replace(
                receiving_cut,
                assembly_freedom=AssemblyFreedom.translation(butt_direction, freed_after=scalar(0)),
            ),
            "butt_timber": replace(
                cut,
                assembly_freedom=AssemblyFreedom.translation(-butt_direction, freed_after=scalar(0)),
            ),
        },
        ticket=JointTicket(joint_type="plain_butt"),
        jointAccessories={},
    )

    return joint


def cut_plain_butt_joint_on_face_aligned_timbers(arrangement: ButtJointTimberArrangement) -> Joint:
    """
    Creates a butt joint where the butt timber is cut flush with the face of the receiving timber.

    Requires the timbers to be face-aligned. For an unrestricted version that works at any
    angle, use `cut_plain_butt_joint` directly.

    Args:
        arrangement: Butt joint arrangement with butt_timber, receiving_timber, butt_timber_end.
                     Timbers must be face-aligned and non-parallel.

    Returns:
        Joint object containing the cut butt timber and uncut receiving timber.

    Raises:
        AssertionError: If the timbers are not face-aligned or are parallel.
    """
    assert are_timbers_face_aligned(arrangement.receiving_timber, arrangement.butt_timber), \
        "Timbers must be face-aligned (orientations related by 90-degree rotations) for this joint type"
    return cut_plain_butt_joint(arrangement)
