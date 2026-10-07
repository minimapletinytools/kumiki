"""A frame whose drawings carry measurements, for working on drawing mode.

A mortise and tenon, because it is the one joint that declares features, so its
faces can be named in a measurement rather than picked at. The measurements here
are written by hand -- the point of the fixture is to have some that exist
before anything can make one, so drawing them can be built and looked at without
the picking to go with it.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from kumiki.drawings.drawing import Drawing, Measure
from kumiki.csg.feature_paths import find_feature
from kumiki.identity import ResolvedTimberPath, ViewportId
from kumiki.timber import Frame
from patterns.basic_joints_patterns import example_basic_mortise_and_tenon_joint


def build_frame():
    joint = example_basic_mortise_and_tenon_joint()
    built = Frame.from_joints(joints=[joint])

    def _timber(name):
        cut_timber = built.cut_timber_at(ResolvedTimberPath(name))
        assert cut_timber is not None
        return cut_timber.timber

    def _face(timber, cut, feature):
        cut_timber = built.cut_timber_at(ResolvedTimberPath(timber))
        assert cut_timber is not None
        handle = find_feature(cut_timber, cut, feature)
        assert handle is not None, feature
        return handle

    tenon_top = _face("butt_timber", ("tenon_waste", "tenon"), "tenon_top")
    shoulder = _face("butt_timber", ("tenon_waste", "shoulder"), "shoulder")
    mortise_bottom = _face("receiving_timber", ("mortise_hole",), "mortise_bottom")
    mortise_front = _face("receiving_timber", ("mortise_hole",), "mortise_front")

    return Frame(
        cut_timbers=built.cut_timbers,
        name="Measured Fixture Frame",
        drawings=[
            # One piece, so this gets the four-long-faces layout, and the
            # measurement that matters on it: how far the tenon stands off the
            # shoulder, which is the length that has to be cut.
            Drawing(
                name="tenon",
                timbers=[_timber("butt_timber")],
                measurements={ViewportId("0.0.0"): [Measure(anchor_a=tenon_top, anchor_b=shoulder)]},
            ),
            # The mortise it goes into, measured in two viewports, to show that
            # the same drawing carries different dimensions in different views.
            Drawing(
                name="mortise",
                timbers=[_timber("receiving_timber")],
                measurements={
                    # Keyed by viewport id, which is a POSITION in the layout --
                    # see kumiki/drawings/layout.py. "0.0.0" and "0.0.1" are the first two
                    # rows of the left column, the front and right elevations of
                    # the long-face layout one timber gets.
                    ViewportId("0.0.0"): [Measure(anchor_a=mortise_bottom, anchor_b=mortise_front)],
                    ViewportId("0.0.1"): [Measure(anchor_a=mortise_front, anchor_b=mortise_bottom)],
                },
            ),
            # Both pieces, so world elevations rather than long faces. From the
            # shoulder to the mortise floor: how deep the tenon sits in.
            #
            # In the plan view, not the front elevation, and the reason is the
            # point of measurements belonging to viewports. That pair separates
            # along north, which the front elevation looks straight down -- so
            # there it projects onto itself and measures nothing, while the plan
            # view shows the whole of it.
            Drawing(
                name="the joint",
                timbers=[_timber("butt_timber"), _timber("receiving_timber")],
                measurements={ViewportId("0.0.1"): [Measure(anchor_a=shoulder, anchor_b=mortise_bottom)]},
            ),
        ],
    )


example = build_frame
