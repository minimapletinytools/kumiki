"""The caches picking leans on give the answers they would without them."""

from kumiki.csg.cutcsg import Difference, PointTests, RectangularPrism
from kumiki.csg.edges_on_csg import convex_hull
from kumiki.rule import Matrix, Transform, create_v3, scalar


def _notched_block() -> Difference:
    base = RectangularPrism(size=Matrix([scalar(10), scalar(10)]), transform=Transform.identity(),
                            start_distance=0, end_distance=10)
    notch = RectangularPrism(size=Matrix([scalar(2), scalar(2)]), transform=Transform.identity(),
                             start_distance=2, end_distance=8)
    return Difference(base, [notch])


def test_convex_hull_and_declared_features_are_kept():
    block = _notched_block()
    assert convex_hull(block.base) is convex_hull(block.base)
    first, second = block.base.get_declared_features(), block.base.get_declared_features()
    assert first == second and first is not second
    assert all(a is b for a, b in zip(first, second))


def test_point_tests_answer_alike_inside_the_memo():
    block = _notched_block()
    points = [create_v3(4, 4, 5), create_v3(0, 0, 5), create_v3(1, 0, 5), create_v3(5, 5, 5), create_v3(1, 1, 9)]
    plain = [(block.contains_point(p), block.is_point_on_boundary(p), block.get_outward_normal(p)) for p in points]
    tests = PointTests()
    for _ in range(2):
        kept = [(tests.contains(block, p), tests.on_boundary(block, p), tests.outward_normal(block, p))
                for p in points]
        assert kept == plain
