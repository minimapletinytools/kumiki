"""Three-piece Luban lock (鲁班锁三通) / burr puzzle cross.

Three 1×1×3 timbers form a cross around the origin:
  - Timber 'x' runs along the X axis, centered at the origin
  - Timber 'y' runs along the Y axis, centered at the origin
  - Timber 'z' runs along the Z axis, centered at the origin

Timber 'x' cut:
  In the middle third (X ∈ [-0.5, +0.5]):
  Looking along the X axis, the cross-section is split into 4 quadrants (each 1/2 × 1/2):
    - (+y, +z): removed (negative 1/2 × 1/2 × 1 prism)
    - (-y, -z): removed (negative 1/2 × 1/2 × 1 prism)
    - (+y, -z): removed (negative 1/2 × 1/2 × 1 prism)
    - (-y, +z): positive cylinder with parallel length axis
      (negative 1/2 × 1/2 × 1 prism minus positive cylinder)

NOTE: Disassembly and the assembly solver (solve_frame_assembly) will not work
on this frame until rotational degrees of freedom (RotationDof) are supported
in the solver (currently raises NotImplementedError).
"""

from kumiki import *
from kumiki.cutcsg import RectangularPrism, Cylinder, Difference, SolidUnion
from kumiki.assembly import RotationDof, TranslationDof


# --- Dimensions -----------------------------------------------------------

side = inches(1)
length = inches(3)
block_size = create_v2(side, side)


def example() -> Frame:
    # Half-length offset so bottom_position puts the timber centroid at (0, 0, 0)
    half_len = length / scalar(2)

    # -- X-axis timber ------------------------------------------------------
    # Length runs along +X, width along +Y, height along +Z.
    # Centered at the origin: X in [-1.5, +1.5], Y in [-0.5, +0.5], Z in [-0.5, +0.5].
    x_timber = create_timber(
        length=length,
        size=block_size,
        bottom_position=create_v3(-half_len, scalar(0), scalar(0)),
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
        ticket=TimberTicket(path="x", tags=(GenericTag("x-axis"),)),
    )

    # -- Y-axis timber ------------------------------------------------------
    # Length runs along +Y, width along +Z, height along +X.
    # Centered at the origin: X in [-0.5, +0.5], Y in [-1.5, +1.5], Z in [-0.5, +0.5].
    y_timber = create_timber(
        length=length,
        size=block_size,
        bottom_position=create_v3(scalar(0), -half_len, scalar(0)),
        length_direction=create_v3(scalar(0), scalar(1), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket=TimberTicket(path="y", tags=(GenericTag("y-axis"),)),
    )

    # -- Z-axis timber ------------------------------------------------------
    # Length runs along +Z, width along +X, height along +Y.
    # Centered at the origin: X in [-0.5, +0.5], Y in [-0.5, +0.5], Z in [-1.5, +1.5].
    z_timber = create_timber(
        length=length,
        size=block_size,
        bottom_position=create_v3(scalar(0), scalar(0), -half_len),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket=TimberTicket(path="z", tags=(GenericTag("z-axis"),)),
    )

    # -- Timber 'x' joint cut -----------------------------------------------
    # In x_timber local coordinates:
    #   - local Z is along +X (length axis), running from 0 to 3 inches
    #   - middle third is local Z in [1", 2"] (length = 1")
    #   - local X is along +Y (width axis), in [-0.5", +0.5"]
    #   - local Y is along +Z (height axis), in [-0.5", +0.5"]
    #
    # The middle third is divided into 4 quadrants (each 1/2" × 1/2" cross section):
    #   1. (+y, +z) section: local X in [0, 0.5], local Y in [0, 0.5] (center at +1/4, +1/4)
    #   2. (-y, -z) section: local X in [-0.5, 0], local Y in [-0.5, 0] (center at -1/4, -1/4)
    #   3. (+y, -z) section: local X in [0, 0.5], local Y in [-0.5, 0] (center at +1/4, -1/4)
    #   4. (-y, +z) section: local X in [-0.5, 0], local Y in [0, 0.5] (center at -1/4, +1/4)
    quadrant_size = create_v2(inches(1, 2), inches(1, 2))
    quarter = inches(1, 4)
    third_start = inches(1)
    third_len = inches(1)

    # 1. (+y, +z) section - removed
    p_pos_y_pos_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(quarter, quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    # 2. (-y, -z) section - removed
    p_neg_y_neg_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(-quarter, -quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    # 3. (+y, -z) section - removed
    p_pos_y_neg_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(quarter, -quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    # 4. (-y, +z) section - negative prism minus positive cylinder
    p_neg_y_pos_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(-quarter, quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    cyl_neg_y_pos_z = Cylinder(
        axis_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        radius=quarter,
        position=create_v3(-quarter, quarter, third_start),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    # Shavings/waste around the cylinder to be removed
    cut_neg_y_pos_z = Difference(base=p_neg_y_pos_z, subtract=[cyl_neg_y_pos_z])

    # Combined negative CSG for timber 'x'
    x_negative_csg = SolidUnion([
        p_pos_y_pos_z,
        p_neg_y_neg_z,
        p_pos_y_neg_z,
        cut_neg_y_pos_z,
    ])

    x_joint = Joint(
        cuttings={"x": Cutting(timber=x_timber, negative_csg=x_negative_csg)},
        ticket=JointTicket(path="x_joint"),
    )

    # -- Timber 'y' joint cut -----------------------------------------------
    # In y_timber local coordinates:
    #   - local Z is along +Y (length axis), running from 0 to 3 inches
    #   - middle third is local Z in [1", 2"] (length = 1")
    #   - local X is along +Z (height axis in global), in [-0.5", +0.5"]
    #   - local Y is along +X (width axis in global), in [-0.5", +0.5"]
    #
    # Looking down the Y axis, we split the center into 4 quadrants:
    # Keep (+x, -z) [local Y > 0, local X < 0], and remove the other 3 quadrants:
    #   1. (+x, +z) section: local Y in [0, 0.5], local X in [0, 0.5] (center at +1/4, +1/4)
    #   2. (-x, +z) section: local Y in [-0.5, 0], local X in [0, 0.5] (center at -1/4, +1/4)
    #   3. (-x, -z) section: local Y in [-0.5, 0], local X in [-0.5, 0] (center at -1/4, -1/4)

    # 1. (+x, +z) section - removed
    p_pos_x_pos_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(quarter, quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    # 2. (-x, +z) section - removed
    p_neg_x_pos_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(quarter, -quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    # 3. (-x, -z) section - removed
    p_neg_x_neg_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(-quarter, -quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    # Combined negative CSG for timber 'y'
    y_negative_csg = SolidUnion([
        p_pos_x_pos_z,
        p_neg_x_pos_z,
        p_neg_x_neg_z,
    ])

    y_joint = Joint(
        cuttings={"y": Cutting(timber=y_timber, negative_csg=y_negative_csg)},
        ticket=JointTicket(path="y_joint"),
    )

    # -- Timber 'z' joint cut -----------------------------------------------
    # In z_timber local coordinates:
    #   - local Z is along +Z (length axis), running from 0 to 3 inches
    #   - middle third is local Z in [1", 2"] (length = 1")
    #   - local X is along +X (width axis in global), in [-0.5", +0.5"]
    #   - local Y is along +Y (height axis in global), in [-0.5", +0.5"]
    #
    # Looking down the Z axis, we:
    #   - Keep (-x, +y) quadrant [local X < 0, local Y > 0] across full middle third Z ∈ [1, 2]
    #   - Keep (-x, -y, -z) octant [local X < 0, local Y < 0, local Z ∈ [1.0, 1.5]]
    #   - Keep (+x, +y, +z) octant [local X > 0, local Y > 0, local Z ∈ [1.5, 2.0]]
    #   - Remove everything else:
    #       1. (+x, -y) quadrant across full middle third Z ∈ [1, 2]
    #       2. (+x, +y, -z) octant: local X > 0, local Y > 0, local Z ∈ [1.0, 1.5]
    #       3. (-x, -y, +z) octant: local X < 0, local Y < 0, local Z ∈ [1.5, 2.0]
    half_inch = inches(1, 2)
    octant_start = inches(3, 2)  # 1.5 inches from bottom

    # 1. (+x, -y) quadrant - removed across full middle third
    p_pos_x_neg_y = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(quarter, -quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=third_len,
    )

    # 2. (+x, +y, -z) octant - removed (leaving +x, +y, +z filled)
    p_pos_x_pos_y_neg_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(quarter, quarter, third_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=half_inch,
    )

    # 3. (-x, -y, +z) octant - removed
    p_neg_x_neg_y_pos_z = RectangularPrism(
        size=quadrant_size,
        transform=Transform(
            position=create_v3(-quarter, -quarter, octant_start),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=half_inch,
    )

    # Combined negative CSG for timber 'z'
    z_negative_csg = SolidUnion([
        p_pos_x_neg_y,
        p_pos_x_pos_y_neg_z,
        p_neg_x_neg_y_pos_z,
    ])

    # -- Assembly Freedoms --------------------------------------------------
    # NOTE: Disassembly / the assembly solver does not yet support rotational DOFs
    # (RotationDof raises NotImplementedError in solve_frame_assembly).
    #
    # 1. Between X and Y: X rotates about cylinder axis by +90°, then is free.
    #    Cylinder axis runs along +X at Y = -0.25", Z = +0.25".
    PX = create_v3(scalar(1), scalar(0), scalar(0))
    PY = create_v3(scalar(0), scalar(1), scalar(0))
    cyl_axis_pos = create_v3(scalar(0), -quarter, quarter)

    rot_x = RotationDof(
        axis_position=cyl_axis_pos,
        axis_direction=PX,
        freed_after_angle=degrees(90),
    )
    rot_neg_x = RotationDof(
        axis_position=cyl_axis_pos,
        axis_direction=-PX,
        freed_after_angle=degrees(90),
    )

    freedom_x_in_xy = AssemblyFreedom(rotations=(rot_x,))
    freedom_y_in_xy = AssemblyFreedom(rotations=(rot_neg_x,))

    # 2. Between Y and Z: Y moves in +X and is free after 1.
    freedom_y_in_yz = AssemblyFreedom.translation(PX, side)
    freedom_z_in_yz = AssemblyFreedom.translation(-PX, side)

    # 3. Between Z and X: Z moves in +Y and is free after 1;
    #    also X rotates about cylinder axis by +90° (and Z opposite).
    trans_z_in_zx = TranslationDof(direction=PY, freed_after=side)
    trans_x_in_zx = TranslationDof(direction=-PY, freed_after=side)
    freedom_z_in_zx = AssemblyFreedom(
        translations=(trans_z_in_zx,),
        rotations=(rot_neg_x,),
    )
    freedom_x_in_zx = AssemblyFreedom(
        translations=(trans_x_in_zx,),
        rotations=(rot_x,),
    )

    # -- Joints -------------------------------------------------------------
    # Joint between X and Y:
    x_and_y = Joint(
        cuttings={
            "x": Cutting(timber=x_timber, negative_csg=x_negative_csg, assembly_freedom=freedom_x_in_xy),
            "y": Cutting(timber=y_timber, assembly_freedom=freedom_y_in_xy),
        },
        ticket=JointTicket(path="x_and_y"),
    )

    # Joint between Y and Z:
    y_and_z = Joint(
        cuttings={
            "y": Cutting(timber=y_timber, negative_csg=y_negative_csg, assembly_freedom=freedom_y_in_yz),
            "z": Cutting(timber=z_timber, assembly_freedom=freedom_z_in_yz),
        },
        ticket=JointTicket(path="y_and_z"),
    )

    # Joint between Z and X:
    z_and_x = Joint(
        cuttings={
            "z": Cutting(timber=z_timber, negative_csg=z_negative_csg, assembly_freedom=freedom_z_in_zx),
            "x": Cutting(timber=x_timber, assembly_freedom=freedom_x_in_zx),
        },
        ticket=JointTicket(path="z_and_x"),
    )

    return Frame.from_joints(
        [x_and_y, y_and_z, z_and_x],
        name="luban_lock_2",
    )



