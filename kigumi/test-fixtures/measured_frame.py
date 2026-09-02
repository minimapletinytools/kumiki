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

from kumiki.drawing import Drawing, Measure
from kumiki.identity import FeatureRef, ResolvedTimberPath, SingleFeaturePath
from kumiki.timber import Frame
from patterns.basic_joints_patterns import example_basic_mortise_and_tenon_joint


def _face(timber, cut, feature):
    """A declared face of one timber, named the way the drawings file names it."""
    return SingleFeaturePath(
        timber=ResolvedTimberPath(timber),
        ref=FeatureRef(csg_path=cut, feature=feature),
        feature_type="FACE",
    )


def build_frame():
    joint = example_basic_mortise_and_tenon_joint()

    tenon_top = _face("butt_timber", ("tenon_waste", "tenon"), "tenon_top")
    shoulder = _face("butt_timber", ("tenon_waste", "shoulder"), "shoulder")
    mortise_bottom = _face("receiving_timber", ("mortise_hole",), "mortise_bottom")
    mortise_front = _face("receiving_timber", ("mortise_hole",), "mortise_front")

    return Frame(
        cut_timbers=Frame.from_joints(joints=[joint]).cut_timbers,
        name="Measured Fixture Frame",
        drawings=[
            # One piece, so this gets the four-long-faces layout, and the
            # measurement that matters on it: how far the tenon stands off the
            # shoulder, which is the length that has to be cut.
            Drawing(
                name="tenon",
                timber_paths=["butt_timber"],
                measurements={"front": [Measure(anchor_a=tenon_top, anchor_b=shoulder)]},
            ),
            # The mortise it goes into, measured in two viewports, to show that
            # the same drawing carries different dimensions in different views.
            Drawing(
                name="mortise",
                timber_paths=["receiving_timber"],
                measurements={
                    "front": [Measure(anchor_a=mortise_bottom, anchor_b=mortise_front)],
                    "right": [Measure(anchor_a=mortise_front, anchor_b=mortise_bottom)],
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
                timber_paths=["butt_timber", "receiving_timber"],
                measurements={"top": [Measure(anchor_a=shoulder, anchor_b=mortise_bottom)]},
            ),
        ],
    )
