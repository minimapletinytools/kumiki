import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from giraffecad.construction import create_timber
from giraffecad.rule import Orientation, Transform, create_v2, create_v3, mm
from giraffecad.timber import Frame, Peg, PegShape


def build_frame():
    timber = create_timber(
        bottom_position=create_v3(mm(0), mm(0), mm(0)),
        length=mm(800),
        size=create_v2(mm(100), mm(100)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket="A",
    )

    base_frame = Frame.from_joints(
        joints=[],
        additional_unjointed_timbers=[timber],
        name="Runner Accessory Test Frame",
    )

    accessory_transform = Transform(
        position=create_v3(mm(50), mm(0), mm(200)),
        orientation=Orientation.identity(),
    )
    peg = Peg(
        transform=accessory_transform,
        size=mm(20),
        shape=PegShape.SQUARE,
        forward_length=mm(80),
        stickout_length=mm(20),
    )

    return Frame(
        cut_timbers=base_frame.cut_timbers,
        accessories=[peg],
        name=base_frame.name,
    )
