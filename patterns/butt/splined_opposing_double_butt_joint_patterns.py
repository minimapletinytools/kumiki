# Last checked on kumiki 0.9.0
"""
Splined Opposing Double Butt Joint Patterns
"""

from typing import Optional
from kumiki import Frame, Joint, Kiwari, kiwari, create_v3, pattern
from kumiki.rule import V3, inches, mm, scalar
from kumiki.timber import Frame, PegShape, TimberEnd
from kumiki.joints.workshop.butt import cut_splined_opposing_double_butt_joint_on_face_aligned_timbers
from kumiki.joints.workshop.shavings.build_a_butt import SimplePegParameters
from kumiki.example_shavings import create_canonical_example_opposing_double_butt_joint_timbers


def make_splined_opposing_double_butt_joint_example(position: V3, k: Kiwari) -> Frame:
    """
    Create a splined opposing double butt joint example.

    Two butt timbers approach a receiving timber (post) from opposite directions.
    Returns a Frame containing all three cut timbers and the spline accessory.

    Args:
        position: Center position of the joint (V3)
    """
    arrangement = create_canonical_example_opposing_double_butt_joint_timbers(position=position)
    joint = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        slot_facing_end_on_receiving_timber=TimberEnd.TOP,
        slot_thickness=k.length("slot_thickness"),
        slot_depth=k.length("slot_depth"),
        spline_length=k.length("spline_length"),
        spline_extra_depth=inches(1, 2),
        slot_symmetric_extra_length=inches(1, 4),
        shoulder_symmetric_inset=k.length("shoulder_symmetric_inset"),
        slot_lateral_offset=inches(0),
        peg_parameters=SimplePegParameters(
            shape=k.choice("peg_shape"),
            peg_positions=[(mm(30), scalar(0))],
            size=k.length("peg_size"),
        ),
    )
    return Frame.from_joints([joint], name="Splined Opposing Double Butt Joint")


SPLINE = kiwari(
    slot_thickness=kiwari.length(inches(1)),
    slot_depth=kiwari.length(inches(2)),
    spline_length=kiwari.length(inches(12)),
    shoulder_symmetric_inset=kiwari.length(inches(1)),
    peg_shape=kiwari.choice(PegShape, PegShape.SQUARE),
    peg_size=kiwari.length(mm(15)),
)


@pattern('butt/splined_opposing_double_butt_joint', tags=["main"], kiwari=SPLINE)
def splined_opposing_double_butt_joint_pattern(k: Optional[Kiwari] = None) -> Frame:
    return make_splined_opposing_double_butt_joint_example(create_v3(0, 0, 0), SPLINE.resolve(k))
