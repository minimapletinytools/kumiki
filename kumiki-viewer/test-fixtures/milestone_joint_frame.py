import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm
from kumiki.timber import Frame, add_milestone
from patterns.basic_joints_examples import example_basic_butt_joint


def build_frame():
    add_milestone("fixture:start")

    butt_joint = example_basic_butt_joint(create_v3(mm(0), mm(0), mm(0)))
    add_milestone("fixture:joint-created")

    extra_timber = create_timber(
        bottom_position=create_v3(mm(1200), mm(0), mm(0)),
        length=mm(700),
        size=create_v2(mm(80), mm(80)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket="extra-timber",
    )

    frame = Frame.from_joints(
        joints=[butt_joint],
        additional_unjointed_timbers=[extra_timber],
        name="Runner Milestone Joint Frame",
    )

    add_milestone("fixture:frame-ready")
    return frame
