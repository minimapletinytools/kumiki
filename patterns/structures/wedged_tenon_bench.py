# Last checked on kumiki 0.9.9
"""Purpose
-------
Build a five-foot bench with a pill-shaped seat and two arched slab feet.

Concepts demonstrated — overview
--------------------------------
Furniture, dressed dimensional lumber, and face-aligned through-tenons.

Concepts demonstrated — details
-------------------------------
Two tenons on each foot share a shoulder against the underside of the seat.
Each tenon takes two wedges driven from above, spreading it along the seat grain.
The tenon tips and wedge heads finish flush with the seating surface.
Dimensions are source constants.

Recipe notes
------------
The seat is a flat 2x10 (9-1/4" by 1-1/2"). Each upright 2x8 foot (7-1/4" by
1-1/2") stands 12" tall with its outer face 8" in from the seat end.
The seat ends are half-rounds of radius 4-5/8". A 2-1/2" radius arch cut from
the bottom of each foot leaves two 1-1/8" toes.
"""

__title__ = {"en": "Wedged twin-tenon bench", "ja": "楔締めの二枚枘のベンチ"}

from typing import Optional

from kumiki import *


top_size = create_v2(inches(9.25), inches(1.5))
foot_size = create_v2(inches(7.25), inches(1.5))
top_length = feet(5)
foot_height = feet(1)
foot_end_inset = inches(8)
arch_radius = inches(2.5)

tenon_width_across_foot = inches(1.5)
tenon_thickness = inches(1)
tenon_center_offset = inches(2)
wedges = WedgeParameters(
    paired_edge_inset=inches(1, 4),
    tenon_kerf_size=inches(1, 16),
    wedge_length=inches(1),
    wedge_angle=degrees(6),
    mortise_side_angle=degrees(2),
)


@frame
def bench(k: Optional[Kiwari] = None) -> Frame:
    """Build the rounded seat and its two wedged, twin-tenoned feet."""
    seat_axis_z = foot_height + top_size[1] / 2
    seat_half_length = top_length / 2
    top = create_axis_aligned_timber(
        bottom_position=create_v3(-seat_half_length, 0, seat_axis_z),
        length=top_length,
        size=top_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket=TimberTicket(path="Seat", tags=("top",)),
    )
    joints = [
        cut_basic_practice_rounded_end_decoration(top, rounded_face=TimberFace.FRONT, rounded_end=end)
        for end in (TimberFace.TOP, TimberFace.BOTTOM)
    ]

    foot_center_x = seat_half_length - foot_end_inset - foot_size[1] / 2
    for name, x in (("Foot West", -foot_center_x), ("Foot East", foot_center_x)):
        foot = create_axis_aligned_timber(
            bottom_position=create_v3(x, 0, 0),
            length=foot_height,
            size=foot_size,
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.FRONT,
            ticket=TimberTicket(path=name, tags=("foot",)),
        )
        arrangement = ButtJointTimberArrangement(foot, top, TimberEnd.TOP)
        tenons = [
            cut_mortise_and_tenon_joint_on_face_aligned_timbers(
                arrangement,
                tenon_position=create_v2(offset, 0),
                tenon_width_relative_to_joint=tenon_thickness,
                tenon_height_relative_to_joint=tenon_width_across_foot,
                tenon_length=top_size[1],
                mortise_depth=None,
                wedge_parameters=wedges,
                relief=None,
                inset_shoulder_relief_style=InsetShoulderReliefStyle.NoRelief,
            )
            for offset in (-tenon_center_offset, tenon_center_offset)
        ]
        joints.append(merge_mortise_and_tenon_joints(tenons, relief=None))

        # The foot's local Y axis runs through its thickness, with the origin on the floor.
        arch_half_length = foot_size[1] / 2 + inches(1)
        arch = Cylinder(
            axis_direction=create_v3(0, 1, 0),
            radius=arch_radius,
            start_distance=-arch_half_length,
            end_distance=arch_half_length,
        )
        joints.append(Joint(
            cuttings={name: Cutting(timber=foot, negative_csg=arch, label=CutCSGLabel("foot_arch"))},
            ticket=JointTicket(joint_type="foot_arch"),
        ))

    return Frame.from_joints(joints, name="Bench", kiwari=k)
