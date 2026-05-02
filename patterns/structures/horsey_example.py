"""
Sawhorse Example - A simple sawhorse structure with mortise and tenon joints

This example creates a sawhorse with:
- Two horizontal beams (feet) on a 3.5ft x 2ft footprint
- Two vertical posts connecting the beams
- A horizontal stretcher between the posts
- A top plate spanning across the posts

All joints are mortise and tenon with pegs.
"""

from kumiki import *

# Define timber dimensions
beam_size = Matrix([inches(4), inches(6)])  # 4x6 with 6" in Z
post_size = Matrix([inches(4), inches(4)])  # 4x4
stretcher_size = Matrix([inches(4), inches(4)])  # 4x4
plate_size = Matrix([inches(4), inches(6)])  # 4x6 with 6" in Y

# Define dimensions
footprint_width = feet(Rational(7, 2))  # 3.5 feet in X
footprint_length = feet(2)  # 2 feet in Y
beam_length = feet(2)  # 2 feet in Y direction
post_height = feet(2)  # 2 feet tall
plate_length = feet(5)  # 5 feet in X direction

# Joint parameters
tenon_thickness = inches(1)
tenon_width = inches(3)
tenon_length = inches(3)
mortise_depth = tenon_length + inches(0.25)
peg_diameter = inches(Rational(5, 8))
peg_distance_from_shoulder = inches(1)


def create_sawhorse() -> Frame:
    """
    Create a complete sawhorse structure with mortise and tenon joints with pegs.
    
    Returns:
        Frame: Frame object containing all cut timbers for the complete sawhorse
    """
    
    # Calculate beam positions on the inside of the footprint
    # Footprint X spans from -footprint_width/2 to +footprint_width/2
    # Beams are 4" wide, positioned inside the footprint edges
    beam_offset_x = footprint_width / 2 - beam_size[0] / 2
    
    # Create left beam (4x6, runs in Y direction, 6" dimension in Z)
    left_beam = create_axis_aligned_timber(
        bottom_position=create_v3(-beam_offset_x, -beam_length / 2, Rational(0)),
        length=beam_length,
        size=beam_size,
        length_direction=TimberFace.FRONT,  # Y direction
        width_direction=TimberFace.RIGHT,   # X direction (width is 4")
        ticket="Left Beam"
    )
    
    # Create right beam (4x6, runs in Y direction, 6" dimension in Z)
    right_beam = create_axis_aligned_timber(
        bottom_position=create_v3(beam_offset_x, -beam_length / 2, Rational(0)),
        length=beam_length,
        size=beam_size,
        length_direction=TimberFace.FRONT,  # Y direction
        width_direction=TimberFace.RIGHT,   # X direction (width is 4")
        ticket="Right Beam"
    )
    
    # Create left post (4x4, vertical, centered on left beam)
    left_post = create_axis_aligned_timber(
        bottom_position=create_v3(-beam_offset_x, Rational(0), beam_size[1]),  # Start at top of beam
        length=post_height,
        size=post_size,
        length_direction=TimberFace.TOP,    # Z direction
        width_direction=TimberFace.RIGHT,   # X direction
        ticket="Left Post"
    )
    
    # Create right post (4x4, vertical, centered on right beam)
    right_post = create_axis_aligned_timber(
        bottom_position=create_v3(beam_offset_x, Rational(0), beam_size[1]),  # Start at top of beam
        length=post_height,
        size=post_size,
        length_direction=TimberFace.TOP,    # Z direction
        width_direction=TimberFace.RIGHT,   # X direction
        ticket="Right Post"
    )
    
    # Create stretcher (4x4, horizontal, connects the two posts at their midpoint)
    # Stretcher runs in X direction between the posts
    stretcher_z_position = beam_size[1] + post_height / 2  # Middle of posts
    stretcher_length = 2 * beam_offset_x  # Distance between post centers
    
    stretcher = create_axis_aligned_timber(
        bottom_position=create_v3(-beam_offset_x, Rational(0), stretcher_z_position),
        length=stretcher_length,
        size=stretcher_size,
        length_direction=TimberFace.RIGHT,  # X direction
        width_direction=TimberFace.FRONT,   # Y direction
        ticket="Stretcher"
    )
    
    # Create top plate (4x6 with 6" in Y, 5ft long in X direction)
    plate_z_position = beam_size[1] + post_height  # Top of posts
    
    plate = create_axis_aligned_timber(
        bottom_position=create_v3(-plate_length / 2, Rational(0), plate_z_position),
        length=plate_length,
        size=plate_size,
        length_direction=TimberFace.RIGHT,  # X direction (5ft long)
        width_direction=TimberFace.FRONT,   # Y direction (6" wide)
        ticket="Top Plate"
    )
    
    # ============================================================================
    # Create joints with pegs
    # ============================================================================
    
    # ============================================================================
    # Peg parameters for all joints
    # ============================================================================
    # Base peg parameters: 5/8" diameter, 1" from shoulder, centered on tenon
    base_peg_params = SimplePegParameters(
        shape=PegShape.ROUND,
        peg_positions=[(peg_distance_from_shoulder, Rational(0))],  # 1" from shoulder, centered
        size=peg_diameter,
        depth=None,  # Through peg
        tenon_hole_offset=Rational(0)
    )
    
    # Joint 1 & 2: Posts into beams
    # Post: length=Z (TOP), width=X (RIGHT), depth=Y (FRONT)
    # Beam: length=Y (FRONT)
    # Tenon at post BOTTOM going up into beam - peg goes through RIGHT face
    peg_params_post_beam = base_peg_params  # Already has RIGHT face

    left_beam_post_joint = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=left_beam,
            butt_timber=left_post,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        ),
        tenon_size=Matrix([tenon_thickness, tenon_width]),  # 1" x 3" (3" in beam's Y direction)
        tenon_length=tenon_length,
        mortise_depth=None,  # Through mortise
        peg_parameters=peg_params_post_beam,
    )

    right_beam_post_joint = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=right_beam,
            butt_timber=right_post,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        ),
        tenon_size=Matrix([tenon_thickness, tenon_width]),  # 1" x 3" (3" in beam's Y direction)
        tenon_length=tenon_length,
        mortise_depth=None,  # Through mortise
        peg_parameters=peg_params_post_beam,
    )
    
    # Joint 3 & 4: Stretcher into posts
    # Stretcher: length=X (RIGHT), width=Y (FRONT), depth=Z
    # Post: length=Z (TOP), mortise on LEFT/RIGHT face
    # Tenon at stretcher ends going sideways into posts - peg through LEFT face
    peg_params_stretcher = base_peg_params

    left_post_stretcher_joint = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=left_post,
            butt_timber=stretcher,
            butt_timber_end=TimberReferenceEnd.BOTTOM,  # Left end of stretcher
            front_face_on_butt_timber=TimberLongFace.LEFT,
        ),
        tenon_size=Matrix([tenon_thickness, tenon_width]),  # 1" x 3" (3" in post's Z direction)
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params_stretcher,
    )

    right_post_stretcher_joint = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=right_post,
            butt_timber=stretcher,
            butt_timber_end=TimberReferenceEnd.TOP,  # Right end of stretcher
            front_face_on_butt_timber=TimberLongFace.LEFT,
        ),
        tenon_size=Matrix([tenon_thickness, tenon_width]),  # 1" x 3" (3" in post's Z direction)
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params_stretcher,
    )
    
    # Joint 5 & 6: Posts into plate
    # Post: length=Z (TOP), width=X (RIGHT), depth=Y (FRONT)
    # Plate: length=X (RIGHT)
    # Tenon at post TOP going up into plate - peg goes through FRONT face
    peg_params_post_plate = base_peg_params

    left_post_plate_joint = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate,
            butt_timber=left_post,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_size=Matrix([tenon_width, tenon_thickness]),  # 3" x 1" (3" in plate's X direction)
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params_post_plate,
    )

    right_post_plate_joint = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate,
            butt_timber=right_post,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_size=Matrix([tenon_width, tenon_thickness]),  # 3" x 1" (3" in plate's X direction)
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params_post_plate,
    )
    
    # ============================================================================
    # Create Frame from joints using the new from_joints constructor
    # ============================================================================
    # The from_joints method automatically:
    # - Extracts all cut timbers from the joints
    # - Merges cuts for timbers that appear in multiple joints
    # - Collects all accessories (pegs, wedges, etc.)
    
    all_joints = [
        left_beam_post_joint,
        right_beam_post_joint,
        left_post_stretcher_joint,
        right_post_stretcher_joint,
        left_post_plate_joint,
        right_post_plate_joint
    ]
    
    return Frame.from_joints(all_joints, name="Sawhorse")


example = create_sawhorse


def main():
    """Main function that creates and returns the sawhorse frame."""
    frame = create_sawhorse()
    
    print(f"Created sawhorse '{frame.name}' with {len(frame.cut_timbers)} timbers:")
    print()
    
    for i, cut_timber in enumerate(frame.cut_timbers):
        timber = cut_timber.timber
        print(f"{i+1}. {timber.ticket.name}")
        print(f"   Length: {float(timber.length):.3f}m ({float(timber.length) / 0.0254:.1f} inches)")
        print(f"   Size: {float(timber.size[0]):.3f}m x {float(timber.size[1]):.3f}m "
              f"({float(timber.size[0]) / 0.0254:.1f}\" x {float(timber.size[1]) / 0.0254:.1f}\")")
        print(f"   Position: ({float(timber.get_bottom_position_global()[0]):.3f}, "
              f"{float(timber.get_bottom_position_global()[1]):.3f}, "
              f"{float(timber.get_bottom_position_global()[2]):.3f}) meters")
        print(f"   Cuts: {len(cut_timber.cuts)}")
        print()
    
    print(f"Total accessories (pegs, etc.): {len(frame.accessories)}")
    
    return frame


if __name__ == "__main__":
    frame = main()
    print(f"\nFrame '{frame.name}' ready for rendering or further processing.")

