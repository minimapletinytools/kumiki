# API cheat sheet

The signatures of what a frame most often uses, and one complete small frame. The usage instructions
and concepts say when to use each and why; this is what to type. For anything not here, look the name
up (Kigumi's agent: `kumiki_api`, or `kumiki_source` to read and search kumiki's files) rather than guessing.

All of these come from `from kumiki import *`. Lengths are metres unless made with a unit.

## Units and vectors

```python
mm(numerator, denominator=1)      # mm(90); mm(1, 2) is half a millimetre
inches(numerator, denominator=1)  # inches(7, 2) is 3.5"
feet(numerator, denominator=1)
degrees(numerator, denominator=1) # degrees(45, 2) is 22.5 degrees, in radians
radians(numerator, denominator=1)
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


| Basic joint signature | When to use |
|---|---|
| `cut_basic_plain_miter_joint(arrangement: CornerJointTimberArrangement) -> Joint` |Mitered frame corners. |
| `cut_basic_plain_miter_joint_on_face_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint` | |
| `cut_basic_tongue_and_fork_corner_joint_on_plane_aligned_timbers(arrangement: CornerJointTimberArrangement, tongue_thickness: Optional[Numeric]=None, tongue_position: Numeric=scalar(0)) -> Joint` | |
| `cut_basic_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement: ButtJointTimberArrangement, tongue_thickness: Optional[Numeric]=None, tongue_position: Numeric=scalar(0), shoulder_inset: Numeric=scalar(0)) -> Joint` | |
| `cut_basic_plain_butt_joint(arrangement: ButtJointTimberArrangement) -> Joint` |Plain contact between members. |
| `cut_basic_plain_butt_joint_on_face_aligned_timbers(arrangement: ButtJointTimberArrangement) -> Joint` | |
| `cut_basic_plain_butt_splice_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement) -> Joint` | |
| `cut_basic_plain_cross_lap_joint_on_face_aligned_timbers(arrangement: CrossJointTimberArrangement) -> Joint` | |
| `cut_basic_plain_house_joint_on_face_aligned_timbers(arrangement: CrossJointTimberArrangement) -> Joint` | |
| `cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers(arrangement: DoubleButtJointTimberArrangement, slot_facing_end_on_receiving_timber: TimberEnd) -> Joint` | |
| `cut_basic_plain_splice_lap_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement) -> Joint` |Lengthening a timber. |
| `cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement) -> Joint` | |
| `cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(tenon_timber: TimberLike, mortise_timber: TimberLike, tenon_end: TimberEnd, use_peg: bool=False) -> Joint` |A beam into a post, or a rail into a leg. |
| `cut_basic_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(tenon_timber: TimberLike, mortise_timber: TimberLike, tenon_end: TimberEnd) -> Joint` | |
| `cut_basic_lapped_gooseneck_joint_on_aligned_timbers(gooseneck_timber: TimberLike, receiving_timber: TimberLike, receiving_timber_end: TimberEnd, gooseneck_timber_face: TimberLongFace) -> Joint` | |
| `cut_basic_dropin_dovetail_butt_joint_on_face_aligned_timbers(dovetail_timber: TimberLike, receiving_timber: TimberLike, dovetail_timber_end: TimberEnd, dovetail_timber_face: TimberLongFace, receiving_timber_shoulder_inset: Numeric, dovetail_length: Numeric, dovetail_small_width: Numeric, dovetail_angle: Numeric) -> Joint` | |
| `cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers(housed_timber: TimberLike, receiving_timber: TimberLike, housed_timber_end: TimberEnd, housed_timber_face: TimberLongFace, receiving_timber_shoulder_inset: Numeric=scalar(0)) -> Joint` | |
| `cut_basic_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint` | |
| `cut_basic_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(arrangement: ButtJointTimberArrangement) -> Joint` | |

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
