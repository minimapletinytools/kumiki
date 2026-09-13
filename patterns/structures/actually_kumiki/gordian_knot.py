"""Gordian's Knot puzzle structure with cutouts.

Six interlocking 5×7×1 pieces arranged around the origin:
  - Z length axis: YELLOW (-x) and RED (+x)
  - X length axis: PURPLE (-y) and GREEN (+y)
  - Y length axis: BLUE (-z) and ORANGE (+z)

Each piece has outer dimensions 5×7×1:
  - Length: 7 units (along piece's length axis)
  - Width: 5 units (along piece's width axis)
  - Thickness: 1 unit (along piece's thickness/offset axis)

Cutouts (7 rows × 5 cols, 'X' = solid material, ' ' = cutout hole):
-------------------------------------------------------------------
RED:
  XXXXX
  X X X
  X X  
  X XXX
    X  
  X X X
  XXXXX

YELLOW:
  XXXXX
  X X X
  X    
  X X X
  X X X
  X X X
  XXXXX

PURPLE:
  XXXXX
  X X X
  X   X
  X   X
      X
  X X X
  XXXXX

GREEN:
  XXXXX
  X X X
  X X X
  X X X
  X X X
  X X X
  XXXXX

ORANGE:
  XXXXX
  X X X
  X   X
  X   X
  X    
  X X X
  XXXXX

BLUE:
  XXXXX
  X X X
  X    
  X   X
  X  XX
  X X X
  XXXXX
"""

from kumiki import *
from kumiki.cutcsg import RectangularPrism, SolidUnion


# --- Dimensions -----------------------------------------------------------

length = inches(7)
width = inches(5)
thickness = inches(1)
gap = inches(1)

piece_size = create_v2(width, thickness)
half_len = length / scalar(2)
offset = (gap + thickness) / scalar(2)  # 1.0 inch offset from origin


# --- Cutout Grids (7 rows × 5 cols) ---------------------------------------

RED_GRID = [
    "XXXXX",
    "X X X",
    "X X  ",
    "X XXX",
    "  X  ",
    "X X X",
    "XXXXX",
]

YELLOW_GRID = [
    "XXXXX",
    "X X X",
    "X    ",
    "X X X",
    "X X X",
    "X X X",
    "XXXXX",
]

PURPLE_GRID = [
    "XXXXX",
    "X X X",
    "X   X",
    "X   X",
    "    X",
    "X X X",
    "XXXXX",
]

GREEN_GRID = [
    "XXXXX",
    "X X X",
    "X X X",
    "X X X",
    "X X X",
    "X X X",
    "XXXXX",
]

ORANGE_GRID = [
    "XXXXX",
    "X X X",
    "X   X",
    "X   X",
    "X    ",
    "X X X",
    "XXXXX",
]

BLUE_GRID = [
    "XXXXX",
    "X X X",
    "X    ",
    "X   X",
    "X  XX",
    "X X X",
    "XXXXX",
]


def _make_cuts_for_grid(grid: list[str]) -> SolidUnion | None:
    """Generate negative CSG rectangular prisms for empty cells in the 7×5 grid."""
    prisms = []
    unit_size = create_v2(inches(1), inches(1))
    for r in range(7):
        for c in range(5):
            if grid[r][c] == " ":
                # In timber local coordinates:
                # local X is width: c=0 is +2, c=4 is -2 (center = 2 - c)
                # local Z is length: r=0 is [6, 7], r=6 is [0, 1] (start = 6 - r)
                # local Y is thickness: [-0.5, +0.5]
                x_center = inches(2 - c)
                z_start = inches(6 - r)
                p = RectangularPrism(
                    size=unit_size,
                    transform=Transform(
                        position=create_v3(x_center, scalar(0), z_start),
                        orientation=Orientation.identity(),
                    ),
                    start_distance=scalar(0),
                    end_distance=inches(1),
                )
                prisms.append(p)
    return SolidUnion(prisms) if prisms else None


def example() -> Frame:
    # Six timbers in right-handed arrangement:
    # 1. YELLOW (-x) & RED (+x): length along +Z, width along +Y, thickness along X
    # 2. PURPLE (-y) & GREEN (+y): length along +X, width along +Z, thickness along Y
    # 3. BLUE (-z) & ORANGE (+z): length along +Y, width along +X, thickness along Z
    timbers_spec = [
        ("yellow", YELLOW_GRID, create_v3(scalar(0), scalar(0), scalar(1)), create_v3(scalar(0), scalar(1), scalar(0)), create_v3(-offset, scalar(0), -half_len)),
        ("red",    RED_GRID,    create_v3(scalar(0), scalar(0), scalar(1)), create_v3(scalar(0), scalar(1), scalar(0)), create_v3(offset, scalar(0), -half_len)),
        ("purple", PURPLE_GRID, create_v3(scalar(1), scalar(0), scalar(0)), create_v3(scalar(0), scalar(0), scalar(1)), create_v3(-half_len, -offset, scalar(0))),
        ("green",  GREEN_GRID,  create_v3(scalar(1), scalar(0), scalar(0)), create_v3(scalar(0), scalar(0), scalar(1)), create_v3(-half_len, offset, scalar(0))),
        ("blue",   BLUE_GRID,   create_v3(scalar(0), scalar(1), scalar(0)), create_v3(scalar(1), scalar(0), scalar(0)), create_v3(scalar(0), -half_len, -offset)),
        ("orange", ORANGE_GRID, create_v3(scalar(0), scalar(1), scalar(0)), create_v3(scalar(1), scalar(0), scalar(0)), create_v3(scalar(0), -half_len, offset)),
    ]

    cut_timbers = []
    for name, grid, ldir, wdir, bpos in timbers_spec:
        timber = create_timber(
            length=length,
            size=piece_size,
            bottom_position=bpos,
            length_direction=ldir,
            width_direction=wdir,
            ticket=TimberTicket(path=name, tags=(GenericTag(name),)),
        )
        neg_csg = _make_cuts_for_grid(grid)
        cuts = [Cutting(timber=timber, negative_csg=neg_csg)] if neg_csg else []
        cut_timbers.append(CutTimber(timber=timber, cuts=cuts))

    return Frame(
        cut_timbers=cut_timbers,
        name="gordian_knot",
    )
