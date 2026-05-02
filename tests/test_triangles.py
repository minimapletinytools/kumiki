import pytest
from sympy import Integer, Rational

from kumiki import (
    ConvexPolygonExtrusion,
    Cylinder,
    Difference,
    HalfSpace,
    Orientation,
    RectangularPrism,
    SolidUnion,
    Transform,
    TRIANGLES_HALF_SPACE_INFINITE_EXTENT,
    TRIANGLES_PRISM_INFINITE_EXTENT,
    create_v2,
    create_v3,
    raw_raycast_first,
    triangulate_cutcsg,
)


class TestTriangles:
    def test_triangulate_rectangular_prism_bounds(self):
        prism = RectangularPrism(
            size=create_v2(Rational(2), Rational(4)),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(6),
        )

        triangle_mesh = triangulate_cutcsg(prism)

        assert triangle_mesh.mesh.is_watertight
        bounds = triangle_mesh.mesh.bounds
        assert pytest.approx(bounds[0][0], abs=1e-6) == -1.0
        assert pytest.approx(bounds[1][0], abs=1e-6) == 1.0
        assert pytest.approx(bounds[0][1], abs=1e-6) == -2.0
        assert pytest.approx(bounds[1][1], abs=1e-6) == 2.0
        assert pytest.approx(bounds[0][2], abs=1e-6) == 0.0
        assert pytest.approx(bounds[1][2], abs=1e-6) == 6.0

    def test_triangulate_infinite_prism_uses_fake_extent(self):
        prism = RectangularPrism(
            size=create_v2(Rational(2), Rational(2)),
            transform=Transform.identity(),
            start_distance=None,
            end_distance=Integer(5),
        )

        bounds = triangulate_cutcsg(prism).mesh.bounds

        assert pytest.approx(bounds[0][2], abs=1e-6) == -TRIANGLES_PRISM_INFINITE_EXTENT
        assert pytest.approx(bounds[1][2], abs=1e-6) == 5.0

    def test_triangulate_half_space_uses_larger_fake_extent(self):
        half_space = HalfSpace(
            normal=create_v3(Integer(0), Integer(0), Integer(1)),
            offset=Integer(3),
        )

        bounds = triangulate_cutcsg(half_space).mesh.bounds

        assert pytest.approx(bounds[0][2], abs=1e-6) == 3.0
        assert pytest.approx(bounds[1][2], abs=1e-6) == 3.0 + TRIANGLES_HALF_SPACE_INFINITE_EXTENT
        assert pytest.approx(bounds[0][0], abs=1e-6) == -TRIANGLES_HALF_SPACE_INFINITE_EXTENT
        assert pytest.approx(bounds[1][0], abs=1e-6) == TRIANGLES_HALF_SPACE_INFINITE_EXTENT

    def test_triangulate_convex_polygon_extrusion_bounds(self):
        extrusion = ConvexPolygonExtrusion(
            points=[
                create_v2(Integer(0), Integer(0)),
                create_v2(Integer(2), Integer(0)),
                create_v2(Integer(1), Integer(2)),
            ],
            transform=Transform.identity(),
            start_distance=Integer(1),
            end_distance=Integer(4),
        )

        triangle_mesh = triangulate_cutcsg(extrusion)

        assert triangle_mesh.mesh.is_watertight
        bounds = triangle_mesh.mesh.bounds
        assert pytest.approx(bounds[0][0], abs=1e-6) == 0.0
        assert pytest.approx(bounds[1][0], abs=1e-6) == 2.0
        assert pytest.approx(bounds[0][2], abs=1e-6) == 1.0
        assert pytest.approx(bounds[1][2], abs=1e-6) == 4.0

    def test_triangulate_difference_reduces_volume(self):
        base = RectangularPrism(
            size=create_v2(Rational(4), Rational(4)),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(4),
        )
        subtract = Cylinder(
            axis_direction=create_v3(Integer(0), Integer(0), Integer(1)),
            radius=Rational(1),
            position=create_v3(Integer(0), Integer(0), Integer(0)),
            start_distance=Integer(0),
            end_distance=Integer(4),
        )

        mesh = triangulate_cutcsg(Difference(base=base, subtract=[subtract])).mesh

        assert mesh.is_watertight
        assert mesh.volume > 0
        assert mesh.volume < 64.0

    def test_triangulate_union_grows_volume(self):
        prism_a = RectangularPrism(
            size=create_v2(Rational(2), Rational(2)),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(2),
        )
        prism_b = RectangularPrism(
            size=create_v2(Rational(2), Rational(2)),
            transform=Transform(
                position=create_v3(Rational(1), Integer(0), Integer(0)),
                orientation=Orientation.identity(),
            ),
            start_distance=Integer(0),
            end_distance=Integer(2),
        )

        mesh = triangulate_cutcsg(SolidUnion(children=[prism_a, prism_b])).mesh

        assert mesh.is_watertight
        assert mesh.volume > 8.0

    def test_raw_raycast_first_hits_top_face(self):
        prism = RectangularPrism(
            size=create_v2(Rational(2), Rational(2)),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(2),
        )

        hit = raw_raycast_first(
            prism,
            origin=create_v3(Integer(0), Integer(0), Integer(5)),
            direction=create_v3(Integer(0), Integer(0), Integer(-1)),
        )

        assert hit is not None
        assert hit.position == (0.0, 0.0, 2.0)
        assert hit.normal == (0.0, 0.0, 1.0)
        assert pytest.approx(hit.distance, abs=1e-6) == 3.0

    def test_raw_raycast_first_miss_returns_none(self):
        prism = RectangularPrism(
            size=create_v2(Rational(2), Rational(2)),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(2),
        )

        hit = raw_raycast_first(
            prism,
            origin=create_v3(Integer(5), Integer(5), Integer(5)),
            direction=create_v3(Integer(1), Integer(0), Integer(0)),
        )

        assert hit is None