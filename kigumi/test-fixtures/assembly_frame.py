import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm
from kumiki.ticket import JointTicket
from kumiki.timber import AssemblyFreedom, Cutting, Frame, Joint, Ordering


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

    joint = Joint(
        cuttings={
            # The end cut is what makes this a joint at all: Joint rejects
            # cuttings that between them remove nothing. The assembly
            # annotations below are what this fixture is really here for.
            "a": Cutting(timber=timber_a, maybe_top_end_cut_distance_from_bottom=mm(900)),
            "b": Cutting(
                timber=timber_b,
                assembly_freedom=AssemblyFreedom.translation(create_v3(0, 0, 1), mm(200)),
            ),
        },
        ticket=JointTicket(path="ab_joint", joint_type="test_joint"),
    ).with_order(1)

    return Frame.from_joints(
        joints=[joint],
        name="Assembly Fixture Frame",
    )
