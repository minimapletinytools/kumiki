"""
Test file for Kumiki Viewer extension.
Run 'Render Kumiki' command with this file open to test the viewer.
"""

import sys
from pathlib import Path

# Add the project root to the path so we can import kumikicad
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from kumiki.timber import Frame, CutTimber
from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm

def build_frame():
    """
    This function is called by the Kumiki Viewer extension.
    It should return a Frame object.

    Note: Originally wanted to call this 'raise' (as in 'raising a frame'),
    but that's a Python keyword, so we use 'build_frame' instead.
    """

    # Create some simple timbers for testing
    timber1 = create_timber(
        bottom_position=create_v3(0, 0, 0),
        length=mm(2000),
        size=create_v2(mm(100), mm(150)),
        length_direction=create_v3(0, 0, 1),  # Vertical
        width_direction=create_v3(1, 0, 0),   # Along X-axis
        name="Post 1"
    )

    timber2 = create_timber(
        bottom_position=create_v3(mm(500), 0, 0),
        length=mm(3000),
        size=create_v2(mm(150), mm(150)),
        length_direction=create_v3(0, 0, 1),  # Vertical
        width_direction=create_v3(1, 0, 0),   # Along X-axis
        name="Post 2"
    )

    timber3 = create_timber(
        bottom_position=create_v3(0, mm(300), 0),
        length=mm(1500),
        size=create_v2(mm(100), mm(200)),
        length_direction=create_v3(1, 0, 0),  # Horizontal along X
        width_direction=create_v3(0, 1, 0),   # Along Y-axis
        name="Beam 1"
    )

    # Create a frame from these timbers
    frame = Frame.from_joints(
        joints=[],
        additional_unjointed_timbers=[timber1, timber2, timber3],
        name="Test Frame"
    )

    return frame

# For testing from command line
if __name__ == '__main__':
    frame = build_frame()
    print(f"Created frame: {frame.name}")
    print(f"Timbers: {len(frame.cut_timbers)}")
    print(f"Accessories: {len(frame.accessories)}")
