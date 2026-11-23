"""Straight and tapered end-to-end finger joints."""

from typing import Optional

from kumiki.construction import SpliceJointTimberArrangement, arrangement_check, arrangement_error
from kumiki.measuring import get_center_point_on_face_global
from kumiki.rule import Numeric, V3, atan, safe_dot_product, safe_equality_test, scalar
from kumiki.timber import AssemblyFreedom, Joint, JointTicket, TimberLongFace
from ..shavings.fingers import finger_cutting, finger_slots, matched_span


def cut_uniform_finger_splice_joint(
    arrangement: SpliceJointTimberArrangement, finger_length: Numeric, finger_count: int | None = None, *,
    finger_width: Numeric | None = None, taper_angle: Numeric = atan(scalar(1, 8)), splice_point: Optional[V3] = None,
) -> Joint:
    """Splice opposed ends of matching rectangular stock with fingers of axial length finger_length.

    Set finger_count to divide the section evenly (default five), or finger_width to mark
    fixed widths at mid-overlap starting at front_face_on_timber1 (default FRONT).
    Timber1 keeps the first finger. Any remainder at the far face must accommodate
    the taper. taper_angle is the angle of each flank
    to the grain, in radians. Zero gives straight fingers. The center of the overlap is the
    projected world-space splice_point, or the midpoint of the selected ends when omitted.

    [![Tapered finger splice](../../../assets/joint-drawings/finger-splice.svg)](../../../assets/joint-drawings/finger-splice.svg)
    """
    arrangement_check(arrangement.check_face_aligned_and_parallel_axis(), arrangement)
    first, second = arrangement.timber1, arrangement.timber2
    along = first.get_face_direction_global(arrangement.timber1_end)
    if not safe_equality_test(safe_dot_product(along, second.get_face_direction_global(arrangement.timber2_end)), -1):
        raise arrangement_error("The selected splice ends must point in opposite directions", arrangement)
    front = arrangement.front_face_on_timber1 or TimberLongFace.FRONT
    width = matched_span(arrangement, front)
    thickness = matched_span(arrangement, front.rotate_right())
    end_global = get_center_point_on_face_global(arrangement.timber1_end, first)
    if splice_point is None:
        center_global = (end_global + get_center_point_on_face_global(arrangement.timber2_end, second)) / 2
    else:
        center_global = end_global + along * safe_dot_product(splice_point - end_global, along)
    shoulder_global = center_global - along * (finger_length / 2)
    first_slots, second_slots = finger_slots(shoulder_global, first.get_face_direction_global(front), along,
                                            width, finger_length, thickness, finger_count, finger_width, taper_angle)
    through = first.get_face_direction_global(front.rotate_right())
    sideways = AssemblyFreedom.bidirectional_translation(through, thickness)
    first_freedom = AssemblyFreedom.combine(AssemblyFreedom.translation(-along, finger_length), sideways)
    second_freedom = AssemblyFreedom.combine(AssemblyFreedom.translation(along, finger_length), sideways)
    return Joint(cuttings={
        "timber1": finger_cutting(first, arrangement.timber1_end, center_global + along * (finger_length / 2),
                                  finger_length, first_slots, first_freedom),
        "timber2": finger_cutting(second, arrangement.timber2_end, shoulder_global,
                                  finger_length, second_slots, second_freedom),
    }, ticket=JointTicket(joint_type="finger_splice"))
