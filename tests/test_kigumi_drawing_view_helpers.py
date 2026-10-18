"""Where a drawing's views look from (kumiki/drawings/kigumi_drawing_view_helpers.py)."""

import pytest

from kumiki.drawings.kigumi_drawing_view_helpers import OrientedBox, orient_by_search, orient_from_box


class TestOrientationStrategies:
    """How the preview decides where to look from. Two strategies, one seam."""

    def _box(self, axes, half_sizes, centre=(0.0, 0.0, 0.0)):
        return OrientedBox(centre=list(centre), axes=axes, half_sizes=half_sizes)

    WORLD = ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0])

    def test_a_box_reaches_furthest_along_its_own_axes(self):
        box = self._box(self.WORLD, (1.2, 0.05, 0.1))

        assert box.reach([1.0, 0.0, 0.0]) == 1.2
        assert box.reach([0.0, 0.0, 1.0]) == 0.1

    def test_a_tilted_box_reaches_along_its_own_axes_not_the_worlds(self):
        # The whole reason an oriented box exists: a brace lying at forty-five
        # degrees is not as big as the world box it sits in.
        diagonal = 2 ** -0.5
        box = self._box(([diagonal, 0.0, diagonal], [0.0, 1.0, 0.0], [-diagonal, 0.0, diagonal]),
                        (1.0, 0.05, 0.05))

        assert box.reach([diagonal, 0.0, diagonal]) == pytest.approx(1.0, abs=1e-9)

    def test_the_silhouette_is_smallest_end_on(self):
        box = self._box(self.WORLD, (1.2, 0.05, 0.1))

        assert box.silhouette_area([1.0, 0.0, 0.0]) < box.silhouette_area([0.0, 1.0, 0.0])

    def test_the_search_keeps_the_world_upright_when_asked(self):
        # Several timbers: which way is up is part of what the preview says, so
        # it is not traded away for a slightly bigger picture.
        box = self._box(self.WORLD, (1.2, 0.05, 0.1))

        frame = orient_by_search(box, 0.707, preserve_up=True)

        assert frame.up[2] > 0.5

    def test_the_search_may_roll_the_view_when_not(self):
        # A long piece in a tall viewport fits far better on its side, which is
        # worth having as an option even though an assembly should not take it.
        box = self._box(self.WORLD, (1.2, 0.05, 0.1))

        upright = orient_by_search(box, 0.5, preserve_up=True)
        rolled = orient_by_search(box, 0.5, preserve_up=False)

        assert rolled.up[2] < upright.up[2]

    def test_the_search_never_looks_down_the_length(self):
        box = self._box(self.WORLD, (1.2, 0.05, 0.1))

        frame = orient_by_search(box, 0.707)

        assert abs(frame.look[0]) < 0.95

    def test_a_piece_is_seen_the_same_way_wherever_it_lies(self):
        # orient_from_box works in the box's own frame, so a post, a beam and a
        # brace all get the same view of themselves.
        diagonal = 2 ** -0.5
        boxes = [
            self._box(([0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, -1.0, 0.0]), (1.2, 0.05, 0.1)),
            self._box(([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]), (1.2, 0.05, 0.1)),
            self._box(([diagonal, 0.0, diagonal], [0.0, 1.0, 0.0], [-diagonal, 0.0, diagonal]),
                      (1.2, 0.05, 0.1)),
        ]

        angles = []
        for box in boxes:
            frame = orient_from_box(box, 0.707)
            along = box.axes[0]
            angles.append(abs(sum(frame.look[i] * along[i] for i in range(3))))

        assert angles[0] == pytest.approx(angles[1], abs=1e-9)
        assert angles[1] == pytest.approx(angles[2], abs=1e-9)

    def test_a_piece_stands_up_in_a_tall_viewport_and_lies_down_in_a_wide_one(self):
        box = self._box(self.WORLD, (1.2, 0.05, 0.1))

        tall = orient_from_box(box, 0.5)
        wide = orient_from_box(box, 2.0)

        # How much of the length runs up the screen.
        assert abs(tall.up[0]) > abs(wide.up[0])
