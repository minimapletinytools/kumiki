"""Six-piece Luban lock (鲁班锁) / burr puzzle.

Six 1×1 wooden blocks (length = 2√2 × side), each rotated 45° around its
length axis so the cross section is a diamond.  Two blocks run along each
global axis (X, Y, Z).  The pairs are offset so that, viewed from any axis,
the two diamonds touch at one corner along the origin axis lines.

Naming convention
-----------------
  {axis}_{m|p}{offset_axis}
  e.g. y_mx = runs along Y, on the negative-X side

  Timber   Axis   Offset
  ------   ----   ------
  x_pz     X      +Z
  x_mz     X      -Z
  y_px     Y      +X
  y_mx     Y      -X
  z_py     Z      +Y
  z_my     Z      -Y

Housing cycle (housing ← housed)
---------------------------------
  X timbers house Y timbers   (Y housed into X)
  Y timbers house Z timbers   (Z housed into Y)
  Z timbers house X timbers   (X housed into Z)

Assembly freedoms
-----------------
Each timber in a joint has 3 degrees of freedom derived from the 45° diamond
facets and the timber's length axis.

For example, x_pz in z_my:
  1. ±X: slide along its own length axis
  2. (0, 1, 1): slide along one 45° diamond facet out of z_my
  3. (0, 1, -1): slide along the other 45° diamond facet out of z_my

In general, for a housed timber sitting in a 45° V-notch:
  - It slides along its own length axis (bidirectional).
  - It escapes the housing timber along the two 45° facet vectors facing
    away from the housing timber.

Housed timber freedoms:
  Housed in   Length axis   45° facet escape vectors
  ---------   -----------   ------------------------
  x in z_my   ±X            (0, 1, 1), (0, 1, -1)
  x in z_py   ±X            (0, -1, 1), (0, -1, -1)
  y in x_mz   ±Y            (1, 0, 1), (-1, 0, 1)
  y in x_pz   ±Y            (1, 0, -1), (-1, 0, -1)
  z in y_mx   ±Z            (1, 1, 0), (1, -1, 0)
  z in y_px   ±Z            (-1, 1, 0), (-1, -1, 0)

Housing timber freedoms (relative to housed timbers):
  The housing timber cannot slide along its own length axis (the notch
  walls prevent movement through the housed timber). It only escapes
  along the opposite 45° facet vectors facing away from the housed timber.

  Housing timber   45° facet escape vectors
  --------------   ------------------------
  z_my (houses x)  (0, -1, 1), (0, -1, -1)
  z_py (houses x)  (0, 1, 1), (0, 1, -1)
  x_mz (houses y)  (1, 0, -1), (-1, 0, -1)
  x_pz (houses y)  (1, 0, 1), (-1, 0, 1)
  y_mx (houses z)  (-1, 1, 0), (-1, -1, 0)
  y_px (houses z)  (1, 1, 0), (1, -1, 0)
"""

from dataclasses import replace
from kumiki import *
from kumiki.assembly import AssemblyFreedom


# --- Dimensions -----------------------------------------------------------

block_width = inches(1)
block_height = inches(1)
# Length = 2√2 × side so each timber spans exactly 2 full diagonals.
block_length = scalar(2) * sqrt(scalar(2)) * block_width
block_size = create_v2(block_width, block_height)

# Half-diagonal of the 1×1 square cross section = √2 / 2.
# For two diamonds to touch corner-to-corner, their centres must be
# separated by a full diagonal = √2 × (side / 2) × 2 = side × √2.
half_diag = block_width * sqrt(scalar(2)) / scalar(2)


def example() -> Frame:

    # -- X-axis pair --------------------------------------------------------
    # Length runs along +X, cross section in YZ rotated 45° around X.
    # Offset in ±Z so diamond corners touch along Z = 0.
    x_length_dir = create_v3(scalar(1), scalar(0), scalar(0))
    x_width_dir = create_v3(scalar(0), cos(degrees(45)), sin(degrees(45)))

    x_pz = create_timber(
        length=block_length,
        size=block_size,
        bottom_position=create_v3(-block_length / scalar(2), scalar(0), half_diag),
        length_direction=x_length_dir,
        width_direction=x_width_dir,
        ticket=TimberTicket(path="x_pz", tags=(GenericTag("x-pair"),)),
    )
    x_mz = create_timber(
        length=block_length,
        size=block_size,
        bottom_position=create_v3(-block_length / scalar(2), scalar(0), -half_diag),
        length_direction=x_length_dir,
        width_direction=x_width_dir,
        ticket=TimberTicket(path="x_mz", tags=(GenericTag("x-pair"),)),
    )

    # -- Y-axis pair --------------------------------------------------------
    # Length runs along +Y, cross section in XZ rotated 45° around Y.
    # Offset in ±X so diamond corners touch along X = 0.
    y_length_dir = create_v3(scalar(0), scalar(1), scalar(0))
    y_width_dir = create_v3(cos(degrees(45)), scalar(0), sin(degrees(45)))

    y_px = create_timber(
        length=block_length,
        size=block_size,
        bottom_position=create_v3(half_diag, -block_length / scalar(2), scalar(0)),
        length_direction=y_length_dir,
        width_direction=y_width_dir,
        ticket=TimberTicket(path="y_px", tags=(GenericTag("y-pair"),)),
    )
    y_mx = create_timber(
        length=block_length,
        size=block_size,
        bottom_position=create_v3(-half_diag, -block_length / scalar(2), scalar(0)),
        length_direction=y_length_dir,
        width_direction=y_width_dir,
        ticket=TimberTicket(path="y_mx", tags=(GenericTag("y-pair"),)),
    )

    # -- Z-axis pair --------------------------------------------------------
    # Length runs along +Z, cross section in XY rotated 45° around Z.
    # Offset in ±Y so diamond corners touch along Y = 0.
    z_length_dir = create_v3(scalar(0), scalar(0), scalar(1))
    z_width_dir = create_v3(cos(degrees(45)), sin(degrees(45)), scalar(0))

    z_py = create_timber(
        length=block_length,
        size=block_size,
        bottom_position=create_v3(scalar(0), half_diag, -block_length / scalar(2)),
        length_direction=z_length_dir,
        width_direction=z_width_dir,
        ticket=TimberTicket(path="z_py", tags=(GenericTag("z-pair"),)),
    )
    z_my = create_timber(
        length=block_length,
        size=block_size,
        bottom_position=create_v3(scalar(0), -half_diag, -block_length / scalar(2)),
        length_direction=z_length_dir,
        width_direction=z_width_dir,
        ticket=TimberTicket(path="z_my", tags=(GenericTag("z-pair"),)),
    )

    # -- Assembly freedom helpers -------------------------------------------
    # Escape distance — use the full timber length so pieces clear completely.
    freed = block_length / scalar(3)

    # Global axis unit directions
    PX = create_v3(scalar(1), scalar(0), scalar(0))
    PY = create_v3(scalar(0), scalar(1), scalar(0))
    PZ = create_v3(scalar(0), scalar(0), scalar(1))

    # 45° facet escape directions
    # In YZ plane (for X timbers):
    V_0_1_1 = create_v3(scalar(0), scalar(1), scalar(1))
    V_0_1_m1 = create_v3(scalar(0), scalar(1), scalar(-1))
    V_0_m1_1 = create_v3(scalar(0), scalar(-1), scalar(1))
    V_0_m1_m1 = create_v3(scalar(0), scalar(-1), scalar(-1))

    # In XZ plane (for Y timbers):
    V_1_0_1 = create_v3(scalar(1), scalar(0), scalar(1))
    V_m1_0_1 = create_v3(scalar(-1), scalar(0), scalar(1))
    V_1_0_m1 = create_v3(scalar(1), scalar(0), scalar(-1))
    V_m1_0_m1 = create_v3(scalar(-1), scalar(0), scalar(-1))

    # In XY plane (for Z timbers):
    V_1_1_0 = create_v3(scalar(1), scalar(1), scalar(0))
    V_1_m1_0 = create_v3(scalar(1), scalar(-1), scalar(0))
    V_m1_1_0 = create_v3(scalar(-1), scalar(1), scalar(0))
    V_m1_m1_0 = create_v3(scalar(-1), scalar(-1), scalar(0))

    # 3D body diagonal escape directions for simultaneous group separation:
    # Group 1: {x_pz, y_px, z_py} translates along (+1, +1, +1)
    # Group 2: {x_mz, y_mx, z_my} translates along (-1, -1, -1)
    V_1_1_1 = create_v3(scalar(1), scalar(1), scalar(1))
    V_m1_m1_m1 = create_v3(scalar(-1), scalar(-1), scalar(-1))

    def _make_house_joint(
        housing_timber: TimberLike,
        housed_timber: TimberLike,
        housed_length_axis: V3,
        housed_facet_1: V3,
        housed_facet_2: V3,
        ticket_path: str,
        housed_diagonal: Optional[V3] = None,
    ) -> Joint:
        """Cut a single free house joint.

        Freedoms are strictly symmetric opposites:
        - Housed timber:
            * its own length axis (bidirectional: ±housed_length_axis)
            * two 45° facet escape directions away from the housing timber
            * optional 3D diagonal escape direction (for crossing joints)
        - Housing timber:
            * exact opposite of all housed freedoms (Newtonian action/reaction):
              ∓housed_length_axis (same as ±housed_length_axis), -facet_1, -facet_2,
              and optional -housed_diagonal
            * zero freedom along the housing timber's length axis (blocked by the housed timber in its notch)
        """
        joint = cut_free_house_joint(
            housing_timber=housing_timber,
            housed_timbers=[housed_timber],
        )
        housed_freedom = AssemblyFreedom.combine(
            AssemblyFreedom.bidirectional_translation(housed_length_axis, freed),
            AssemblyFreedom.combine(
                AssemblyFreedom.translation(housed_facet_1, freed),
                AssemblyFreedom.translation(housed_facet_2, freed),
            ),
        )
        housing_freedom = AssemblyFreedom.combine(
            AssemblyFreedom.bidirectional_translation(housed_length_axis, freed),
            AssemblyFreedom.combine(
                AssemblyFreedom.translation(-housed_facet_1, freed),
                AssemblyFreedom.translation(-housed_facet_2, freed),
            ),
        )
        if housed_diagonal is not None:
            housed_freedom = AssemblyFreedom.combine(
                housed_freedom,
                AssemblyFreedom.translation(housed_diagonal, freed),
            )
            housing_freedom = AssemblyFreedom.combine(
                housing_freedom,
                AssemblyFreedom.translation(-housed_diagonal, freed),
            )
        new_cuttings = {
            "housing_timber": replace(joint.cuttings["housing_timber"], assembly_freedom=housing_freedom),
            "housed_timber_1": replace(joint.cuttings["housed_timber_1"], assembly_freedom=housed_freedom),
        }
        return Joint(cuttings=new_cuttings, ticket=JointTicket(path=ticket_path),
                     jointAccessories=joint.jointAccessories)

    # -- Free house joints (12 separate joints) ------------------------------
    # Housing cycle: Y into X, Z into Y, X into Z.
    # Each house joint is cut separately as a distinct 2-timber joint.
    # The 12 joints divide into:
    #   - 3 internal Group 1 joints ({x_pz, y_px, z_py})
    #   - 3 internal Group 2 joints ({x_mz, y_mx, z_my})
    #   - 6 crossing joints between Group 1 and Group 2, which carry the (1,1,1) diagonal escape.

    # Y timbers housed into X timbers (4 separate joints)
    #   x_pz (housing at +Z, G1):
    y_px_into_x_pz = _make_house_joint(x_pz, y_px, PY, V_1_0_m1, V_m1_0_m1, "y_px_into_x_pz")  # internal G1
    y_mx_into_x_pz = _make_house_joint(x_pz, y_mx, PY, V_1_0_m1, V_m1_0_m1, "y_mx_into_x_pz", V_m1_m1_m1)  # crossing (G2)

    #   x_mz (housing at -Z, G2):
    y_px_into_x_mz = _make_house_joint(x_mz, y_px, PY, V_1_0_1, V_m1_0_1, "y_px_into_x_mz", V_1_1_1)  # crossing (G1)
    y_mx_into_x_mz = _make_house_joint(x_mz, y_mx, PY, V_1_0_1, V_m1_0_1, "y_mx_into_x_mz")  # internal G2

    # Z timbers housed into Y timbers (4 separate joints)
    #   y_px (housing at +X, G1):
    z_py_into_y_px = _make_house_joint(y_px, z_py, PZ, V_m1_1_0, V_m1_m1_0, "z_py_into_y_px")  # internal G1
    z_my_into_y_px = _make_house_joint(y_px, z_my, PZ, V_m1_1_0, V_m1_m1_0, "z_my_into_y_px", V_m1_m1_m1)  # crossing (G2)

    #   y_mx (housing at -X, G2):
    z_py_into_y_mx = _make_house_joint(y_mx, z_py, PZ, V_1_1_0, V_1_m1_0, "z_py_into_y_mx", V_1_1_1)  # crossing (G1)
    z_my_into_y_mx = _make_house_joint(y_mx, z_my, PZ, V_1_1_0, V_1_m1_0, "z_my_into_y_mx")  # internal G2

    # X timbers housed into Z timbers (4 separate joints)
    #   z_py (housing at +Y, G1):
    x_pz_into_z_py = _make_house_joint(z_py, x_pz, PX, V_0_m1_1, V_0_m1_m1, "x_pz_into_z_py")  # internal G1
    x_mz_into_z_py = _make_house_joint(z_py, x_mz, PX, V_0_m1_1, V_0_m1_m1, "x_mz_into_z_py", V_m1_m1_m1)  # crossing (G2)

    #   z_my (housing at -Y, G2):
    x_pz_into_z_my = _make_house_joint(z_my, x_pz, PX, V_0_1_1, V_0_1_m1, "x_pz_into_z_my", V_1_1_1)  # crossing (G1)
    x_mz_into_z_my = _make_house_joint(z_my, x_mz, PX, V_0_1_1, V_0_1_m1, "x_mz_into_z_my")  # internal G2

    return Frame.from_joints(
        [
            y_px_into_x_pz, y_mx_into_x_pz,
            y_px_into_x_mz, y_mx_into_x_mz,
            z_py_into_y_px, z_my_into_y_px,
            z_py_into_y_mx, z_my_into_y_mx,
            x_pz_into_z_py, x_mz_into_z_py,
            x_pz_into_z_my, x_mz_into_z_my,
        ],
        name="luban_lock_1",
    )
