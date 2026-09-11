"""
Splined Opposing Double Butt Joint Patterns
"""

from kumiki.rule import V3, inches, mm, scalar
from kumiki.timber import Frame, PegShape, TimberEnd
from kumiki.joints.workshop.butt import cut_splined_opposing_double_butt_joint_on_face_aligned_timbers
from kumiki.joints.workshop.shavings.build_a_butt import SimplePegParameters
from kumiki.example_shavings import create_canonical_example_opposing_double_butt_joint_timbers
from kumiki.patternbook import Pattern


def make_splined_opposing_double_butt_joint_example(position: V3) -> Frame:
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
        slot_thickness=inches(1),
        slot_depth=inches(2),
        spline_length=inches(12),
        spline_extra_depth=inches(1, 2),
        slot_symmetric_extra_length=inches(1, 4),
        shoulder_symmetric_inset=inches(1),
        slot_lateral_offset=inches(0),
        peg_parameters=SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(mm(30), scalar(0))],
            size=mm(15),
        ),
    )
    return Frame.from_joints([joint], name="Splined Opposing Double Butt Joint")


patterns = [
    Pattern(path="multi_butt_joints/splined_opposing_double_butt_joint", lambda_=make_splined_opposing_double_butt_joint_example, pattern_type='frame', tags=['main']),
]
