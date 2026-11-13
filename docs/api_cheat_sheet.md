# API cheat sheet

A cheat sheet of actual methods to use when authoring kumiki frames. Use the `kumiki_api` tool to learn more about the methods. Use the `kumiki_source` tool to see the full source code. Please also see `agent_usage_instructions.md` and `concepts.md`.

## Units and vectors

```python
mm(numerator, denominator=1)      # mm(90) is 90mm; mm(1, 2) is half a millimetre
cm(..)
m(..)
inches(..)  # inches(7, 2) is 3.5"
feet(..)
degrees(..)
radians(..)
create_v2(x, y)                   # a size (width, height), or a point on the footprint
create_v3(x, y, z)                # a point in the world; Z is up
```

## Creating Timbers

make a footprint first and add timbers to it:

```python
Footprint(corners=(create_v2(...), ...))   # the corners, in order around it
create_vertical_timber_on_footprint_corner(footprint, corner_index, length, location_type, size, ticket=None) -> Timber
create_vertical_timber_on_footprint_side(footprint, side_index, distance_along_side, length, location_type, size, ticket=None) -> Timber
create_horizontal_timber_on_footprint(footprint, corner_index, location_type, size, length=None, ticket=None) -> Timber
# location_type: FootprintLocation.INSIDE (the usual), OUTSIDE or CENTER
```

join timbers together:

```python
join_face_aligned_on_face_aligned_timbers(timber1, timber2, location_on_timber1, stickout, size, lateral_offset_from_timber1=0,
                                          feature_to_mark_on_joining_timber=None, orientation_face_on_timber1=None, ticket=None) -> Timber
join_timbers(timber1, timber2, location_on_timber1, location_on_timber2=None, lateral_offset=0, stickout=Stickout(...),
             size=None, orientation_width_vector=None, ticket=None) -> Timber
# stickout: Stickout.nostickout() to end at the two timbers' centerlines
```

creating timbers with no relations

```python
create_axis_aligned_timber(bottom_position, length, size, length_direction, width_direction=None, ticket=None) -> Timber
create_timber(length: Numeric, size: V2, bottom_position: V3,
                          length_direction: Direction3D, width_direction: Direction3D,
                          ticket: Optional[Union[TimberTicket, str]] = None) -> 'Timber'
```

- `bottom_position` is the center of the timber's bottom end, not a corner: a timber lying flat at Z = 0 is half below the ground.
- `size` is `(width, height)`: the width runs along `width_direction`, the height along the third axis.
- `length_direction` and `width_direction` are `TimberFace`s naming world directions: `TOP` is +Z, `RIGHT` +X, `FRONT` +Y.
- `ticket` is the timber's name (a string), or a `TimberTicket(path, material=None, reference_features=(), tags=())`.

## Joints

### Arrangements

Most joint functions take an arrangement naming the timbers in the joint and the "orientation" of the joint.

```python
ButtJointTimberArrangement(butt_timber, receiving_timber, butt_timber_end,
                           front_face_on_butt_timber=None, top_face_on_butt_timber=None)
DoubleButtJointTimberArrangement(butt_timber_1, butt_timber_2, receiving_timber,
                                 butt_timber_1_end, butt_timber_2_end, front_face_on_butt_timber_1=None)
CornerJointTimberArrangement(timber1, timber2, timber1_end, timber2_end, front_face_on_timber1=None)
CrossJointTimberArrangement(timber1, timber2, front_face_on_timber1=None)
SpliceJointTimberArrangement(timber1, timber2, timber1_end, timber2_end, front_face_on_timber1=None)
# ends: TimberEnd.BOTTOM/TOP
# faces: TimberLongFace.LEFT/RIGHT/FRONT/BACK
```

### Common Joints

A list of joints to use dependening on the application. Always use for the `cut_basic_*` variants first (they size the cut from the timbers); call the underlying `cut_*` function when you need more control over its parameters.

Example usage of joints can be found in the `patterns` folder in source, you can search for them using `kumiki_source(search="pattern")` tool.


| The job | Joint | Pattern |
|---|---|---|
| Beam or girt into the side of a post, pegged | `cut_mortise_and_tenon_joint_on_face_aligned_timbers` (basic variant first, `use_peg=True`) | `mixed/mortise_and_tenon_joints_patterns.py` |
| Leg into a seat or top; apron or rail into a leg | `cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers` | `basic_joints_patterns.py` |
| Tie beam, or a beam under heavy load, into a post | `cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers` | `butt/wedged_half_dovetail_joint_patterns.py` |
| Joist into a beam or sill | `cut_dropin_housed_butt_joint_on_face_aligned_timbers`; the dovetail version below if it must not pull out | `butt/dropin_housed_butt_joint_patterns.py` |
| Shelf into the side of a case, dovetailed | `cut_basic_dropin_dovetail_butt_joint_on_face_aligned_timbers` | `butt/dropin_dovetail_butt_joint_patterns.py` |
| Shelf into the side of a case, plain (a dado) | `cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers` | `butt/dropin_housed_butt_joint_patterns.py` |
| Two butt timbers into one timber from opposite sides | `cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers` | `butt/splined_opposing_double_butt_joint_patterns.py` |
| Sills or plates meeting at a corner | `cut_plain_corner_lap_joint_on_plane_aligned_timbers` (simplest); `cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers` (no end grain shows) | `corner/plain_corner_lap_joint_patterns.py` |
| A frame or box corner, mitered | `cut_basic_plain_miter_joint` | `corner/plain_miter_joint_patterns.py` |
| Box or drawer corner, dovetailed | `cut_dovetail_corner_joint` | `corner/dovetail_corner_joint_patterns.py` |
| Two rafters meeting at the ridge | `cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers` | `corner/tongue_and_fork_corner_joint_patterns.py` |
| Two timbers crossing, both notched | `cut_basic_plain_cross_lap_joint_on_face_aligned_timbers` | `basic_joints_patterns.py` |
| One timber crossing in a housing in the other | `cut_basic_plain_house_joint_on_face_aligned_timbers` | `basic_joints_patterns.py` |
| Lengthening a timber, simply | `cut_basic_plain_splice_lap_joint_on_aligned_timbers` | `splice/plain_splice_lap_joint_patterns.py` |
| Lengthening a sill (gooseneck facing up) | `cut_lapped_gooseneck_joint_on_aligned_timbers` | `splice/lapped_gooseneck_joint_patterns.py` |
| A placeholder only: it holds against nothing | `cut_basic_plain_butt_joint_on_face_aligned_timbers` | `butt/plain_butt_joint_patterns.py` |

This is not the complete list of joints. Search patterns to find joints not listed here. (TODO create a complete list of all joints)

## Creating the frame

Your kumiki project is not done until there is a `@frame` decorated function that returns a Frame. Always use Frame.from_joints and pass in the list of joint objects returned by the joint functions above. If Only use `additional_unjointed_timbers` if there are timbers that have no joints.

```
def from_joints(cls, joints: List[Joint],
                    additional_unjointed_timbers: Optional[List[PerfectTimberWithin]] = None,
                    name: Optional[str] = None,
                    kiwari: Optional['Kiwari'] = None) -> 'Frame': 
```

```python
@frame
def my_frame(k: Optional[Kiwari] = None) -> Frame:
    ...
    return Frame.from_joints(joints, additional_unjointed_timbers=None, name="my frame", kiwari=k)
```


## Examples

See all examples in the `patterns/structures` folder and using the `kumiki_source` tool.
These examples are the best API reference. Unless the user asks for just like the example, it may be better to build from the ground up rather than adapt an example.