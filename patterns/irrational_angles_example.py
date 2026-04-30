"""
Irrational Angles Example

This module creates a simple mortise and tenon joint at an irrational angle
to test the precision and alignment of CSG operations when SymPy's exact 
representations are converted to floating point values in CAD systems.
"""

from sympy import Rational, pi, Matrix, cos, sin
from kumiki.timber import Frame, TimberFace, TimberReferenceEnd, create_v3, timber_from_directions
from kumiki.construction import ButtJointTimberArrangement
from kumiki.joints.mortise_and_tenon_joint import cut_mortise_and_tenon_joint
from kumiki.patternbook import PatternBook, PatternMetadata


def create_irrational_angles_patternbook() -> PatternBook:
    """
    Create a PatternBook with irrational angles test pattern.
    
    Returns:
        PatternBook: PatternBook containing the irrational angles test pattern
    """
    patterns = [
        (PatternMetadata("irrational_angles_test", ["irrational_angles", "test_examples"], "frame"),
         lambda center: create_all_irrational_examples()),
    ]
    
    return PatternBook(patterns=patterns)


patternbook = create_irrational_angles_patternbook()


def create_all_irrational_examples() -> Frame:
    """
    Create a mortise and tenon joint at 37 degrees (an irrational angle).
    
    This tests whether CSG cuts align properly when timbers are rotated
    at irrational angles and SymPy values are converted to floats.
    """
    # Vertical post (mortise timber)
    post = timber_from_directions(
        length=Rational(96),
        size=Matrix([Rational(6), Rational(6)]),
        bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
        length_direction=create_v3(Rational(0), Rational(0), Rational(1)),
        width_direction=create_v3(Rational(1), Rational(0), Rational(0)),
        ticket="Vertical Post"
    )
    
    # Angled beam at 37° (tenon timber)
    angle_37 = pi * Rational(37, 180)  # 37 degrees in radians (irrational, exact)
    
    # Direction vector at 37° in XY plane
    length_dir = create_v3(cos(angle_37), sin(angle_37), Rational(0))
    width_dir = create_v3(Rational(0), Rational(0), Rational(1))
    
    beam = timber_from_directions(
        length=Rational(60),
        size=Matrix([Rational(4), Rational(6)]),
        bottom_position=create_v3(Rational(0), Rational(0), Rational(48)),
        length_direction=length_dir,
        width_direction=width_dir,
        ticket="Angled Beam (37°)"
    )
    
    # Create mortise and tenon joint
    tenon_size = Matrix([Rational(2), Rational(3)])  # width x thickness
    arrangement = ButtJointTimberArrangement(
        receiving_timber=post,
        butt_timber=beam,
        butt_timber_end=TimberReferenceEnd.BOTTOM,
        front_face_on_butt_timber=None,
    )
    joint = cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=Rational(4),
        mortise_depth=Rational(4),
    )
    
    frame = Frame.from_joints([joint], name="Mortise and Tenon at 37°")
    
    print("Creating Irrational Angles Example...")
    print("=" * 70)
    print("\nMortise and Tenon Joint at 37° (irrational angle)")
    print("  Timbers: 2")
    print("  - Vertical Post (mortise)")
    print("  - Angled Beam at 37° (tenon)")
    print("\n" + "=" * 70)
    print("Example created successfully!")
    print("\nThis tests CSG alignment at an irrational angle (37° = 37π/180 radians).")
    print("Render in Fusion360 or FreeCAD to check for z-fighting or misalignment.")
    print()
    
    return frame


example = create_all_irrational_examples


if __name__ == "__main__":
    create_all_irrational_examples()
