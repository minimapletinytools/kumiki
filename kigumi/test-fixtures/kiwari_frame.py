"""A frame with parameters, for driving the kiwari panel end to end."""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from kumiki.construction import create_timber
from kumiki.kiwari import Kiwari, kiwari
from kumiki.rule import create_v2, create_v3, degrees, mm
from kumiki.timber import Frame, TimberEnd


def build_frame(k=None):
    k = kiwari(
        posts=kiwari.count(2, minimum=1, maximum=6, about="How many posts"),
        post_height=kiwari.length(mm(1000), about="How tall each post stands"),
        lean=kiwari.angle(degrees(0)),
        size=kiwari.point2(create_v2(mm(100), mm(100))),
        capped=kiwari.flag(False),
        end=kiwari.choice(TimberEnd, TimberEnd.TOP),
    ).resolve(k)

    timbers = [
        create_timber(
            bottom_position=create_v3(mm(300) * index, mm(0), mm(0)),
            length=k.length("post_height"),
            size=k.v2("size"),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket=f"Post {index + 1}",
        )
        for index in range(k.count("posts"))
    ]

    return Frame.from_joints(
        joints=[],
        additional_unjointed_timbers=timbers,
        name=f"Kiwari Test Frame ({k.count('posts')} posts)",
        kiwari=k,
    )
