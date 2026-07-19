"""N-Legged Stool Structure

An n-legged stool consisting of a round flat seat, n legs arranged with circular
symmetry splaying out by 10 degrees, and a ring of stretchers.
All members (seat, legs, stretchers) are round timbers.
"""

from sympy import pi, cos, sin
from kumiki import *
from kumiki.ticket import TimberTicket

def build_frame(
    n: int = Param(4, description="Number of legs (at least 3)", kind="number", minimum=3),
    stool_height: Numeric = Param(mm(450), description="Total height of the stool", kind="number"),
    seat_diameter: Numeric = Param(mm(300), description="Diameter of the seat", kind="number"),
    seat_thickness: Numeric = Param(mm(40), description="Thickness of the seat", kind="number"),
    leg_diameter: Numeric = Param(mm(35), description="Diameter of the legs", kind="number"),
    stretcher_diameter: Numeric = Param(mm(25), description="Diameter of the stretchers", kind="number"),
    stretcher_height: Numeric = Param(mm(150), description="Height of stretchers from ground", kind="number"),
    leg_top_radius: Numeric = Param(mm(100), description="Radial distance of leg attachment from center", kind="number"),
) -> Frame:
    n_int = int(scalar(n))
    assert n_int >= 3, "Number of legs must be at least 3"

    # 1. Stool Seat
    # Seat is a horizontal regular rectangular timber running along the X axis.
    # Thickness is vertical (local X) and depth is horizontal (local Y).
    seat = create_timber(
        bottom_position=create_v3(-seat_diameter / scalar(2), scalar(0), stool_height - seat_thickness / scalar(2)),
        length=seat_diameter,
        size=create_v2(seat_thickness, seat_diameter),
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket=TimberTicket(path="Seat"),
    )

    # 2. Stool Legs
    # Splay angle is 10 degrees away from the center of the seat board.
    splay_angle_rad = pi * scalar(10, 180)  # 10 degrees in radians
    cos_splay = cos(splay_angle_rad)
    sin_splay = sin(splay_angle_rad)

    # Leg length is calculated so the leg centerline hits the ground (Z=0) exactly.
    # The vertical distance from seat underside to ground is stool_height - seat_thickness.
    vertical_leg_height = stool_height - seat_thickness
    leg_length = vertical_leg_height / cos_splay

    legs = []
    theta_step = pi * scalar(2) / n_int

    for i in range(n_int):
        theta_i = i * theta_step
        cos_t = cos(theta_i)
        sin_t = sin(theta_i)

        # The top point of leg centerline (under the seat)
        leg_top_pos = create_v3(leg_top_radius * cos_t, leg_top_radius * sin_t, vertical_leg_height)

        # The length direction (local +Z axis) points generally upward towards the seat,
        # but tilted inward so that going from bottom to top goes towards the center.
        # So it has negative radial component, positive vertical component.
        length_direction = create_v3(-sin_splay * cos_t, -sin_splay * sin_t, cos_splay)

        # The width direction (local +X axis, RIGHT face) points towards the center.
        # This is orthogonal to length_direction.
        width_direction = create_v3(-cos_splay * cos_t, -cos_splay * sin_t, -sin_splay)

        # Bottom position of the leg
        leg_bottom_pos = leg_top_pos - length_direction * leg_length

        leg_perfect = create_timber(
            bottom_position=leg_bottom_pos,
            length=leg_length,
            size=create_v2(leg_diameter, leg_diameter),
            length_direction=length_direction,
            width_direction=width_direction,
            ticket=TimberTicket(path=f"Leg {i+1}"),
        )
        leg = RoundTimber.from_perfect_timber_within(leg_perfect, leg_diameter)
        legs.append(leg)

    # 3. Stretchers (connecting legs in a ring)
    # Stretchers are placed at stretcher_height.
    # The parameter along the leg length is determined by stretcher_height / cos_splay.
    t_stretcher = stretcher_height / cos_splay
    stretcher_centers = []
    for i in range(n_int):
        # Position along the leg's centerline
        theta_i = i * theta_step
        cos_t = cos(theta_i)
        sin_t = sin(theta_i)
        leg_top_pos = create_v3(leg_top_radius * cos_t, leg_top_radius * sin_t, vertical_leg_height)
        length_direction = create_v3(-sin_splay * cos_t, -sin_splay * sin_t, cos_splay)
        leg_bottom_pos = leg_top_pos - length_direction * leg_length

        pt = leg_bottom_pos + length_direction * t_stretcher
        stretcher_centers.append(pt)

    stretchers = []
    for i in range(n_int):
        pt_start = stretcher_centers[i]
        pt_end = stretcher_centers[(i + 1) % n_int]

        # Stretcher spans from leg i to leg i+1
        diff = pt_end - pt_start
        stretcher_len = diff.norm()
        stretcher_dir = diff / stretcher_len

        # Since it is horizontal, width direction is up
        stretcher_perfect = create_timber(
            bottom_position=pt_start,
            length=stretcher_len,
            size=create_v2(stretcher_diameter, stretcher_diameter),
            length_direction=stretcher_dir,
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket=TimberTicket(path=f"Stretcher {i+1}"),
        )
        stretcher = RoundTimber.from_perfect_timber_within(stretcher_perfect, stretcher_diameter)
        stretchers.append(stretcher)

    # 4. Jointing everything together
    joints = []

    # Legs to Seat: through-mortise-and-tenon
    # Tenon diameter = leg_diameter * 0.7
    leg_tenon_diameter = leg_diameter * scalar(7, 10)
    # tenon length must go through seat thickness (plus extra)
    leg_tenon_length = seat_thickness * scalar(1,2)

    for i in range(n_int):
        leg = legs[i]
        arrangement = ButtJointTimberArrangement(
            receiving_timber=seat,
            butt_timber=leg,
            butt_timber_end=TimberEnd.TOP,
        )
        joint = cut_round_mortise_and_tenon_joint(
            arrangement=arrangement,
            diameter=leg_tenon_diameter,
            tenon_length=leg_tenon_length,
            mortise_depth=seat_thickness * scalar(1/2),
            mortise_shoulder_distance_from_centerline = seat_thickness * scalar(3,8),
        )
        joints.append(joint)

    # Stretchers to Legs: basic mortise-and-tenon
    stretcher_tenon_diameter = stretcher_diameter * scalar(6, 10)
    stretcher_tenon_length = leg_diameter * scalar(1, 4)
    stretcher_mortise_depth = stretcher_tenon_length

    for i in range(n_int):
        stretcher = stretchers[i]
        leg_start = legs[i]
        leg_end = legs[(i + 1) % n_int]

        # Joint at start of stretcher i (into leg i)
        arr_start = ButtJointTimberArrangement(
            receiving_timber=leg_start,
            butt_timber=stretcher,
            butt_timber_end=TimberEnd.BOTTOM,
        )
        joint_start = cut_round_mortise_and_tenon_joint(
            arrangement=arr_start,
            diameter=stretcher_tenon_diameter,
            tenon_length=stretcher_tenon_length,
            mortise_depth=stretcher_mortise_depth,
            mortise_shoulder_distance_from_centerline = leg_diameter * scalar(3,8),
        )
        joints.append(joint_start)

        # Joint at end of stretcher i (into leg i+1)
        arr_end = ButtJointTimberArrangement(
            receiving_timber=leg_end,
            butt_timber=stretcher,
            butt_timber_end=TimberEnd.TOP,
        )
        joint_end = cut_round_mortise_and_tenon_joint(
            arrangement=arr_end,
            diameter=stretcher_tenon_diameter,
            tenon_length=stretcher_tenon_length,
            mortise_depth=stretcher_mortise_depth,
            mortise_shoulder_distance_from_centerline = leg_diameter * scalar(3,8),
        )
        joints.append(joint_end)

    return Frame.from_joints(joints, name=f"{n_int}-Legged Stool")

example = build_frame
