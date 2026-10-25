# API cheat sheet

The signatures of what a frame most often uses, and one complete small frame. The usage instructions
and concepts say when to use each and why; this is what to type. For anything not here, look the name
up (Kigumi's agent: `kumiki_api`) rather than guessing.

All of these come from `from kumiki import *`. Lengths are metres unless made with a unit.

## Units and vectors

```python
mm(numerator, denominator=1)      # mm(90); mm(1, 2) is half a millimetre
inches(numerator, denominator=1)  # inches(7, 2) is 3.5"
feet(numerator, denominator=1)
degrees(angle)
create_v2(x, y)                   # a size (width, height), or a point on the footprint
create_v3(x, y, z)                # a point in the world; Z is up
```

## Timbers

```python
create_axis_aligned_timber(bottom_position, length, size, length_direction, width_direction=None, ticket=None) -> Timber
```

- `bottom_position` is the center of the timber's bottom end, not a corner: a timber lying flat at Z = 0 is half below the ground.
- `size` is `(width, height)`: the width runs along `width_direction`, the height along the third axis.
- `length_direction` and `width_direction` are `TimberFace`s naming world directions: `TOP` is +Z, `RIGHT` +X, `FRONT` +Y.
- `ticket` is the timber's name (a string), or a `TimberTicket(path, material=None, reference_features=(), tags=())`.

On a footprint, which keeps timbers on the ground:

```python
Footprint(corners=(create_v2(...), ...))   # the corners, in order around it
create_vertical_timber_on_footprint_corner(footprint, corner_index, length, location_type, size, ticket=None) -> Timber
create_vertical_timber_on_footprint_side(footprint, side_index, distance_along_side, length, location_type, size, ticket=None) -> Timber
create_horizontal_timber_on_footprint(footprint, corner_index, location_type, size, length=None, ticket=None) -> Timber
# location_type: FootprintLocation.INSIDE (the usual), OUTSIDE or CENTER
```

Between two timbers:

```python
join_face_aligned_on_face_aligned_timbers(timber1, timber2, location_on_timber1, stickout, size, lateral_offset_from_timber1=0,
                                          feature_to_mark_on_joining_timber=None, orientation_face_on_timber1=None, ticket=None) -> Timber
join_timbers(timber1, timber2, location_on_timber1, location_on_timber2=None, lateral_offset=0, stickout=Stickout(...),
             size=None, orientation_width_vector=None, ticket=None) -> Timber
# stickout: Stickout.nostickout() to end at the two timbers' centerlines
```

The new timber's `BOTTOM` end is at `timber1`, its `TOP` end at `timber2`.

## Joints

```python
cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(tenon_timber, mortise_timber, tenon_end, use_peg=False) -> Joint
```

Sizes the tenon and mortise for you; start with it. For control over them:

```python
ButtJointTimberArrangement(butt_timber, receiving_timber, butt_timber_end, front_face_on_butt_timber=None, top_face_on_butt_timber=None)
cut_mortise_and_tenon_joint_on_face_aligned_timbers(arrangement, tenon_length, tenon_size=None, tenon_width_relative_to_joint=None,
    tenon_height_relative_to_joint=None, mortise_depth=None, tenon_position=None, mortise_shoulder_inset=0,
    wedge_parameters=None, peg_parameters=None, use_round_tenon=False) -> Joint
SimplePegParameters(shape, peg_positions, size, depth=None, tenon_hole_offset=0)   # shape: PegShape.ROUND or SQUARE
```

- `TimberEnd.TOP` or `BOTTOM` names a timber's end; `TimberLongFace.RIGHT`, `FRONT`, `LEFT` or `BACK` one of its long faces.
- `front_face_on_butt_timber` must be parallel to the plane both timbers lie in (concepts.md, "Butt joint arrangements"). Pegged joints need it.

## The frame

```python
@frame
def my_frame(k: Optional[Kiwari] = None) -> Frame:
    ...
    return Frame.from_joints(joints, additional_unjointed_timbers=None, name="my frame", kiwari=k)
```

## A complete small frame

Four posts on a footprint, a beam along the top of each long side, and a rail across each end, all
in basic mortise and tenons. It builds, and every timber meets the rest.

```python
from typing import Optional
from kumiki import *

POST = create_v2(inches(4), inches(4))
BEAM = create_v2(inches(4), inches(6))
POST_HEIGHT = feet(3)


@frame
def bench(k: Optional[Kiwari] = None) -> Frame:
    # A 4' x 2' rectangle on the ground, its corners in order around it.
    footprint = Footprint(corners=(create_v2(0, 0), create_v2(feet(4), 0), create_v2(feet(4), feet(2)), create_v2(0, feet(2))))
    posts = [create_vertical_timber_on_footprint_corner(footprint, i, POST_HEIGHT, FootprintLocation.INSIDE, POST,
                                                        ticket=f"post {i}") for i in range(4)]
    # A beam between the tops of each long side's posts.
    beams = [join_face_aligned_on_face_aligned_timbers(posts[a], posts[b], location_on_timber1=POST_HEIGHT - BEAM[1] / 2,
                                                       stickout=Stickout.nostickout(), size=BEAM, ticket=name)
             for a, b, name in [(0, 1, "front beam"), (3, 2, "back beam")]]
    # A rail at each end, a foot up, tying the two sides together.
    rails = [join_face_aligned_on_face_aligned_timbers(posts[a], posts[b], location_on_timber1=feet(1),
                                                       stickout=Stickout.nostickout(), size=POST, ticket=name)
             for a, b, name in [(1, 2, "right rail"), (0, 3, "left rail")]]
    # Each beam or rail is tenoned into the posts at its ends: its BOTTOM end into the first, TOP into the second.
    spans = [(beams[0], posts[0], posts[1]), (beams[1], posts[3], posts[2]), (rails[0], posts[1], posts[2]), (rails[1], posts[0], posts[3])]
    joints = [cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(span, post, end)
              for span, first, second in spans
              for post, end in [(first, TimberEnd.BOTTOM), (second, TimberEnd.TOP)]]
    return Frame.from_joints(joints, name="bench", kiwari=k)
```
