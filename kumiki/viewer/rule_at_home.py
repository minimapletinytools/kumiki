"""Plain-float math for the live viewer's hot path, standing in for rule.py there and only there.

The math types here exist only to be used over rule.py's on the hot path inside live viewer code:
picking runs on every hover, over every feature of a timber, and rule.py's V3 -- a Matrix -- costs
far more per operation than floats in a tuple. Everywhere else, use rule.py. Convert at the edges:
Float3.of(a V3 or a list from the wire), and .v3() back.

A Float3 is a tuple, so it goes to the viewer as a JSON array as it is.
"""

import math
from typing import NamedTuple, Optional, Sequence, Tuple

from ..rule import V3, create_v3


class Float3(NamedTuple):
    """A point or direction as three floats."""
    x: float
    y: float
    z: float

    @staticmethod
    def of(vector) -> 'Float3':
        """From a V3 (a 3x1 Matrix) or any three numbers, such as a list off the wire."""
        try:
            return Float3(float(vector[0, 0]), float(vector[1, 0]), float(vector[2, 0]))
        except (TypeError, IndexError, KeyError):
            return Float3(float(vector[0]), float(vector[1]), float(vector[2]))

    def v3(self) -> V3:
        return create_v3(self.x, self.y, self.z)

    def __add__(self, other: Sequence[float]) -> 'Float3':
        return Float3(self.x + other[0], self.y + other[1], self.z + other[2])

    def __sub__(self, other: Sequence[float]) -> 'Float3':
        return Float3(self.x - other[0], self.y - other[1], self.z - other[2])

    def __mul__(self, factor: float) -> 'Float3':  # type: ignore[override]
        return Float3(self.x * factor, self.y * factor, self.z * factor)

    def __neg__(self) -> 'Float3':
        return Float3(-self.x, -self.y, -self.z)

    def dot(self, other: Sequence[float]) -> float:
        return self.x * other[0] + self.y * other[1] + self.z * other[2]

    def cross(self, other: Sequence[float]) -> 'Float3':
        return Float3(self.y * other[2] - self.z * other[1],
                      self.z * other[0] - self.x * other[2],
                      self.x * other[1] - self.y * other[0])

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def dist(self, other: Sequence[float]) -> float:
        return (self - other).length()

    def unit(self) -> Optional['Float3']:
        """This direction at length one, or None when it has no length."""
        length = self.length()
        return None if length < 1e-12 else self * (1.0 / length)

    def across(self, direction: 'Float3') -> 'Float3':
        """The part of this square to a unit *direction*: what it is once flattened along it."""
        return self - direction * self.dot(direction)


#: A rotation as three rows, for turning world vectors into a timber's local space and back.
Rows3 = Tuple[Float3, Float3, Float3]
