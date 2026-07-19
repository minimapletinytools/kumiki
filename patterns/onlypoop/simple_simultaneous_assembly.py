"""Simple Assembly Test Structure

A regular n-gon of timbers where each timber is joined to the next timber in sequence
with a basic mortise and tenon joint. This creates a reciprocal frame cycle such that
all n timbers need to be disassembled simultaneously.
"""

from sympy import pi, cos, sin
from kumiki import *
from kumiki.ticket import TimberTicket

def build_frame(
    n: int = Param(4, description="Number of timbers (at least 3)", kind="number", minimum=3)
) -> Frame:
    n_int = int(scalar(n))
    assert n_int >= 3, "Number of timbers must be at least 3"

    timber_size = create_v2(inches(2), inches(2))

    radius = inches(13)

    # Angle of each sector
    theta_rad = pi * scalar(2) / n_int
    
    # Distance between successive points A_i and A_{i+1}
    s = scalar(2) * radius * sin(theta_rad / scalar(2))

    # Total length of each timber: we extend it past A_{i+1} by an inset.
    # This ensures there is receiving wood to hold the mortise for timber_{i+1}.
    inset = timber_size[0] * scalar(2)
    length = s + inset

    # Create the timbers
    timbers = []
    for i in range(n_int):
        # Position of A_i (bottom position of timber i)
        angle_i = i * theta_rad
        pos_x = radius * cos(angle_i)
        pos_y = radius * sin(angle_i)
        bottom_position = create_v3(pos_x, pos_y, scalar(0))

        # Direction of timber i (from A_i to A_{i+1})
        # The angle of the vector A_{i+1} - A_i is i * theta_rad + theta_rad / 2 + pi / 2.
        dir_angle = i * theta_rad + theta_rad / scalar(2) + pi / scalar(2)
        length_direction = create_v3(cos(dir_angle), sin(dir_angle), scalar(0))

        # The width direction (local X face) points up (global +Z).
        width_direction = create_v3(scalar(0), scalar(0), scalar(1))

        # Create timber
        timber = create_timber(
            bottom_position=bottom_position,
            length=length,
            size=timber_size,
            length_direction=length_direction,
            width_direction=width_direction,
            ticket=TimberTicket(path=f"Timber {i+1}"),
        )
        timbers.append(timber)

    # Cut the joints
    joints = []
    # Joint configuration:
    # Tenon is at the bottom end of timber_{i+1} (butt timber)
    # Mortise is in timber_i (receiving timber) at distance s along its centerline.
    # Tenon dimensions: standard 1/3 of face width.
    tenon_w = timber_size[0] / scalar(3)
    tenon_h = timber_size[1] * scalar(2, 3)
    tenon_size = create_v2(tenon_w, tenon_h)
    tenon_len = timber_size[1] * scalar(3, 4)
    mortise_d = tenon_len + mm(5)

    for i in range(n_int):
        recv_timber = timbers[i]
        butt_timber = timbers[(i + 1) % n_int]

        # The arrangement
        arrangement = ButtJointTimberArrangement(
            receiving_timber=recv_timber,
            butt_timber=butt_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        )

        # Cut the mortise and tenon joint
        # Note: since the intersection is at distance s along recv_timber,
        # the mortise will be cut automatically at the correct position.
        joint = cut_mortise_and_tenon_joint(
            arrangement=arrangement,
            tenon_size=tenon_size,
            tenon_length=tenon_len,
            mortise_depth=mortise_d,
            mortise_shoulder_distance_from_centerline_or_centerplane = timber_size[0] / scalar(2)
        )
        joints.append(joint)

    return Frame.from_joints(joints, name=f"Simple Assembly Test ({n_int}-gon)")

example = build_frame
