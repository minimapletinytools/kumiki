# Last checked on kumiki 0.9.4
"""Build a small table from four STL cabriole legs and a rectangular top.

Purpose: demonstrate imported curved stock and timber-local STL placement.
Concepts demonstrated — overview: furniture, small structure, STL stock, placement editing.
Concepts demonstrated — details: millimetre STL units become metres; individual calls
allow each leg's placement to be written back independently. Dimensions are source constants.
The placement example starts with a rectangular placeholder; select it and choose Edit STL placement to align
its STL. Four stopped mortise-and-tenon joints connect the legs to the tabletop.
"""
from typing import Optional
from kumiki import (
    Frame, Kiwari, TimberTicket, create_timber, create_v2, create_v3,
    create_stl_timber, frame, ButtJointTimberArrangement, TimberEnd,
    cut_mortise_and_tenon_joint_on_face_aligned_timbers, mm,
)


def _reference(x, y, name):
    return create_timber(length=.72, size=create_v2(.07, .07), length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0),
                         bottom_position=create_v3(x, y, 0),
                         ticket=TimberTicket(name))


@frame
def cabriole_table(k: Optional[Kiwari] = None) -> Frame:
    front_left = create_stl_timber(_reference(-.4, -.25, 'legs/front_left'), '../assets/cabriole_leg.stl', placement={'rotation': [0, 0, 180]})
    front_right = create_stl_timber(_reference(.4, -.25, 'legs/front_right'), '../assets/cabriole_leg.stl', placement={'rotation': [0, 0, -90]})
    back_left = create_stl_timber(_reference(-.4, .25, 'legs/back_left'), '../assets/cabriole_leg.stl', placement={'rotation': [0, 0, 90]})
    back_right = create_stl_timber(_reference(.4, .25, 'legs/back_right'), '../assets/cabriole_leg.stl', placement={})
    # The last 25 mm of each STL leg forms the tenon inside the 35 mm tabletop.
    top = create_timber(length=1.0, size=create_v2(.7, .035), length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 1, 0),
                        bottom_position=create_v3(-.5, 0, .7125), ticket=TimberTicket('tabletop'))
    joints = [cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        ButtJointTimberArrangement(leg, top, TimberEnd.TOP),
        tenon_length=mm(25), tenon_width_relative_to_joint=mm(30), tenon_height_relative_to_joint=mm(30), mortise_depth=mm(25), relief=None,
    ) for leg in (front_left, front_right, back_left, back_right)]
    return Frame.from_joints(joints)



@frame
def cabriole_placement(k: Optional[Kiwari] = None) -> Frame:
    leg = create_stl_timber(_reference(1.2, 0, 'cabriole_leg'), '../assets/cabriole_leg.stl')
    return Frame.from_joints([], additional_unjointed_timbers=[leg])
