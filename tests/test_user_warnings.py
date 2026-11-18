"""kumiki's warnings point at the line in the user's code that led to them."""

import warnings

from kumiki.user_warnings import warn_user
from kumiki.csg.triangles import triangulate_cutcsg


def test_a_warning_is_located_at_the_first_line_outside_kumiki():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_user("from the test itself")

    assert caught[0].filename == __file__


def test_one_raised_deep_in_kumiki_still_points_here():
    from kumiki.rule import create_v3, scalar, Transform
    from kumiki.csg.cutcsg import RectangularPrism

    prism = RectangularPrism(size=create_v3(scalar(1), scalar(1), scalar(0))[:2, :], transform=Transform.identity(),
                             start_distance=scalar(1), end_distance=scalar(1))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        triangulate_cutcsg(prism)

    said = [w for w in caught if "Skipping a RectangularPrism" in str(w.message)]
    assert said and said[0].filename == __file__
