"""Half-blind tenoned, dadoed, rabbeted scarf joint (Kanawa Tsugi style).

Two 4"x6" timbers meeting end-to-end, joined with
`cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers`. Unlike
a plain splice joint, the two raw timbers must physically overlap near the
joint center -- the profile only carves shape within material that's already
there, it doesn't extend either timber -- so both timbers are laid out
generously overlapping around the joint center.

This lives in patterns/structures (rather than patterns/, where the other
splice joint examples live) so it can be scrubbed through its disassembly
sequence in the Kigumi viewer -- assembly previews aren't available for plain
patterns.
"""

from kumiki import *


# --- Dimensions --------------------------------------------------------

timber_size = create_v2(inches(4), inches(6))
timber_length = inches(48)

overlap = inches(8)  # how far each timber's raw body extends past the joint center

stepped_shoulder_depth = inches(1)
scarf_length = inches(10)
dado_depth = inches(1)
dado_height = inches(1.5)
stub_tenon_width = inches(1.5)


def example() -> Frame:
    # timber1's TOP (joint end) sits `overlap` past the joint center;
    # timber2's BOTTOM (joint end) sits `overlap` before it -- so both
    # physically reach into the other's territory near the joint.
    timber1 = create_timber(
        length=timber_length,
        size=timber_size,
        bottom_position=create_v3(-timber_length + overlap, scalar(0), scalar(0)),
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="scarf_timber1",
    )
    timber2 = create_timber(
        length=timber_length,
        size=timber_size,
        bottom_position=create_v3(-overlap, scalar(0), scalar(0)),
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="scarf_timber2",
    )

    arrangement = SpliceJointTimberArrangement(
        timber1=timber1,
        timber2=timber2,
        timber1_end=TimberEnd.TOP,
        timber2_end=TimberEnd.BOTTOM,
        front_face_on_timber1=TimberLongFace.RIGHT,
    )

    joint = cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers(
        arrangement=arrangement,
        stepped_shoulder_depth=stepped_shoulder_depth,
        scarf_length=scarf_length,
        dado_depth=dado_depth,
        dado_height=dado_height,
        stub_tenon_width=stub_tenon_width,
        joint_center_relative_to_timber1_end=overlap,
    )

    return Frame.from_joints(
        [joint],
        name="Half-Blind Tenoned Dadoed Rabbeted Scarf Joint",
    )
