import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm
from kumiki.timber import Frame


def build_frame():
    timber_a = create_timber(
        bottom_position=create_v3(mm(0), mm(0), mm(0)),
        length=mm(1000),
        size=create_v2(mm(100), mm(100)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket="A",
    )

    timber_b = create_timber(
        bottom_position=create_v3(mm(300), mm(0), mm(0)),
        length=mm(900),
        size=create_v2(mm(80), mm(120)),
        length_direction=create_v3(0, 1, 0),
        width_direction=create_v3(1, 0, 0),
        ticket="B",
    )

    return Frame.from_joints(
        joints=[],
        additional_unjointed_timbers=[timber_a, timber_b],
        name="Runner Test Frame",
    )
