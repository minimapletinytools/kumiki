"""Carriers: the planes, lines, points and barrels a CSG's features lie on, and their unknowns.

A primitive names its carriers (`CutCSG.carriers`), and each feature names the carriers that
produce it (`CSGFeature.solve_recipe`). Rows over the unknowns are in csg/solve_recipe.py.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Dict, List, Mapping, Optional, Sequence, Tuple, Type, Union

from ..geometry import Line, Plane, planes_are_coincident
from ..rule import Numeric, V3

if TYPE_CHECKING:
    from .cutcsg import CutCSG, FeatureKey


class PlaneCoord(Enum):
    """A plane's unknowns: its offset, and tilts toward its perpendicular_axes."""
    OFFSET = 0
    TILT_1 = 1
    TILT_2 = 2


class LineCoord(Enum):
    """A line's unknowns: shifts along its perpendicular_axes, and turns toward them about `line.point`."""
    SHIFT_1 = 0
    SHIFT_2 = 1
    TURN_1 = 2
    TURN_2 = 3


class PointCoord(Enum):
    X = 0
    Y = 1
    Z = 2


class BarrelCoord(Enum):
    RADIUS = 0


Coord = Union[PlaneCoord, LineCoord, PointCoord, BarrelCoord]


@dataclass(frozen=True)
class CarrierPlane:
    plane: Plane

    COORDS: ClassVar[Type[PlaneCoord]] = PlaneCoord


@dataclass(frozen=True)
class CarrierLine:
    line: Line

    COORDS: ClassVar[Type[LineCoord]] = LineCoord


@dataclass(frozen=True)
class CarrierPoint:
    point: V3

    COORDS: ClassVar[Type[PointCoord]] = PointCoord


@dataclass(frozen=True)
class CarrierBarrel:
    """A cylinder's barrel around the CarrierLine at `axis` on the same primitive."""
    axis: 'FeatureKey'
    radius: Numeric

    COORDS: ClassVar[Type[BarrelCoord]] = BarrelCoord


Carrier = Union[CarrierPlane, CarrierLine, CarrierPoint, CarrierBarrel]


@dataclass(frozen=True, eq=False)
class CarrierRef:
    """One carrier of one primitive: the primitive, compared by identity, and the carrier's key."""
    owner: 'CutCSG'
    local: 'FeatureKey'

    def carrier(self) -> Carrier:
        return self.owner.carriers()[self.local]

    def __eq__(self, other) -> bool:
        return isinstance(other, CarrierRef) and self.owner is other.owner and self.local == other.local

    def __hash__(self) -> int:
        return hash((id(self.owner), self.local))


@dataclass(frozen=True)
class Midplane:
    """The plane midway between two planar carriers, e.g. a timber's centerplane between two opposite faces."""
    front: CarrierRef
    back: CarrierRef


# A carrier, or a plane made from carriers.
RecipePart = Union[CarrierRef, Midplane]

# List of references to the carriers producing the feature in question, which is the carrier
# itself for non-derived features.
Recipe = Tuple[RecipePart, ...]

# One unknown: a solving carrier and one of its COORDS.
Column = Tuple[CarrierRef, Coord]
Row = Dict[Column, float]


def merge_coincident_planes(carriers: Dict[CarrierRef, Carrier],
                            rank: Optional[Mapping[CarrierRef, int]] = None) -> Dict[CarrierRef, CarrierRef]:
    """Map each carrier to its solving carrier: coincident planes (facing either way) share the one ranked
    lowest in `rank` (unranked count as 0), else the first; others map to themselves."""
    canonical: Dict[CarrierRef, CarrierRef] = {}
    groups: List[Tuple[Plane, List[CarrierRef]]] = []
    for ref, carrier in carriers.items():
        canonical[ref] = ref
        if not isinstance(carrier, CarrierPlane):
            continue
        same = next((group for plane, group in groups if planes_are_coincident(plane, carrier.plane)), None)
        if same is None:
            groups.append((carrier.plane, [ref]))
        else:
            same.append(ref)
    for _, group in groups:
        best = min(group, key=lambda ref: (rank or {}).get(ref, 0))
        for ref in group:
            canonical[ref] = best
    return canonical


class CarrierMap:
    """Every primitive carrier mapped to the solving carrier whose columns it uses."""

    def __init__(self, carriers: Dict[CarrierRef, Carrier], canonical: Dict[CarrierRef, CarrierRef]):
        self._carriers = carriers
        self._canonical = canonical

    @staticmethod
    def union(maps: Sequence['CarrierMap']) -> 'CarrierMap':
        """Return one map combining `maps`, which must cover distinct primitives."""
        carriers: Dict[CarrierRef, Carrier] = {}
        canonical: Dict[CarrierRef, CarrierRef] = {}
        for one in maps:
            carriers.update(one._carriers)
            canonical.update(one._canonical)
        return CarrierMap(carriers, canonical)

    def canonical(self, ref: CarrierRef) -> CarrierRef:
        return self._canonical[ref]

    def carrier(self, ref: CarrierRef) -> Carrier:
        """Return the geometry of `ref`'s solving carrier."""
        return self._carriers[self._canonical[ref]]

    def solving_carriers(self) -> List[CarrierRef]:
        return list(dict.fromkeys(self._canonical.values()))

    def carrier_rows(self, ref: CarrierRef) -> List[Row]:
        """Return one unit row per unknown of `ref`'s solving carrier."""
        column = self.canonical(ref)
        coords: List[Coord] = list(type(self.carrier(ref)).COORDS)
        return [{(column, coord): 1.0} for coord in coords]

    def unknowns(self) -> List[Row]:
        """Return one unit row per unknown of every solving carrier."""
        return [row for ref in self.solving_carriers() for row in self.carrier_rows(ref)]

    def __contains__(self, ref: CarrierRef) -> bool:
        return ref in self._canonical
