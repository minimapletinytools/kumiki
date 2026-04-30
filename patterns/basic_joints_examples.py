"""
Example usage of basic joint construction functions
Uses canonical timber configurations from construction.py
"""

from sympy import Matrix, Rational
from kumiki.rule import inches, Transform
from kumiki.timber import (
    Timber, TimberReferenceEnd, TimberFace, TimberLongFace, Peg, Wedge,
    PegShape, timber_from_directions,
    create_v3, V2, CutTimber, Frame
)
from kumiki.ticket import Ticket
from kumiki.joints.basic_joints import (
    cut_basic_miter_joint,
    cut_basic_miter_joint_on_face_aligned_timbers,
    cut_basic_tongue_and_fork_corner_joint,
    cut_basic_butt_joint_on_face_aligned_timbers,
    cut_basic_butt_splice_joint_on_aligned_timbers,
    cut_basic_cross_lap_joint,
    cut_basic_house_joint,
    cut_basic_splined_opposing_double_butt_joint,
    cut_basic_splice_lap_joint_on_aligned_timbers,
    cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers,
    cut_basic_lapped_gooseneck_joint,
    cut_basic_housed_dovetail_butt_joint,
    cut_basic_mitered_and_keyed_lap_joint,
)
from kumiki.example_shavings import (
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_splice_joint_timbers,
    create_canonical_example_cross_joint_timbers,
    create_canonical_example_opposing_double_butt_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_LENGTH,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import PatternBook, PatternMetadata, make_pattern_from_joint


def example_basic_miter_joint(position=None):
    """
    Create a basic miter joint using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_miter_joint(arrangement)
    
    return joint


def example_basic_miter_joint_face_aligned(position=None):
    """
    Create a basic miter joint on face-aligned timbers using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_miter_joint_on_face_aligned_timbers(arrangement)
    
    return joint


def example_basic_tongue_and_fork_joint(position=None):
    """
    Create a basic tongue-and-fork corner joint using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_tongue_and_fork_corner_joint(arrangement)

    return joint


def example_basic_butt_joint(position=None):
    """
    Create a basic butt joint using canonical butt joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    arrangement = create_canonical_example_butt_joint_timbers(position)
    joint = cut_basic_butt_joint_on_face_aligned_timbers(arrangement)
    
    return joint


def example_basic_butt_splice_joint(position=None):
    """
    Create a basic butt splice joint using canonical splice joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    arrangement = create_canonical_example_splice_joint_timbers(position)
    joint = cut_basic_butt_splice_joint_on_aligned_timbers(arrangement)
    
    return joint


def example_basic_cross_lap_joint(position=None):
    """
    Create a basic cross lap joint using canonical cross joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    arrangement = create_canonical_example_cross_joint_timbers(position=position)
    joint = cut_basic_cross_lap_joint(arrangement)
    
    return joint


def example_basic_house_joint(position=None):
    """
    Create a basic house joint using canonical cross joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    # TODO offset
    arrangement = create_canonical_example_cross_joint_timbers(position=position, lateral_offset=inches(2))
    joint = cut_basic_house_joint(arrangement)
    
    return joint


def example_basic_splined_opposing_double_butt_joint(position=None):
    """
    Create a basic splined opposing double butt joint using canonical timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_opposing_double_butt_joint_timbers(position)
    joint = cut_basic_splined_opposing_double_butt_joint(
        arrangement=arrangement,
        slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
    )

    return joint


def example_basic_splice_lap_joint(position=None):
    """
    Create a basic splice lap joint using canonical splice joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    from kumiki.construction import SpliceJointTimberArrangement
    arrangement = create_canonical_example_splice_joint_timbers(position)
    joint = cut_basic_splice_lap_joint_on_aligned_timbers(
        SpliceJointTimberArrangement(
            timber1=arrangement.timber1,
            timber2=arrangement.timber2,
            timber1_end=arrangement.timber1_end,
            timber2_end=arrangement.timber2_end,
            front_face_on_timber1=TimberLongFace.FRONT,
        )
    )
    return joint


def example_basic_mortise_and_tenon_joint(position=None):
    """
    Create a basic mortise and tenon joint using canonical butt joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    arrangement = create_canonical_example_butt_joint_timbers(position)
    joint = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
        tenon_timber=arrangement.butt_timber,
        mortise_timber=arrangement.receiving_timber,
        tenon_end=arrangement.butt_timber_end,
        use_peg=False
    )
    
    return joint


def example_basic_mortise_and_tenon_joint_with_peg(position=None):
    """
    Create a basic mortise and tenon joint with peg using canonical butt joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    arrangement = create_canonical_example_butt_joint_timbers(position)
    joint = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
        tenon_timber=arrangement.butt_timber,
        mortise_timber=arrangement.receiving_timber,
        tenon_end=arrangement.butt_timber_end,
        use_peg=True
    )
    
    return joint


def example_basic_lapped_gooseneck_joint(position=None):
    """
    Create a basic lapped gooseneck joint.
    Uses canonical splice joint timbers (parallel timbers meeting at position).
    """
    arrangement = create_canonical_example_splice_joint_timbers(position)
    joint = cut_basic_lapped_gooseneck_joint(
        gooseneck_timber=arrangement.timber2,
        receiving_timber=arrangement.timber1,
        receiving_timber_end=arrangement.timber1_end,
        gooseneck_timber_face=TimberLongFace.RIGHT,
    )
    return joint


def example_basic_housed_dovetail_butt_joint(position=None):
    """
    Create a basic housed dovetail butt joint.
    Uses canonical butt joint timbers (receiving along X, butt/dovetail along Y).
    """
    from sympy import Integer

    arrangement = create_canonical_example_butt_joint_timbers(position)
    # Face perpendicular to receiving timber length (X): use RIGHT (normal +Z) on butt timber
    dovetail_timber_face = TimberLongFace.RIGHT
    width = arrangement.butt_timber.get_size_in_face_normal_axis(dovetail_timber_face.rotate_right())
    dovetail_length = width / Integer(2)
    dovetail_small_width = width * Rational(1, 2)
    dovetail_large_width = width * Rational(2, 3)
    receiving_timber_shoulder_inset = inches(1)  # 1 inch inset

    joint = cut_basic_housed_dovetail_butt_joint(
        dovetail_timber=arrangement.butt_timber,
        receiving_timber=arrangement.receiving_timber,
        dovetail_timber_end=arrangement.butt_timber_end,
        dovetail_timber_face=dovetail_timber_face,
        receiving_timber_shoulder_inset=receiving_timber_shoulder_inset,
        dovetail_length=dovetail_length,
        dovetail_small_width=dovetail_small_width,
        dovetail_large_width=dovetail_large_width
    )
    return joint


def example_basic_mitered_and_keyed_lap_joint(position=None):
    """
    Create a basic mitered and keyed lap joint using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_mitered_and_keyed_lap_joint(
        arrangement=arrangement
    )
    
    return joint


def create_basic_joints_patternbook() -> PatternBook:
    """
    Create a PatternBook with all basic joint patterns.
    
    Each pattern has groups: ["basic_joints", "{variant}"]
    For example: ["basic_joints", "miter"] or ["basic_joints", "butt"]
    
    Returns:
        PatternBook: PatternBook containing all basic joint patterns
    """
    patterns = [
        (PatternMetadata("basic_miter", ["basic_joints", "miter"], "frame"),
         make_pattern_from_joint(example_basic_miter_joint)),
        
        (PatternMetadata("basic_miter_face_aligned", ["basic_joints", "miter"], "frame"),
         make_pattern_from_joint(example_basic_miter_joint_face_aligned)),

        (PatternMetadata("basic_tongue_fork", ["basic_joints", "corner"], "frame"),
         make_pattern_from_joint(example_basic_tongue_and_fork_joint)),
        
        (PatternMetadata("basic_butt", ["basic_joints", "butt"], "frame"),
         make_pattern_from_joint(example_basic_butt_joint)),
        
        (PatternMetadata("basic_butt_splice", ["basic_joints", "splice"], "frame"),
         make_pattern_from_joint(example_basic_butt_splice_joint)),
        
        (PatternMetadata("basic_cross_lap", ["basic_joints", "lap"], "frame"),
         make_pattern_from_joint(example_basic_cross_lap_joint)),
        
        (PatternMetadata("basic_house", ["basic_joints", "house"], "frame"),
         make_pattern_from_joint(example_basic_house_joint)),

        (PatternMetadata("basic_splined_double_butt", ["basic_joints", "butt"], "frame"),
         make_pattern_from_joint(example_basic_splined_opposing_double_butt_joint)),
        
        (PatternMetadata("basic_splice_lap", ["basic_joints", "lap"], "frame"),
         make_pattern_from_joint(example_basic_splice_lap_joint)),
        
        (PatternMetadata("basic_mortise_tenon", ["basic_joints", "mortise_tenon"], "frame"),
         make_pattern_from_joint(example_basic_mortise_and_tenon_joint)),
        
        (PatternMetadata("basic_mortise_tenon_peg", ["basic_joints", "mortise_tenon"], "frame"),
         make_pattern_from_joint(example_basic_mortise_and_tenon_joint_with_peg)),
        
        (PatternMetadata("basic_gooseneck", ["basic_joints", "japanese"], "frame"),
         make_pattern_from_joint(example_basic_lapped_gooseneck_joint)),
        
        (PatternMetadata("basic_dovetail", ["basic_joints", "japanese"], "frame"),
         make_pattern_from_joint(example_basic_housed_dovetail_butt_joint)),
        
        (PatternMetadata("basic_mitered_keyed_lap", ["basic_joints", "japanese"], "frame"),
         make_pattern_from_joint(example_basic_mitered_and_keyed_lap_joint)),
    ]
    
    return PatternBook(patterns=patterns)


patternbook = create_basic_joints_patternbook()


def create_all_basic_joints_examples():
    """
    Create basic joint examples with automatic spacing.
    
    This uses the PatternBook to raise all patterns in the "basic_joints" group.
    
    Returns:
        Frame: Frame object containing all cut timbers and accessories for the examples
    """
    book = create_basic_joints_patternbook()
    
    # Raise all patterns in the "basic_joints" group with 6 feet spacing
    frame = book.raise_pattern_group("basic_joints", separation_distance=inches(72))
    
    return frame


example = create_all_basic_joints_examples
