"""Where a drawing's views land on the page, and what they are called there.

Two things are pinned. The arithmetic -- a tree of splits resolving to the same
rects the hand-computed tables used to hold, which is what makes the change from
one to the other provably nothing. And the identity rule: a viewport is its
position, a name is a label, and the two are never the same string.
"""

import pytest

from kumiki.layout import (FloatingPane, Layout, Page, Share, Split,
                           SplitDirection, View, columns, covering_page,
                           resolve_layout, rows)

A3 = Page(0.420, 0.297)


def _rects(layout, page=A3):
    return {str(placed.id): tuple(round(value, 9) for value in placed.rect)
            for placed in resolve_layout(layout, page)}


class TestTheLayoutsThatShip:
    """The trees reproduce the fraction tables they replaced, value for value."""

    def test_the_shop_drawing_is_four_rows_beside_a_preview(self):
        # Was _LONG_FACE_RECTS in kigumi/runner.py: front, right, back, left
        # down the left half, a full-height preview on the right.
        layout = covering_page(columns(
            rows(View(role="front"), View(role="right"),
                 View(role="back"), View(role="left")),
            View(role="preview"),
        ))

        assert _rects(layout) == {
            "0.0.0": (0.0, 0.0, 0.5, 0.25),
            "0.0.1": (0.0, 0.25, 0.5, 0.25),
            "0.0.2": (0.0, 0.5, 0.5, 0.25),
            "0.0.3": (0.0, 0.75, 0.5, 0.25),
            "0.1": (0.5, 0.0, 0.5, 1.0),
        }

    def test_the_quadrants_are_two_rows_of_two(self):
        # Was _SELECTION_QUADRANTS and _DEBUG_DRAWING_RECTS, which were equal.
        layout = covering_page(rows(
            columns(View(role="front"), View(role="top")),
            columns(View(role="right"), View(role="preview")),
        ))

        assert _rects(layout) == {
            "0.0.0": (0.0, 0.0, 0.5, 0.5),
            "0.0.1": (0.5, 0.0, 0.5, 0.5),
            "0.1.0": (0.0, 0.5, 0.5, 0.5),
            "0.1.1": (0.5, 0.5, 0.5, 0.5),
        }


class TestIdsAreWhereAViewIs:
    def test_an_undivided_floating_pane_is_just_its_index(self):
        layout = Layout((
            FloatingPane(rect=(0.0, 0.0, 0.5, 1.0), content=View()),
            FloatingPane(rect=(0.5, 0.0, 0.5, 1.0), content=View()),
        ))

        assert [str(placed.id) for placed in resolve_layout(layout, A3)] == ["0", "1"]

    def test_nesting_adds_a_step_for_each_level(self):
        layout = covering_page(rows(View(), columns(View(), rows(View(), View()))))

        assert [str(placed.id) for placed in resolve_layout(layout, A3)] == [
            "0.0", "0.1.0", "0.1.1.0", "0.1.1.1"]

    def test_a_name_is_a_label_and_never_an_id(self):
        layout = covering_page(rows(View(name="Front"), View(name="Front")))
        placed = resolve_layout(layout, A3)

        # Two views may share a name. Nothing is ambiguous, because nothing
        # looks a view up by one.
        assert [view.name for view in placed] == ["Front", "Front"]
        assert [str(view.id) for view in placed] == ["0.0", "0.1"]

    def test_a_view_needs_no_name_at_all(self):
        assert resolve_layout(covering_page(View()), A3)[0].name is None

    def test_inserting_a_pane_renumbers_the_ones_after_it(self):
        # The honest cost of positional identity, written down rather than
        # discovered: a measurement on the second row now belongs to the pane
        # that moved into it. Adding at the END renumbers nothing.
        before = covering_page(rows(View(name="a"), View(name="b")))
        after = covering_page(rows(View(name="new"), View(name="a"), View(name="b")))

        assert {str(v.id): v.name for v in resolve_layout(before, A3)} == {
            "0.0": "a", "0.1": "b"}
        assert {str(v.id): v.name for v in resolve_layout(after, A3)} == {
            "0.0": "new", "0.1": "a", "0.2": "b"}


class TestSizing:
    def test_equal_shares_by_default(self):
        rects = _rects(covering_page(rows(View(), View(), View(), View())))

        assert [rect[3] for rect in rects.values()] == [0.25] * 4

    def test_shares_divide_in_proportion(self):
        layout = covering_page(columns(View(size=Share(3)), View(size=Share(1))))

        assert [rect[2] for rect in _rects(layout).values()] == [0.75, 0.25]

    def test_a_length_is_page_units_and_the_shares_take_what_is_left(self):
        # A title block 0.042m tall on a 0.297m sheet is a tenth of it, whatever
        # the rest of the layout does -- which is the point of a fixed size.
        layout = covering_page(rows(View(), View(size=0.0297)))
        heights = [rect[3] for rect in _rects(layout).values()]

        assert heights[1] == pytest.approx(0.1)
        assert heights[0] == pytest.approx(0.9)

    def test_a_length_means_the_same_thing_on_either_axis(self):
        # Fractions differ because the sheet is not square; the printed size
        # does not, which is the whole reason lengths are in page units.
        down = covering_page(rows(View(size=0.042), View()))
        across = covering_page(columns(View(size=0.042), View()))

        assert list(_rects(down).values())[0][3] == pytest.approx(0.042 / 0.297)
        assert list(_rects(across).values())[0][2] == pytest.approx(0.042 / 0.420)

    def test_fixed_sizes_that_do_not_fit_say_so(self):
        layout = covering_page(rows(View(size=0.2), View(size=0.2)))

        with pytest.raises(ValueError, match="more fixed size than its cell has"):
            resolve_layout(layout, A3)


class TestGapsAndPadding:
    def test_a_gap_goes_between_children_and_not_around_them(self):
        layout = covering_page(columns(View(), View(), gap=0.042))
        rects = list(_rects(layout).values())

        assert rects[0][0] == 0.0
        assert rects[1][0] + rects[1][2] == pytest.approx(1.0)
        assert rects[1][0] - (rects[0][0] + rects[0][2]) == pytest.approx(0.1)

    def test_padding_insets_a_pane_on_every_side(self):
        layout = covering_page(View(padding=0.042))
        x, y, width, height = list(_rects(layout).values())[0]

        assert x == pytest.approx(0.1)
        assert width == pytest.approx(0.8)
        assert y == pytest.approx(0.042 / 0.297)
        assert height == pytest.approx(1 - 2 * 0.042 / 0.297)

    def test_padding_that_leaves_nothing_says_so(self):
        with pytest.raises(ValueError, match="leaves nothing"):
            resolve_layout(covering_page(View(padding=0.3)), A3)


class TestFloatingPanes:
    def test_z_decides_what_is_drawn_last(self):
        # Back to front, because the viewer draws the list forwards and picks it
        # backwards -- so the last one out is the one on top and the one a click
        # finds first.
        layout = Layout((
            FloatingPane(rect=(0.0, 0.0, 1.0, 1.0), content=View(name="under"), z=5),
            FloatingPane(rect=(0.2, 0.2, 0.3, 0.3), content=View(name="over"), z=9),
            FloatingPane(rect=(0.6, 0.2, 0.3, 0.3), content=View(name="bottom"), z=1),
        ))

        assert [v.name for v in resolve_layout(layout, A3)] == ["bottom", "under", "over"]

    def test_written_order_settles_a_tie(self):
        layout = Layout((
            FloatingPane(rect=(0.0, 0.0, 0.5, 1.0), content=View(name="first")),
            FloatingPane(rect=(0.1, 0.0, 0.5, 1.0), content=View(name="second")),
        ))

        assert [v.name for v in resolve_layout(layout, A3)] == ["first", "second"]

    def test_z_does_not_disturb_the_ids(self):
        # Ids come from where a pane is WRITTEN; z only says what covers what.
        layout = Layout((
            FloatingPane(rect=(0.0, 0.0, 0.5, 1.0), content=View(name="a"), z=9),
            FloatingPane(rect=(0.5, 0.0, 0.5, 1.0), content=View(name="b"), z=1),
        ))

        assert {str(v.id): v.name for v in resolve_layout(layout, A3)} == {"0": "a", "1": "b"}

    def test_a_pane_running_off_the_page_is_refused(self):
        # The viewer clamps a rect into [0, 1] without a word, so this would
        # otherwise become a different pane silently.
        with pytest.raises(ValueError, match="runs off it"):
            FloatingPane(rect=(0.8, 0.0, 0.4, 1.0), content=View())

    def test_panes_may_overlap(self):
        layout = Layout((
            FloatingPane(rect=(0.0, 0.0, 1.0, 1.0), content=View()),
            FloatingPane(rect=(0.1, 0.1, 0.2, 0.2), content=View()),
        ))

        assert len(resolve_layout(layout, A3)) == 2


class TestRefusals:
    def test_a_split_with_no_children_is_refused(self):
        with pytest.raises(ValueError, match="has none"):
            Split(direction=SplitDirection.ROWS, children=())

    def test_a_share_is_positive(self):
        with pytest.raises(ValueError, match="positive"):
            Share(0)

    def test_a_page_has_a_size(self):
        with pytest.raises(ValueError, match="positive size"):
            Page(0.420, 0)

    def test_a_floating_pane_has_a_size(self):
        with pytest.raises(ValueError, match="positive size"):
            FloatingPane(rect=(0.0, 0.0, 0.0, 1.0), content=View())


class TestTheSheetDoesNotChangeTheLayout:
    def test_shares_come_out_the_same_on_any_page(self):
        # "As right on a small sheet as on a large one" -- a layout in shares
        # describes proportions, not a particular piece of paper.
        layout = covering_page(columns(rows(View(), View()), View(size=Share(2))))

        assert _rects(layout, Page(0.420, 0.297)) == _rects(layout, Page(0.841, 0.594))
