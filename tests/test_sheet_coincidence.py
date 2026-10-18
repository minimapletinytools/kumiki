"""What a view shows lined up needs no dimension (auto_dimensioning.coincidence_assumptions)."""

from kumiki import *
from kumiki.csg.cutcsg import OwnedFeatureHit
from kumiki.csg.dof_solver import remaining
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.drawings.auto_dimensioning import coincidence_assumptions
from kumiki.drawings.drawing import ViewAxes
from kumiki.drawings.measure_solving import DrawingSolve

# Looking along +y: x across the sheet, z up it.
FRONT = ViewAxes(look=create_v3(0, 1, 0), right=create_v3(1, 0, 0), up=create_v3(0, 0, 1))


def _beam(x, name):
    """A beam along x from `x`, 90mm square and centred on z = 0. Laid this way its top, at z = 45mm,
    is the face it calls front."""
    timber = create_timber(bottom_position=create_v3(x, 0, 0), length=m(1), size=create_v2(mm(90), mm(90)),
                           length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 1, 0),
                           ticket=TimberTicket(name))
    return CutTimber(timber, cuts=[])


def _face(cut, side):
    body = cut.render_timber_with_cuts_csg_local()
    feature = next(f for f in body.get_declared_features() if f.name.endswith(f".{side}") and f.real)
    return FeatureHandle(timber=cut.timber, hit=OwnedFeatureHit(feature=feature, owner=body))


def _two_beams_flush():
    """Two beams end to end with their tops flush, a gap between them."""
    one, other = _beam(m(0), "one"), _beam(m(2), "other")
    return one, other, _face(one, "front"), _face(other, "front")


def test_two_tops_seen_side_on_line_up_and_fix_each_other_s_height():
    one, other, top, other_top = _two_beams_flush()
    solve = DrawingSolve([one, other])

    found = coincidence_assumptions({"front": [top, other_top]}, {"front": FRONT}, solve)

    assert len(found) == 1
    rows = [row for assumption in found for row in assumption.rows]
    # With the first top known, the second is left with its two tilts and not its height.
    before = remaining(solve.dof_rows(top), solve.dof_rows(other_top)).count
    after = remaining([*solve.dof_rows(top), *rows], solve.dof_rows(other_top)).count
    assert after == before - 1


def test_a_feature_the_view_does_not_show_lines_up_with_nothing():
    one, other, top, other_top = _two_beams_flush()

    assert coincidence_assumptions({"front": [top]}, {"front": FRONT}, DrawingSolve([one, other])) == []
