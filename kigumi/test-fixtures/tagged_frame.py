import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm
from kumiki.ticket import Member, MemberTag, SliceTag, TimberTicket
from kumiki.timber import Frame


def _post(name, x, slice_name):
    return create_timber(
        bottom_position=create_v3(mm(x), mm(0), mm(0)),
        length=mm(2000),
        size=create_v2(mm(100), mm(100)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket=TimberTicket(path=f"posts/{name}").with_tags(
            MemberTag(Member.CORNER_POST), SliceTag(slice_name)
        ),
    )


def build_frame():
    """A frame that wears every kind of tag, for looking at the tags section."""
    posts = [_post("front_left", 0, "bent1"), _post("front_right", 1500, "bent2")]

    plate = create_timber(
        bottom_position=create_v3(mm(0), mm(0), mm(2000)),
        length=mm(1600),
        size=create_v2(mm(100), mm(150)),
        length_direction=create_v3(1, 0, 0),
        width_direction=create_v3(0, 1, 0),
        ticket=TimberTicket(path="plates/front").with_tags(
            MemberTag(Member.TOP_PLATE), SliceTag("bent1"), SliceTag("bent2"), "needs_review"
        ),
    )

    return Frame.from_joints(
        joints=[],
        additional_unjointed_timbers=[*posts, plate],
        name="Tagged Fixture Frame",
    )
