"""Through finger joints at a square corner."""

from kumiki.construction import CornerJointTimberArrangement, arrangement_check
from kumiki.measuring import get_center_point_on_face_global
from kumiki.rule import safe_dot_product
from kumiki.timber import AssemblyFreedom, Joint, JointTicket
from ..shavings.fingers import finger_cutting, finger_slots, matched_span


def cut_finger_corner_joint(arrangement: CornerJointTimberArrangement, finger_count: int = 5) -> Joint:
    """Cut alternating square through fingers in two orthogonal rectangular ends.

    finger_count counts both members' fingers across their shared width. Timber1 keeps the
    first finger at front_face_on_timber1. If omitted, that face follows the cross product
    of the two outward end directions. Each end finishes flush with the other's outside face.
    """
    arrangement_check(arrangement.check_face_aligned_and_orthogonal(), arrangement)
    arrangement_check(arrangement.check_plane_aligned(), arrangement)
    first, second = arrangement.timber1, arrangement.timber2
    along = first.get_face_direction_global(arrangement.timber1_end)
    across = second.get_face_direction_global(arrangement.timber2_end)
    front = arrangement.front_face_on_timber1 or first.get_closest_oriented_long_face_from_global_direction(
        arrangement.compute_normalized_timber_cross_product())
    width = matched_span(arrangement, front)
    first_outside = first.get_closest_oriented_long_face_from_global_direction(across)
    second_entry = second.get_closest_oriented_long_face_from_global_direction(-along)
    thickness = first.get_size_in_face_normal_axis(first_outside)
    depth = second.get_size_in_face_normal_axis(second_entry)
    entry_global = get_center_point_on_face_global(second_entry, second)
    origin = first.get_bottom_position_global()
    shoulder_global = origin + along * safe_dot_product(entry_global - origin, along)
    first_slots, second_slots = finger_slots(shoulder_global, first.get_face_direction_global(front), along,
                                            width, depth, thickness, finger_count, 0)

    def freedom(sign: int) -> AssemblyFreedom:
        return AssemblyFreedom.combine(AssemblyFreedom.translation(-along * sign, depth),
                                       AssemblyFreedom.translation(across * sign, thickness))

    return Joint(cuttings={
        "timber1": finger_cutting(first, arrangement.timber1_end, shoulder_global + along * depth,
                                  depth, first_slots, freedom(1)),
        "timber2": finger_cutting(second, arrangement.timber2_end, get_center_point_on_face_global(first_outside, first),
                                  thickness, second_slots, freedom(-1)),
    }, ticket=JointTicket(joint_type="finger_corner"))


cut_box_corner_joint = cut_finger_corner_joint
