"""Where a feature is on its cut timber (kumiki/csg/feature_extent.py): cropped once, by its nature."""

import numpy as np
import pytest

from kumiki import *
from kumiki.csg.cutcsg import Cylinder, CylinderAxisFeature, Difference, RectangularPrism, csg_children
from kumiki.csg.feature_extent import extents_of


def _box(x, y, z):
    """An axis-aligned box from (low, high) along each axis, in the timber's local space."""
    return RectangularPrism(size=create_v2(x[1] - x[0], y[1] - y[0]),
                            transform=Transform(position=create_v3((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, 0),
                                                orientation=Transform.identity().orientation),
                            start_distance=scalar(z[0]), end_distance=scalar(z[1]))


@pytest.fixture(scope="module")
def notched():
    """A rough timber, 4 x 6 perfect within, 100 long, oversawn 1 on its right; a notch takes x > 0
    out of its top half (z 50..100), and a bore runs across it at z 25."""
    timber = Timber(length=scalar(100), size=create_v2(scalar(4), scalar(6)), transform=Transform.identity(),
                    rough_half_sizes=(create_v2(scalar(3), scalar(2)), create_v2(scalar(3), scalar(3))))
    bore = Cylinder(axis_direction=create_v3(0, 1, 0), radius=scalar(0.5), position=create_v3(0, 0, 25),
                    start_distance=scalar(-10), end_distance=scalar(10),
                    extra_features=(CylinderAxisFeature(name="axis"),))
    cut = CutTimber(timber, cuts=[Cutting(timber=timber, negative_csg=_box((0, 10), (-10, 10), (50, 200))),
                                  Cutting(timber=timber, negative_csg=bore)])
    root = cut.render_timber_with_cuts_csg_local()
    return root, timber, extents_of(root, timber)


def _named(node, name):
    return next(f for f in node.get_declared_features() if f.name == name)


def _nodes(node):
    yield node
    for child in csg_children(node):
        yield from _nodes(child)


def _body(root):
    return root.base if isinstance(root, Difference) else root


def test_a_real_face_is_the_part_of_it_left_on_the_surface(notched):
    # rptw.left (x = -2) runs the whole length; the rough top half of the right is notched away.
    root, _, extents = notched
    body = _body(root)
    left = extents.of(_named(body, "rptw.left"), body)
    assert pytest.approx(float(left.anchor()[2]), abs=1e-6) == 50.0
    right = extents.of(_named(body, "rough.right"), body)  # x = 3: only its bottom half is left
    assert pytest.approx(float(right.anchor()[2]), abs=1e-6) == 25.0


def test_a_perfect_reference_is_the_plane_cut_to_the_solid(notched):
    # ptw.right (x = 2) is inside the rough stock below the notch, and gone above it.
    root, _, extents = notched
    body = _body(root)
    ends = [float(point[2]) for segment in extents.of(_named(body, "ptw.right"), body).outline() for point in segment]
    assert (min(ends), max(ends)) == pytest.approx((0.0, 50.0), abs=1e-6)


def test_an_axis_in_a_void_keeps_its_own_length(notched):
    root, _, extents = notched
    bore = next(node for node in _nodes(root) if isinstance(node, Cylinder))
    (start, end), = extents.of(_named(bore, "axis"), bore).outline()
    assert abs(float(end[1]) - float(start[1])) == pytest.approx(20.0)


def test_each_is_worked_out_once_per_tree(notched):
    root, timber, extents = notched
    body = _body(root)
    assert extents_of(root, timber) is extents
    assert extents.of(_named(body, "rptw.left"), body) is extents.of(_named(body, "rptw.left"), body)
