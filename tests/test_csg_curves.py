import math

import numpy as np
import pytest

from kumiki.csg.curves import cylindrical_patches
from kumiki.csg.pathcsg import ArcSegment, FancyPath, PathExtrusion
from kumiki.rule import create_v2


def test_oblique_section_preserves_clockwise_profile_and_its_bulge():
    profile = FancyPath([ArcSegment(create_v2(2, 0), 1, math.pi, -math.pi),
                         ArcSegment(create_v2(2, 0), 1, 0, -math.pi)])
    solid = PathExtrusion(profile, start_distance=-1, end_distance=1)
    first, second = cylindrical_patches(solid)
    section = first.section(np.zeros(3), np.array([0., 1., 1.]))
    assert section is not None
    assert section.point(math.pi / 2) == pytest.approx([2, 1, -1])
    assert section.plane_crossings(np.array([2., 0., 0.]), np.array([1., 0., 0.])) == pytest.approx([math.pi / 2])
    assert second.section(np.zeros(3), np.array([0., 1., 0.])) is None
    for normal, point in solid.get_convex_hull().require_faces():
        assert np.dot(np.array(normal).ravel(), [2, 1, 0]) <= np.dot(np.array(normal).ravel(), np.array(point).ravel()) + 1e-10
