"""Plain-float math for the viewer's picking hot path, in place of rule.py's V3.

Use rule.py everywhere else. Convert at the edges: Float3.of(V3 or list), and .v3().
"""

import math
from typing import List, NamedTuple, Optional, Sequence, Tuple

from ..rule import V3, create_v3

#: A point or direction as a list of three floats, the way the viewer sends and takes one.
FloatList3 = List[float]


class Float3(NamedTuple):
    """A point or direction as three floats (a tuple, so JSON-serializable)."""
    x: float
    y: float
    z: float

    @staticmethod
    def of(vector) -> 'Float3':
        """Return a Float3 from a V3 or any three numbers."""
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
        """Return this direction normalized, or None if zero."""
        length = self.length()
        return None if length < 1e-12 else self * (1.0 / length)

    def across(self, direction: 'Float3') -> 'Float3':
        """Return the component square to unit `direction`."""
        return self - direction * self.dot(direction)


#: A rotation as three rows, for turning world vectors into a timber's local space and back.
Rows3 = Tuple[Float3, Float3, Float3]
