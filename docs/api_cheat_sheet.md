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

For imported stock, use `create_stl_timber(reference, stl_path, *, units='mm', placement=None)`.
Omit placement for an editable placeholder; see [STL timbers](stl_timbers.md).

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
| `cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers(arrangement: DoubleButtJointTimberArrangement, slot_facing_end_on_receiving_timber: TimberEnd) -> Joint` | |
| `cut_basic_plain_splice_lap_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement) -> Joint` |Lengthening a timber. |
| `cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement) -> Joint` | |
| `cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(tenon_timber: TimberLike, mortise_timber: TimberLike, tenon_end: TimberEnd, use_peg: bool=False) -> Joint` |A beam into a post, or a rail into a leg. |
| `cut_basic_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(tenon_timber: TimberLike, mortise_timber: TimberLike, tenon_end: TimberEnd) -> Joint` | |
| `cut_basic_lapped_gooseneck_joint_on_aligned_timbers(gooseneck_timber: TimberLike, receiving_timber: TimberLike, receiving_timber_end: TimberEnd, gooseneck_timber_face: TimberLongFace) -> Joint` | |
| `cut_basic_dropin_dovetail_butt_joint_on_face_aligned_timbers(arrangement: ButtJointTimberArrangement, *, receiving_timber_shoulder_inset: Numeric=scalar(0)) -> Joint` | |
| `cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers(housed_timber: TimberLike, receiving_timber: TimberLike, housed_timber_end: TimberEnd, housed_timber_face: TimberLongFace, receiving_timber_shoulder_inset: Numeric=scalar(0)) -> Joint` | |
| `cut_basic_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint` | |
| `cut_basic_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(arrangement: ButtJointTimberArrangement) -> Joint` | |
| `cut_basic_plain_corner_lap_joint_on_plane_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint` |Lapped sill or plate corners. |
| `cut_basic_plain_cross_lap_joint(arrangement: CrossJointTimberArrangement) -> Joint` | |
| `cut_basic_plain_cross_lap_house_joint(arrangement: CrossJointTimberArrangement) -> Joint` | |
| `cut_basic_multi_cross_lap_joint_on_plane_aligned_timbers(timbers: List[TimberLike], starting_face_on_first_timber: TimberFace) -> Joint` | |
| `cut_basic_mortise_and_tenon_joint(arrangement: ButtJointTimberArrangement, *, use_peg: bool=False) -> Joint` | |
| `cut_basic_round_mortise_and_tenon_joint(arrangement: ButtJointTimberArrangement) -> Joint` | |
| `cut_basic_tongue_and_groove_joint(tongue_board: Board, groove_board: Board) -> Joint` |Joining board edges. |
| `cut_basic_practice_sliding_dovetail_joint_on_orthogonal_boards(arrangement: ButtJointBoardArrangement) -> Joint` | |
| `cut_basic_dovetail_corner_joint(arrangement: CornerJointTimberArrangement, *, half_blind: bool=False) -> Joint` |Box and drawer corners. |
| `cut_basic_practice_roundover_decoration(timber: BlockLike, edges: List[TimberEdge]) -> Joint` | |
| `cut_basic_practice_rounded_end_decoration(timber: BlockLike, rounded_face: TimberFace, rounded_end: TimberFace) -> Joint` | |
| `cut_basic_practice_rafter_tail_scallop_corner_end_decoration(timber: BlockLike, short_edge: TimberShortEdge) -> Joint` | |
| `cut_basic_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers(arrangement: CornerJointTimberArrangement, *, use_peg: bool=False) -> Joint` | |

Basic rectangular and round tenons stop short of the receiving timber’s far side, reserving a quarter of the available insertion depth. The existing face-aligned rectangular basic uses the same recipe. Use the full cutters for through tenons or explicit dimensions. Tusked and wedged-half-dovetail basics retain their through-tenon recipes.

The face-aligned basic cross-lap and housing names are deprecated; use the general basics above. Custom-shape cutters and the already-sized free housing and grooved-panel cutters do not need separate basic wrappers.

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

## Drawings

drawings can be automatically generated but the results aren't so great.

```python
from kumiki.drawings.auto_drawings import with_auto_drawings
...
frame = Frame.from_joints(..)
frame = with_auto_drawings(frame, fixed_path="beam")   # a plan measured from the timber "beam", and a shop drawing per distinct piece

# or a shop drawing for just one timber, `post`, generated after the frame is shown
from kumiki.drawings.auto_drawings import piece_drawing
from kumiki.csg.symmetry import SymmetricTimberGroup
from kumiki.finishing import Finishing
def post_drawing(finishing: Finishing) -> None:
    finishing.add_drawing(piece_drawing(SymmetricTimberGroup(frame.cut_timber_of(post), ())))
frame = frame.with_finishing(post_drawing)

return frame
```

To add measurements by manually, make a `Drawing` whose `measurements` are `Measure(feature_a, feature_b)`s between features found with `find_feature`, and add it from a finishing routine (`frame.with_finishing`, `Finishing.add_drawing`). Use the `kumiki_source` tool to see the following files:

- `kumiki/drawings/auto_drawings.py`: `with_auto_drawings`, and `plan_drawing` / `piece_drawing` to start from a generated drawing
- `kumiki/drawings/drawing.py`: `Drawing`, `shop_drawing_viewports()`, `SHOP_DRAWING_IDS`, `elevation_viewports()`
- `kumiki/drawings/measure.py`: `Measure`
- `kumiki/csg/feature_paths.py`: `find_feature`, which names the features to measure between
- `kumiki/finishing.py`: `Finishing`
- an example: `patterns/structures/dovetailed_sawhorse.py`; and "Generating drawings" in `agent_usage_instructions.md`


## Examples

Use these files as source references for the concepts you need. Each starts with its
purpose, a short concept list, and implementation details. Public examples live in
`patterns/structures/`; open a file in Kigumi or find it with `kumiki_source`.

| Example | Good reference for | Kiwari controls |
|---|---|---|
| [Cabriole table and STL placement](../patterns/structures/cabriole_table.py) | Furniture with four imported cabriole legs; separate placeholder for interactive STL alignment | None; source dimensions and STL placement |
| [Starter frame](../patterns/structures/my_cute_frame.py) | Simple four-member frame; face-aligned and axis-oriented construction; pegged tenons | None; source dimensions |
| [Simple sawhorse](../patterns/structures/horsey_example.py) | Small furniture; orthogonal feet, posts, stretcher, and top beam | None; source dimensions |
| [Double-sawhorse workbench](../patterns/structures/doublesawhorseworkbench.py) | Furniture; through/stopped tenons; cross-lapped stretcher and tool tray | None; source dimensions |
| [Coffee table](../patterns/structures/coffee_table.py) | Furniture; several joints meeting shared legs; tusked stretchers and decorative cuts | None; source dimensions |
| [Dovetailed sawhorse](../patterns/structures/dovetailed_sawhorse.py) | Non-square construction; splayed legs; tapered dovetails; drawings and router templates | Sizing and angles: height, timber dimensions, leg spacing and splay; separate template-tool controls |
| [Wood character](../patterns/structures/ki_kanji.py) | Small sculpture; diagonal members; splined and pegged joints; curved profiles | None; source dimensions |
| [Cross-lapped post](../patterns/structures/multi_cross_lap_post.py) | Three boards at 60-degree plan intervals; round stock; multi-member joinery | None; source dimensions and count |
| [Oscar's shed](../patterns/structures/oscarshed.py) | Small standard timber-frame building; **single-pitch rafters** housed in unequal-height plates | None; source dimensions and counts |
| [Timber-frame shed](../patterns/structures/learn_to_timber_frame_shed.py) | Medium standard frame; floor joists; angled braces; **paired rafters joined at the peak** with collars | Structural counts: joists, rafter pairs, intermediate posts; sizing: footprint |
| [120-square-foot tiny house](../patterns/structures/tinyhouse120.py) | Medium standard frame; king posts and ridge beam; **ridge-supported rafters** with eave extensions | None; source dimensions and counts |
| [Multiple frames: pavilion yard](../patterns/structures/multiple_frames.py) | Multiple frames in one file; roofed timber pavilion; simple building models as context | Shared model spacing/height; independent pavilion member sizes, roof rise and rafter count |

Development fixtures live together in `hidden_structures/`, outside the published
pattern catalog. They are useful for specific mechanisms rather than as starting designs:

| Development example | Concepts |
|---|---|
| [Assembly preview](../hidden_structures/assembly_preview_demo.py) | Joint ordering, peg removal, extraction, and deliberate warning cases |
| [Drawing fixture](../hidden_structures/my_cute_frame_drawing_test.py) | Rough stock, reference features, matching pieces, generated drawings |
| [Cat corner cot](../hidden_structures/cat_corner_cot.py) | Multiple frames; non-rectangular supporting context; stepped members and sloping roof |
| [N-legged stool](../hidden_structures/development/n_legged_stool.py) | Radial furniture; splayed round legs; Kiwari leg count, dimensions and angles |
| [Simultaneous assembly](../hidden_structures/development/simple_simultaneous_assembly.py) | Reciprocal polygon; Kiwari member count, cross-section and radius |
| [Six-piece Luban lock](../hidden_structures/actually_kumiki/luban_lock_1.py) | Diamond cross-sections and cyclic housings |
| [Three-piece Luban lock](../hidden_structures/actually_kumiki/luban_lock_2.py) | Custom cuts; rotation followed by translation during disassembly |
| [Gordian knot](../hidden_structures/actually_kumiki/gordian_knot.py) | Cell-based CSG cutouts and interlocking pieces |

The hidden collection also contains relief-algorithm patterns in
`hidden_structures/development/relief_example_patterns.py`.
