"""
Kumiki - Drop-in housed butt joint construction functions
"""

from __future__ import annotations

from typing import Optional, Union

from kumiki.timber import (
    AssemblyFreedom,
    Cutting,
    Joint,
    JointTicket,
    TimberEnd,
    require_check,
)
from kumiki.construction import ButtJointTimberArrangement
from kumiki.rule import (
    Numeric,
    safe_dot_product,
    are_vectors_parallel,
    scalar,
    Matrix,
)
from kumiki.measuring import (
    mark_distance_from_end_along_centerline,
)
from kumiki.cutcsg import (
    CutCSGLabel,
    Difference,
    SolidUnion,
    adopt_csg,
)
from ..shavings.shavings import (
    chop_profile_on_timber_face,
    chop_timber_end_with_prism,
    scribe_face_plane_onto_centerline,
    scribe_centerline_onto_centerline,
)
from ..shavings.relief import (
    chop_shoulder_notch_on_timber_face,
    warn_if_arrangement_timbers_imperfect,
)


def cut_dropin_housed_butt_joint_on_face_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    receiving_timber_shoulder_inset: Numeric,
    housing_length: Numeric,
    housing_width: Numeric,
    housing_lateral_offset: Numeric = scalar(0),
    housing_depth: Optional[Numeric] = None,
) -> Joint:
    """
    Creates a drop-in housed butt joint (housing slot pocket) between two orthogonal timbers.

    Only the housing timber is cut to receive the square end of the housed timber.
    The housed timber drops into the pocket along the housing face normal.

    Args:
        arrangement: Butt joint arrangement where butt_timber is the housed timber,
            receiving_timber receives the housing pocket socket, butt_timber_end is the cut end,
            and front_face_on_butt_timber is the face where the pocket profile is open (normally the top face).
        receiving_timber_shoulder_inset: Distance to inset the shoulder notch on the receiving timber
        housing_length: Length of the housing slot pocket (the joist extension depth into the mudsill)
        housing_width: Width of the housing pocket
        housing_lateral_offset: Lateral offset of the housing pocket from center (default 0)
        housing_depth: Depth of the pocket. If None, defaults to half the timber dimension

    Returns:
        Joint object containing the two CutTimbers with the housing cuts applied
    """
    require_check(arrangement.check_face_aligned_and_orthogonal())
    warn_if_arrangement_timbers_imperfect(arrangement)
    assert arrangement.front_face_on_butt_timber is not None, (
        "arrangement.front_face_on_butt_timber must be set to determine the housing face"
    )
    housed_timber = arrangement.butt_timber
    receiving_timber = arrangement.receiving_timber
    housed_timber_end = arrangement.butt_timber_end
    housed_timber_face = arrangement.front_face_on_butt_timber

    # Validate positive dimensions
    if housing_length <= 0:
        raise ValueError(f"housing_length must be positive, got {housing_length}")
    if housing_width <= 0:
        raise ValueError(f"housing_width must be positive, got {housing_width}")
    if receiving_timber_shoulder_inset < 0:
        raise ValueError(f"receiving_timber_shoulder_inset must be non-negative, got {receiving_timber_shoulder_inset}")
    if housing_depth is not None and housing_depth <= 0:
        raise ValueError(f"housing_depth must be positive if provided, got {housing_depth}")

    if are_vectors_parallel(housed_timber.get_face_direction_global(housed_timber_face), receiving_timber.get_length_direction_global()):
        raise ValueError(
            "Housed timber face must be perpendicular to receiving timber length direction for drop-in housed butt joint. "
            "Try rotating the housing face."
        )

    if housing_depth is None:
        housing_depth = housed_timber.get_size_in_face_normal_axis(housed_timber_face.to.face()) / scalar(2)

    housing_profile = [
        Matrix([-housing_width / scalar(2) + housing_lateral_offset, 0]),
        Matrix([housing_width / scalar(2) + housing_lateral_offset, 0]),
        Matrix([housing_width / scalar(2) + housing_lateral_offset, housing_length]),
        Matrix([-housing_width / scalar(2) + housing_lateral_offset, housing_length]),
    ]

    receiving_timber_shoulder_face = receiving_timber.get_closest_oriented_face_from_global_direction(-housed_timber.get_face_direction_global(housed_timber_end.to.face()))
    face_plane = scribe_face_plane_onto_centerline(
        face=receiving_timber_shoulder_face,
        face_timber=receiving_timber
    )
    marking = mark_distance_from_end_along_centerline(face_plane, housed_timber, housed_timber_end)
    shoulder_distance_from_end = marking.distance - receiving_timber_shoulder_inset

    housing_profile_csg = chop_profile_on_timber_face(
        timber=housed_timber,
        end=housed_timber_end,
        face=housed_timber_face.to.face(),
        profile=housing_profile,
        depth=housing_depth,
        profile_y_offset_from_end=shoulder_distance_from_end,
        label=CutCSGLabel("housing"),
    )

    housing_housing_prism = chop_timber_end_with_prism(
        timber=housed_timber,
        end=housed_timber_end,
        distance_from_end_to_cut=shoulder_distance_from_end,
        label=CutCSGLabel("housing_shoulder"),
    )

    housed_centerline = scribe_centerline_onto_centerline(housed_timber)
    marking_receiving = mark_distance_from_end_along_centerline(housed_centerline, receiving_timber)
    receiving_timber_notch_center = marking_receiving.distance

    if receiving_timber_shoulder_inset > 0:
        notch_width = housed_timber.get_size_in_face_normal_axis(housed_timber_face.rotate_right().to.face())
        notch_depth = receiving_timber_shoulder_inset
        receiving_timber_shoulder_notch = chop_shoulder_notch_on_timber_face(
            timber=receiving_timber,
            notch_face=receiving_timber_shoulder_face,
            distance_along_timber=receiving_timber_notch_center,
            notch_width=notch_width,
            notch_depth=notch_depth
        )

    housing_socket_csg = adopt_csg(housed_timber.transform, receiving_timber.transform, housing_profile_csg)

    if housed_timber_end == TimberEnd.TOP:
        housing_end_local_z = housed_timber.length - shoulder_distance_from_end + housing_length
    else:
        housing_end_local_z = shoulder_distance_from_end - housing_length

    housed_lift_direction_global = housed_timber.get_face_direction_global(housed_timber_face.to.face())
    housed_timber_cut_obj = Cutting(
        timber=housed_timber,
        maybe_top_end_cut_distance_from_bottom=housing_end_local_z if housed_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=housing_end_local_z if housed_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=Difference(
            housing_housing_prism, [housing_profile_csg],
            label=CutCSGLabel("housing_waste"),
        ),
        label=CutCSGLabel("housed_cut"),
        assembly_freedom=AssemblyFreedom.translation(housed_lift_direction_global, freed_after=housing_depth),
    )

    if receiving_timber_shoulder_inset > 0:
        receiving_timber_negative_csg = SolidUnion([receiving_timber_shoulder_notch, housing_socket_csg])
    else:
        receiving_timber_negative_csg = housing_socket_csg

    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        negative_csg=receiving_timber_negative_csg,
        label=CutCSGLabel("housing_socket_cut"),
        assembly_freedom=AssemblyFreedom.translation(-housed_lift_direction_global, freed_after=housing_depth),
    )

    return Joint(
        cuttings={
            housed_timber.ticket.path: housed_timber_cut_obj,
            receiving_timber.ticket.path: receiving_timber_cut_obj
        },
        ticket=JointTicket(joint_type="housed_butt"),
        jointAccessories={},
    )
