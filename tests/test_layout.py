"""Where a drawing's viewports land on the page, and what tells them apart.

Three things are pinned. The arithmetic -- a tree of subdivisions resolving to
the same rects the hand-computed tables used to hold, which is what makes the
change from one to the other provably nothing. The sizing: shares of what is
left, lengths in page units, and the order the two are taken in. And the
identity rule -- a viewport is where it is, a label is a label, and a viewport
is compared by object rather than by value.
"""

import pytest

from kumiki.drawing import (Drawing, Length, Measure, Page, Portion, Share,
                            SplitDirection, Subdivision, Viewport, columns,
                            covering_page, rows)
from kumiki.identity import (FeatureRef, ResolvedTimberPath, SingleFeaturePath,
                             TimberPath, ViewportId)
from kumiki.layout import resolve_drawing, resolve_viewports
from kumiki.rule import mm

A3 = Page(0.420, 0.297)


def _view(label=None):
    return Viewport(label=label)


def _rects(tree, page=A3):
    return {str(placed.id): tuple(round(value, 9) for value in placed.rect)
            for placed in resolve_viewports([tree], page)}


class TestTheLayoutsThatShip:
    """The trees reproduce the fraction tables they replaced, value for value."""

    def test_the_shop_drawing_is_four_rows_beside_a_preview(self):
        # Was _LONG_FACE_RECTS in kigumi/runner.py: front, right, back, left
        # down the left half, a full-height preview on the right.
        tree = covering_page(columns(
            rows(_view("Front"), _view("Right"), _view("Back"), _view("Left")),
            _view("Preview"),
        ))

        assert _rects(tree) == {
            "0.0.0": (0.0, 0.0, 0.5, 0.25),
            "0.0.1": (0.0, 0.25, 0.5, 0.25),
            "0.0.2": (0.0, 0.5, 0.5, 0.25),
            "0.0.3": (0.0, 0.75, 0.5, 0.25),
            "0.1": (0.5, 0.0, 0.5, 1.0),
        }

    def test_the_quadrants_are_two_rows_of_two(self):
        # Was _SELECTION_QUADRANTS and _DEBUG_DRAWING_RECTS, which were equal.
        tree = covering_page(rows(
            columns(_view("Front"), _view("Top")),
            columns(_view("Right"), _view("Preview")),
        ))

        assert _rects(tree) == {
            "0.0.0": (0.0, 0.0, 0.5, 0.5),
            "0.0.1": (0.5, 0.0, 0.5, 0.5),
            "0.1.0": (0.0, 0.5, 0.5, 0.5),
            "0.1.1": (0.5, 0.5, 0.5, 0.5),
        }


class TestAViewportDoesNotKnowWhereItIs:
    def test_a_viewport_carries_no_id_and_no_rect_of_its_own(self):
        inside = _view("Front")

        Drawing(name="d", page=A3, viewports=[covering_page(rows(inside))])

        assert not hasattr(inside, "id")
        assert inside.rect is None, "only a floating viewport is placed by a rect"

    def test_the_drawing_answers_where_one_is(self):
        front, preview = _view("Front"), _view("Preview")
        drawing = Drawing(name="d", page=A3,
                          viewports=[covering_page(columns(rows(front), preview))])

        assert str(drawing.id_of(front)) == "0.0.0"
        assert str(drawing.id_of(preview)) == "0.1"
        assert drawing.viewport_at(ViewportId("0.1")) is preview

    def test_a_viewport_from_another_drawing_is_not_found(self):
        stranger = _view("Front")
        drawing = Drawing(name="d", page=A3, viewports=[covering_page(rows(_view("Front")))])

        with pytest.raises(KeyError):
            drawing.id_of(stranger)

    def test_containers_are_walked_and_only_leaves_render(self):
        drawing = Drawing(name="d", page=A3, viewports=[covering_page(
            columns(rows(_view("a"), _view("b")), _view("c")))])

        assert [str(i) for i, _ in drawing.walk()] == ["0", "0.0", "0.0.0", "0.0.1", "0.1"]
        assert [str(i) for i, _ in drawing.leaves()] == ["0.0.0", "0.0.1", "0.1"]
        # What renders is what the wire gets: containers draw nothing themselves.
        assert [str(p.id) for p in resolve_drawing(drawing)] == ["0.0.0", "0.0.1", "0.1"]


class TestViewportsAreComparedByObject:
    def test_two_viewports_with_the_same_label_are_different_viewports(self):
        # The whole reason ids are positional: what a view IS, to a drawing, is
        # the cell it occupies. Value equality would make id_of a coin toss
        # between two cells that happen to be described alike.
        assert _view("Front") != _view("Front")

    def test_a_viewport_equals_itself(self):
        front = _view("Front")

        assert front == front

    def test_one_viewport_cannot_be_in_two_places(self):
        shared = _view("Front")

        with pytest.raises(ValueError, match="told apart by where they are"):
            Drawing(name="d", page=A3, viewports=[covering_page(rows(shared, shared))])

    def test_two_that_merely_look_alike_are_fine(self):
        drawing = Drawing(name="d", page=A3,
                          viewports=[covering_page(rows(_view("Front"), _view("Front")))])

        assert [str(i) for i, _ in drawing.leaves()] == ["0.0", "0.1"]


class TestWhereAViewportIsPlaced:
    def test_a_root_needs_a_rect(self):
        with pytest.raises(ValueError, match="floats on the page and needs a rect"):
            Drawing(name="d", page=A3, viewports=[_view("Front")])

    def test_a_viewport_inside_a_subdivision_must_not_have_one(self):
        # Its cell comes from its portion's size; a rect would say a second,
        # different thing about where it goes.
        placed_twice = Viewport(label="Front", rect=(0.0, 0.0, 0.5, 0.5))

        with pytest.raises(ValueError, match="inside a subdivision"):
            Drawing(name="d", page=A3, viewports=[covering_page(rows(placed_twice))])

    def test_a_rect_running_off_the_page_is_refused(self):
        # The viewer clamps a rect into [0, 1] without a word, so this would
        # otherwise quietly become a different rect.
        with pytest.raises(ValueError, match="runs off it"):
            Viewport(label="Front", rect=(0.8, 0.0, 0.4, 1.0))

    def test_floating_viewports_may_overlap(self):
        drawing = Drawing(name="d", page=A3, viewports=[
            Viewport(label="sheet", rect=(0.0, 0.0, 1.0, 1.0)),
            Viewport(label="inset", rect=(0.1, 0.1, 0.2, 0.2), z=5),
        ])

        assert len(resolve_drawing(drawing)) == 2


class TestSizing:
    def test_equal_shares_by_default(self):
        rects = _rects(covering_page(rows(_view(), _view(), _view(), _view())))

        assert [rect[3] for rect in rects.values()] == [0.25] * 4

    def test_shares_divide_in_proportion(self):
        tree = covering_page(columns(_view("wide").taking(Share(3)), _view("narrow")))

        assert [rect[2] for rect in _rects(tree).values()] == [0.75, 0.25]

    def test_a_length_is_page_units_and_the_shares_take_what_is_left(self):
        # A title block 40mm tall on a 297mm sheet is 40mm of it, whatever else
        # the drawing does. That is the whole point of a fixed size.
        tree = covering_page(rows(_view("plan"), _view("title").taking(Length(mm(40)))))
        heights = [rect[3] for rect in _rects(tree).values()]

        assert heights[1] * 297 == pytest.approx(40)
        assert heights[0] * 297 == pytest.approx(257)

    def test_a_length_means_the_same_printed_size_on_either_axis(self):
        # The fractions differ because the sheet is not square; the millimetres
        # do not, which is why a Length is in page units rather than fractions.
        down = covering_page(rows(_view().taking(Length(0.042)), _view()))
        across = covering_page(columns(_view().taking(Length(0.042)), _view()))

        assert list(_rects(down).values())[0][3] == pytest.approx(0.042 / 0.297)
        assert list(_rects(across).values())[0][2] == pytest.approx(0.042 / 0.420)

    def test_a_size_belongs_to_the_portion_and_not_the_viewport(self):
        # The same viewport can be half of one row and a third of another,
        # because how much room it takes is a fact about the arrangement.
        view = _view("Front")

        assert Portion(view, Share(1)).viewport is view
        assert not hasattr(view, "size")

    def test_fixed_sizes_that_do_not_fit_say_so(self):
        tree = covering_page(rows(_view().taking(Length(0.2)), _view().taking(Length(0.2))))

        with pytest.raises(ValueError, match="more fixed size than its cell has"):
            _rects(tree)

    def test_a_share_is_positive(self):
        with pytest.raises(ValueError, match="positive"):
            Share(0)

    def test_a_length_is_positive(self):
        with pytest.raises(ValueError, match="positive"):
            Length(0)


class TestNesting:
    def test_a_subdivision_inside_one_gets_a_viewport_of_its_own(self):
        # columns(rows(a, b), c) reads like the shape it makes; the container
        # that holds the rows is real, has an id, and carries no label.
        drawing = Drawing(name="d", page=A3,
                          viewports=[covering_page(columns(rows(_view("a"), _view("b")), _view("c")))])
        container = drawing.viewport_at(ViewportId("0.0"))

        assert container is not None
        assert container.label is None
        assert not container.is_leaf

    def test_a_nested_subdivision_can_state_its_size(self):
        tree = covering_page(columns(rows(_view("a"), _view("b")).taking(Share(3)), _view("c")))

        widths = [rect[2] for rect in _rects(tree).values()]
        assert widths == [0.75, 0.75, 0.25]

    def test_a_subdivision_with_no_portions_is_refused(self):
        with pytest.raises(ValueError, match="has none"):
            Subdivision(direction=SplitDirection.ROWS, portions=())


class TestGapsAndPadding:
    def test_a_gap_goes_between_children_and_not_around_them(self):
        tree = covering_page(columns(_view(), _view(), gap=0.042))
        rects = list(_rects(tree).values())

        assert rects[0][0] == 0.0
        assert rects[1][0] + rects[1][2] == pytest.approx(1.0)
        assert rects[1][0] - (rects[0][0] + rects[0][2]) == pytest.approx(0.1)

    def test_padding_insets_a_viewport_on_every_side(self):
        tree = covering_page(Viewport(label="only", padding=0.042))
        x, y, width, height = list(_rects(tree).values())[0]

        assert x == pytest.approx(0.1)
        assert width == pytest.approx(0.8)
        assert y == pytest.approx(0.042 / 0.297)

    def test_padding_that_leaves_nothing_says_so(self):
        with pytest.raises(ValueError, match="leaves nothing"):
            _rects(covering_page(Viewport(padding=0.3)))


class TestDrawingOrder:
    def test_z_decides_what_is_drawn_last(self):
        # Back to front, because the viewer draws the list forwards and picks it
        # backwards -- so the last one out is the one on top and the one a click
        # finds first.
        drawing = Drawing(name="d", page=A3, viewports=[
            Viewport(label="under", rect=(0.0, 0.0, 1.0, 1.0), z=5),
            Viewport(label="over", rect=(0.2, 0.2, 0.3, 0.3), z=9),
            Viewport(label="bottom", rect=(0.6, 0.2, 0.3, 0.3), z=1),
        ])

        assert [p.label for p in resolve_drawing(drawing)] == ["bottom", "under", "over"]

    def test_written_order_settles_a_tie(self):
        drawing = Drawing(name="d", page=A3, viewports=[
            Viewport(label="first", rect=(0.0, 0.0, 0.5, 1.0)),
            Viewport(label="second", rect=(0.1, 0.0, 0.5, 1.0)),
        ])

        assert [p.label for p in resolve_drawing(drawing)] == ["first", "second"]

    def test_z_does_not_disturb_the_ids(self):
        # Ids come from where a viewport is WRITTEN; z only says what covers what.
        drawing = Drawing(name="d", page=A3, viewports=[
            Viewport(label="a", rect=(0.0, 0.0, 0.5, 1.0), z=9),
            Viewport(label="b", rect=(0.5, 0.0, 0.5, 1.0), z=1),
        ])

        assert {str(i): v.label for i, v in drawing.walk()} == {"0": "a", "1": "b"}


class TestWhereAMeasurementIsWritten:
    """Two ways of saying it, for two different situations."""

    def _anchor(self, name):
        return SingleFeaturePath(ResolvedTimberPath("post"), FeatureRef(("cut",), name))

    def _measure(self, name="a"):
        return Measure(self._anchor(name), self._anchor("b"))

    def test_on_the_viewport_when_the_drawing_built_it(self):
        # No counting: the measurement sits on the view it is drawn in, and the
        # id it ends up under falls out of where that view is.
        front = Viewport(label="Front", measurements=[self._measure()])
        drawing = Drawing(name="d", page=A3, viewports=[
            covering_page(columns(rows(front, _view("Right")), _view("Preview")))])

        assert list(drawing.measurements_by_viewport()) == ["0.0.0"]
        assert str(drawing.id_of(front)) == "0.0.0"

    def test_by_id_when_the_layout_is_not_the_drawings(self):
        # A drawing that names only its timbers has its viewports chosen for
        # it, so there is no viewport object to hang one on.
        drawing = Drawing(name="d", timber_paths=[TimberPath("posts/fl")],
                          measurements={"0.0.1": [self._measure()]})

        assert list(drawing.measurements_by_viewport()) == ["0.0.1"]

    def test_a_viewport_with_both_gets_both(self):
        front = Viewport(label="Front", measurements=[self._measure("own")])
        drawing = Drawing(name="d", page=A3, viewports=[covering_page(rows(front))],
                          measurements={"0.0": [self._measure("keyed")]})

        assert len(drawing.measurements_by_viewport()["0.0"]) == 2

    def test_moving_a_viewport_takes_its_measurements_with_it(self):
        # The reason to write it there. Under an id, inserting a row above
        # leaves the measurement behind on whatever moved into that cell.
        front = Viewport(label="Front", measurements=[self._measure()])
        before = Drawing(name="d", page=A3, viewports=[covering_page(rows(front))])
        after = Drawing(name="d", page=A3, viewports=[covering_page(rows(_view("New"), front))])

        assert list(before.measurements_by_viewport()) == ["0.0"]
        assert list(after.measurements_by_viewport()) == ["0.1"]


class TestTheSheetDoesNotChangeTheLayout:
    def test_shares_come_out_the_same_on_any_page(self):
        # A drawing written in shares describes proportions, not a particular
        # piece of paper.
        tree = covering_page(columns(rows(_view(), _view()), _view().taking(Share(2))))

        assert _rects(tree, Page(0.420, 0.297)) == _rects(tree, Page(0.841, 0.594))

    def test_a_drawing_with_no_page_cannot_be_resolved(self):
        drawing = Drawing(name="d", viewports=[covering_page(rows(_view()))])

        with pytest.raises(ValueError, match="no page"):
            resolve_drawing(drawing)
