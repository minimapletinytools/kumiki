"""
Wedged Half-Dovetail Joint Patterns
"""

from dataclasses import replace

from kumiki import *
from kumiki.joints.workshop.shavings.build_a_butt import (
    DovetailTenonWedgeAccessoryParameters,
)
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_butt_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import Pattern, make_pattern_from_joint


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[1], _CANONICAL_EXAMPLE_TIMBER_SIZE[0]) * sqrt(2)
    )


def example_wedged_half_dovetail_mortise_and_tenon(position=None, use_round_timbers=False):
    """
    Wedged half-dovetail mortise and tenon joint on the canonical 4"x5"x4'
    butt joint timbers. The dovetail's flat (top) side sits on the FRONT face
    of the butt timber, which aligns with the receiving timber's length axis.
    A wedge accessory is included to lock the tenon.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = replace(
        create_canonical_example_butt_joint_timbers(
            position,
            timber_config=_maybe_round_timber_config(use_round_timbers),
        ),
        top_face_on_butt_timber=TimberLongFace.FRONT,
    )
    return cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(4)]),
        tenon_depth=inches(4),
        dovetail_depth=inches(1, 2),
        mortise_shoulder_inset=inches(1, 2),
        receiving_timber_mortise_extra_depth=inches(1, 2),
        wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
            wedge_angle=degrees(8),
            wedge_tip_stickout=inches(1),
            wedge_back_extra_length=inches(1),
        ),
    )


patterns = [
    Pattern(path="butt_joints/wedged_half_dovetail_mortise_and_tenon", lambda_=make_pattern_from_joint(example_wedged_half_dovetail_mortise_and_tenon), pattern_type='frame'),
]
