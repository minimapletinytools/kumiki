"""
Free Dovetail Joint Patterns

A post standing on a beam, held by a sliding dovetail across the post's width: the beam
gets the socket, the post the tongue.
"""

from kumiki import *


def _post_on_beam_with_dovetail(position, taper_angle):
    if position is None:
        position = create_v3(0, 0, 0)
    # The beam runs along x with its top face at z=50mm; the post stands on it from z=0.
    beam = create_timber(bottom_position=position + create_v3(mm(-500), 0, 0), length=mm(1000),
                         size=create_v2(mm(100), mm(100)), length_direction=create_v3(1, 0, 0),
                         width_direction=create_v3(0, 1, 0), ticket="beam")
    post = create_timber(bottom_position=position, length=mm(600), size=create_v2(mm(100), mm(100)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="post")
    # Slides along x, across the post's width. The neck is 40mm wide at the beam's top face and the
    # tongue flares at 15 degrees down into the beam for 30mm, so the post cannot lift out.
    dovetail = FreeDovetailShape(
        origin=Transform(position=position + create_v3(0, 0, mm(50)),
                         orientation=Orientation.from_x_and_y(create_v3(1, 0, 0), create_v3(0, 0, -1))),
        width=mm(40), depth=mm(30), dovetail_angle=degrees(15),
        forward_length=mm(50), backward_length=mm(50), taper_angle=taper_angle,
    )
    return cut_free_dovetail_joint(post, beam, dovetail)


@pattern("free_joints/free_dovetail_joint/sliding", tags=["main"])
def example_free_sliding_dovetail(position=None) -> Joint:
    """A straight sliding dovetail."""
    return _post_on_beam_with_dovetail(position, scalar(0))


@pattern("free_joints/free_dovetail_joint/tapered")
def example_free_tapered_dovetail(position=None) -> Joint:
    """The same, tapering toward its forward end, so it tightens as it slides home."""
    return _post_on_beam_with_dovetail(position, degrees(5))
