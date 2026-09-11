"""A frame with parameters, for driving the kiwari panel end to end.

Every parameter here changes the geometry. A control that does nothing would
make this fixture worse than no fixture, since the panel is the thing it exists
to demonstrate.
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from kumiki.construction import create_timber
from kumiki.kiwari import Kiwari, kiwari
from kumiki.rule import cos, create_v2, create_v3, degrees, mm, scalar, sin
from kumiki.timber import CutTimber, Frame, TimberEnd


def build_frame(k=None):
    k = kiwari(
        posts=kiwari.count(2, minimum=1, maximum=6, about="How many posts"),
        post_height=kiwari.length(mm(1000), about="How tall each post stands"),
        spacing=kiwari.length(mm(300), about="Centre to centre along X"),
        size=kiwari.point2(create_v2(mm(100), mm(100)), about="Post cross section"),
        lean=kiwari.angle(degrees(0), minimum=degrees(-40), maximum=degrees(40),
                          about="How far each post tilts along X"),
        alternating=kiwari.flag(False, about="Lean every other post the other way"),
        # Optional: off is a real answer here, not a missing one.
        cap=kiwari.length(optional=True, about="Thickness of a cap board; off for no cap"),
        cap_end=kiwari.choice(TimberEnd, TimberEnd.TOP, about="Which end the cap sits on"),
    ).resolve(k)

    posts = k.count("posts")
    height = k.length("post_height")
    spacing = k.length("spacing")
    size = k.v2("size")
    lean = k.angle("lean")

    timbers = []
    for index in range(posts):
        tilt = -lean if (k.flag("alternating") and index % 2) else lean
        # Tilt about Y, so the posts lean along X and stay in the XZ plane.
        along = create_v3(sin(tilt), scalar(0), cos(tilt))
        across = create_v3(cos(tilt), scalar(0), -sin(tilt))
        timbers.append(create_timber(
            bottom_position=create_v3(spacing * index, mm(0), mm(0)),
            length=height,
            size=size,
            length_direction=along,
            width_direction=across,
            ticket=f"Post {index + 1}",
        ))

    cap = k.length("cap")
    if cap is not None:
        # One board across all the posts, at whichever end was asked for.
        span = spacing * (posts - 1) + size[0]
        at_top = k.choice("cap_end") is TimberEnd.TOP
        timbers.append(create_timber(
            bottom_position=create_v3(
                -size[0] / scalar(2),
                mm(0),
                height * cos(lean) if at_top else -cap,
            ),
            length=span,
            size=create_v2(cap, size[1]),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 0, 1),
            ticket="Cap",
        ))

    return Frame.from_joints(
        joints=[],
        additional_unjointed_timbers=timbers,
        name=f"Kiwari Test Frame ({posts} posts)",
        kiwari=k,
    )
