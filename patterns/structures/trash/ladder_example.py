"""
Ladder Example - Timber frame A-ladder

Structure:
- Two side frames (left and right), each forming an "A" in the YZ plane with apex in TOP (+Z) direction.
- Rungs connect between parallel stringer pairs: left/right front stringers and left/right back stringers.

All dimensions use exact SymPy Rational values through helper unit functions.
"""

from kumiki import *
from kumiki.patternbook import PatternBook, PatternMetadata
from kumiki.joints.basic_joints import cut_basic_miter_joint


# -----------------------------------------------------------------------------
# Dimensions
# -----------------------------------------------------------------------------

ladder_height = feet(6)
side_stringer_base_depth = feet(2)
side_frame_spacing = inches(18)

rail_size = create_v2(inches(2), inches(4))
step_size = create_v2(inches(1), inches(3))

num_steps = 5
first_step_height = inches(14)
step_spacing = inches(11)

step_tenon_size = create_v2(inches(1), inches(1))
step_tenon_length = inches(1)


# -----------------------------------------------------------------------------
# Geometry helpers
# -----------------------------------------------------------------------------

def _front_y_at_height(z_height: Numeric) -> Numeric:
    return -side_stringer_base_depth / 2 + (side_stringer_base_depth / 2) * (z_height / ladder_height)


def _back_y_at_height(z_height: Numeric) -> Numeric:
    return side_stringer_base_depth / 2 - (side_stringer_base_depth / 2) * (z_height / ladder_height)


def _create_side_rails(origin: V3, x_offset: Numeric, side_label: str) -> tuple[Timber, Timber]:
    apex_global = origin + create_v3(x_offset, Integer(0), ladder_height)
    front_bottom_global = origin + create_v3(x_offset, -side_stringer_base_depth / 2, Integer(0))
    back_bottom_global = origin + create_v3(x_offset, side_stringer_base_depth / 2, Integer(0))

    front_length_direction = normalize_vector(apex_global - front_bottom_global)
    back_length_direction = normalize_vector(apex_global - back_bottom_global)

    # Width points out of the side-frame plane (X), keeping members plane-aligned in YZ.
    width_direction = create_v3(Integer(1), Integer(0), Integer(0))

    front_rail = timber_from_directions(
        length=ladder_height,
        size=rail_size,
        bottom_position=front_bottom_global,
        length_direction=front_length_direction,
        width_direction=width_direction,
        ticket=f"Ladder {side_label} Front Stringer",
    )

    back_rail = timber_from_directions(
        length=ladder_height,
        size=rail_size,
        bottom_position=back_bottom_global,
        length_direction=back_length_direction,
        width_direction=width_direction,
        ticket=f"Ladder {side_label} Back Stringer",
    )

    return front_rail, back_rail


def _create_half_rung_between_parallel_stringers(
    step_index: int,
    origin: V3,
    y_position: Numeric,
    width_direction: Direction3D,
    from_left: bool,
    pair_label: str,
) -> Timber:
    z_height = first_step_height + step_spacing * step_index
    half_rung_length = side_frame_spacing / Rational(2) + step_tenon_length

    if from_left:
        rung_bottom = origin + create_v3(-side_frame_spacing / Rational(2), y_position, z_height)
        length_direction = create_v3(Integer(1), Integer(0), Integer(0))
        side_text = "Left"
    else:
        rung_bottom = origin + create_v3(side_frame_spacing / Rational(2), y_position, z_height)
        length_direction = create_v3(Integer(-1), Integer(0), Integer(0))
        side_text = "Right"

    return timber_from_directions(
        length=half_rung_length,
        size=step_size,
        bottom_position=rung_bottom,
        length_direction=length_direction,
        width_direction=width_direction,
        ticket=f"Ladder {pair_label} {side_text} Half-Rung {step_index + 1}",
    )


# -----------------------------------------------------------------------------
# Main builder
# -----------------------------------------------------------------------------

def create_ladder_frame(origin: Optional[V3] = None) -> Frame:
    if origin is None:
        origin = create_v3(Integer(0), Integer(0), Integer(0))

    left_x = -side_frame_spacing / Rational(2)
    right_x = side_frame_spacing / Rational(2)

    left_front_rail, left_back_rail = _create_side_rails(origin, left_x, "Left")
    right_front_rail, right_back_rail = _create_side_rails(origin, right_x, "Right")

    joints: list[Joint] = []

    # Apex A-joints: one miter at the top of each side frame (acute angle points to TOP/+Z).
    left_apex_joint = cut_basic_miter_joint(
        CornerJointTimberArrangement(
            timber1=left_front_rail,
            timber2=left_back_rail,
            timber1_end=TimberReferenceEnd.TOP,
            timber2_end=TimberReferenceEnd.TOP,
        )
    )

    right_apex_joint = cut_basic_miter_joint(
        CornerJointTimberArrangement(
            timber1=right_front_rail,
            timber2=right_back_rail,
            timber1_end=TimberReferenceEnd.TOP,
            timber2_end=TimberReferenceEnd.TOP,
        )
    )

    joints.append(left_apex_joint)
    joints.append(right_apex_joint)

    # Rungs between parallel front pair and parallel back pair.
    for i in range(num_steps):
        z_height = first_step_height + step_spacing * i
        front_y = _front_y_at_height(z_height)
        back_y = _back_y_at_height(z_height)

        front_left_half_rung = _create_half_rung_between_parallel_stringers(
            step_index=i,
            origin=origin,
            y_position=front_y,
            width_direction=left_front_rail.get_height_direction_global(),
            from_left=True,
            pair_label="Front",
        )

        front_right_half_rung = _create_half_rung_between_parallel_stringers(
            step_index=i,
            origin=origin,
            y_position=front_y,
            width_direction=left_front_rail.get_height_direction_global(),
            from_left=False,
            pair_label="Front",
        )

        back_left_half_rung = _create_half_rung_between_parallel_stringers(
            step_index=i,
            origin=origin,
            y_position=back_y,
            width_direction=left_back_rail.get_height_direction_global(),
            from_left=True,
            pair_label="Back",
        )

        back_right_half_rung = _create_half_rung_between_parallel_stringers(
            step_index=i,
            origin=origin,
            y_position=back_y,
            width_direction=left_back_rail.get_height_direction_global(),
            from_left=False,
            pair_label="Back",
        )

        front_left_rung_joint = cut_mortise_and_tenon_joint_on_PAT(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=left_front_rail,
                butt_timber=front_left_half_rung,
                butt_timber_end=TimberReferenceEnd.BOTTOM,
            ),
            tenon_size=step_tenon_size,
            tenon_length=step_tenon_length,
            mortise_depth=step_tenon_length,
            tenon_position=create_v2(Integer(0), Integer(0)),
            mortise_shoulder_inset=Integer(0),
            peg_parameters=None,
        )

        front_right_rung_joint = cut_mortise_and_tenon_joint_on_PAT(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=right_front_rail,
                butt_timber=front_right_half_rung,
                butt_timber_end=TimberReferenceEnd.BOTTOM,
            ),
            tenon_size=step_tenon_size,
            tenon_length=step_tenon_length,
            mortise_depth=step_tenon_length,
            tenon_position=create_v2(Integer(0), Integer(0)),
            mortise_shoulder_inset=Integer(0),
            peg_parameters=None,
        )

        back_left_rung_joint = cut_mortise_and_tenon_joint_on_PAT(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=left_back_rail,
                butt_timber=back_left_half_rung,
                butt_timber_end=TimberReferenceEnd.BOTTOM,
            ),
            tenon_size=step_tenon_size,
            tenon_length=step_tenon_length,
            mortise_depth=step_tenon_length,
            tenon_position=create_v2(Integer(0), Integer(0)),
            mortise_shoulder_inset=Integer(0),
            peg_parameters=None,
        )

        back_right_rung_joint = cut_mortise_and_tenon_joint_on_PAT(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=right_back_rail,
                butt_timber=back_right_half_rung,
                butt_timber_end=TimberReferenceEnd.BOTTOM,
            ),
            tenon_size=step_tenon_size,
            tenon_length=step_tenon_length,
            mortise_depth=step_tenon_length,
            tenon_position=create_v2(Integer(0), Integer(0)),
            mortise_shoulder_inset=Integer(0),
            peg_parameters=None,
        )

        joints.append(front_left_rung_joint)
        joints.append(front_right_rung_joint)
        joints.append(back_left_rung_joint)
        joints.append(back_right_rung_joint)

    return Frame.from_joints(joints=joints, name="A Ladder Frame")


# -----------------------------------------------------------------------------
# PatternBook wiring
# -----------------------------------------------------------------------------

def create_ladder_patternbook() -> PatternBook:
    patterns = [
        (
            PatternMetadata("a_ladder_timber_frame", ["structures", "ladder"], "frame"),
            lambda center: create_ladder_frame(center),
        ),
    ]
    return PatternBook(patterns=patterns)


patternbook = create_ladder_patternbook()


def create_all_ladder_examples() -> Frame:
    return create_ladder_frame()


example = create_all_ladder_examples
