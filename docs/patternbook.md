# Pattern System

## Overview

Pattern files expose a module-level `patterns` list containing `Pattern` objects. The Kigumi viewer scans these files and displays them in its sidebar.

## Pattern dataclass

```python
from kumiki.patternbook import Pattern

Pattern(
    path="corner_joints/cut_plain_miter_joint",   # required
    lambda_=my_lambda,                            # required
    tags=["main"],                                # optional, default []
    pattern_type="frame",                         # optional, default "frame"
)
```

| Field | Type | Description |
|-------|------|-------------|
| `path` | `str` | Hierarchical path like `"category/name"`. Each segment is an implicit tag. |
| `lambda_` | `PatternLambda` | `Callable[..., Frame \| CutCSG]` — first arg is `center: V3`. |
| `tags` | `List[str]` | Explicit tags. See special tags below. |
| `pattern_type` | `"frame"` or `"csg"` | Whether the lambda returns a `Frame` or `CutCSG`. |

### Special tags

| Tag | Meaning |
|-----|---------|
| `main` | Default pattern shown when file is first opened in viewer. |
| `poop` | Hidden from sidebar (excluded at display level). |

## Writing a pattern file

```python
from kumiki import *
from kumiki.patternbook import Pattern, make_pattern_from_joint, make_pattern_from_frame, make_pattern_from_csg

def my_joint(position=None):
    ...  # returns a joint

def my_frame(position=None):
    ...  # returns a Frame

def my_csg_func():
    ...  # returns a CutCSG

patterns = [
    # function returning joint
    Pattern(path="my_category/basic_joint", lambda_=make_pattern_from_joint(my_joint), pattern_type="frame", tags=["main"]),
    # function returning Frame (takes optional position)
    Pattern(path="my_category/frame_example", lambda_=make_pattern_from_frame(my_frame), pattern_type="frame"),
    # function returning CutCSG
    Pattern(path="my_category/csg_shape", lambda_=make_pattern_from_csg(my_csg_func), pattern_type="csg"),
    # inline lambda for list[CutTimber] functions
    Pattern(path="my_category/timber_list", lambda_=lambda center: Frame(cut_timbers=make_timbers(center), name="My Joint"), pattern_type="frame"),
]
```

## Helper constructors

| Helper | Use when function returns |
|--------|--------------------------|
| `make_pattern_from_joint(func)` | A joint object (has `.cuttings`) — wraps into `Frame.from_joints` |
| `make_pattern_from_frame(func)` | A `Frame` directly — calls at origin |
| `make_pattern_from_csg(func)` | A `CutCSG` object — calls with no args |

All three accept functions with an optional `position` argument defaulting to origin.

## Path conventions

- Use `snake_case` segments: `"corner_joints/cut_plain_miter_joint"`
- The last segment becomes the display name in the sidebar
- Path segments are implicit tags (e.g. `"corner_joints"` and `"cut_plain_miter_joint"`)

## Sidebar display

The Kigumi sidebar shows patterns in two modes:

- **Hierarchical** (default): patterns grouped by their source file
- **Flat**: all patterns sorted alphabetically

Patterns tagged `poop` are filtered out of the sidebar entirely. Patterns tagged `main` are raised first when a file is opened.

## PatternLambda signature

```python
PatternLambda = Callable[..., Union[Frame, CutCSG]]
```

The first positional argument must be `center: V3` (the build origin). Additional keyword arguments are allowed.

```python
# Valid lambda:
lambda center, scale=1: my_joint(center, scale=scale)

# Raise a pattern manually:
pattern.raise_at(center=create_v3(0, 0, 0))
# or at origin:
pattern.raise_at()
```

## Existing pattern files

| File | Patterns |
|------|---------|
| `patterns/basic_joints_patterns.py` | 17 — one per basic joint type |
| `patterns/construction_patterns.py` | 12 — join_face_aligned_on_face_aligned_timbers |
| `patterns/patternbook_patterns.py` | 9 — posts, beams, boxes (legacy demo) |
| `patterns/CSG_debug_patterns.py` | 11 — CSG primitives and debug shapes |
| `patterns/butt/plain_butt_joint_patterns.py` | 2 — plain butt |
| `patterns/butt/tongue_and_fork_butt_joint_patterns.py` | 3 — tongue and fork |
| `patterns/butt/dropin_dovetail_butt_joint_patterns.py` | 1 — drop-in dovetail |
| `patterns/butt/dropin_housed_butt_joint_patterns.py` | 1 — drop-in housed |
| `patterns/butt/splined_opposing_double_butt_joint_patterns.py` | 1 — splined opposing double butt |
| `patterns/butt/wedged_half_dovetail_joint_patterns.py` | 1 — wedged half dovetail |
| `patterns/board/board_joints_patterns.py` | 3 — tongue and groove |
| `patterns/corner/plain_miter_joint_patterns.py` | 3 — plain miter |
| `patterns/corner/mitered_and_keyed_lap_joint_patterns.py` | 2 — mitered and keyed lap |
| `patterns/corner/tongue_and_fork_corner_joint_patterns.py` | 2 — tongue and fork |
| `patterns/corner/dovetail_corner_joint_patterns.py` | 2 — dovetail |
| `patterns/corner/plain_corner_lap_joint_patterns.py` | 1 — plain corner lap |
| `patterns/cross/plain_cross_lap_joint_patterns.py` | 2 — house joint, cross lap |
| `patterns/cross/multi_cross_lap_joint_patterns.py` | 0 — stub |
| `patterns/decorative/decorative_joints_patterns.py` | 5 — decorative cuts |
| `patterns/free/free_house_joint_patterns.py` | 0 — stub |
| `patterns/mixed/mortise_and_tenon_joints_patterns.py` | 20 — mortise and tenon variants, including the 37° irrational angle |
| `patterns/splice/half_blind_tenoned_dadoed_rabbeted_scarf_joint_patterns.py` | 2 — half-blind tenoned, dadoed, rabbeted scarf |
| `patterns/splice/lapped_gooseneck_joint_patterns.py` | 1 — lapped gooseneck |
| `patterns/splice/plain_butt_splice_joint_patterns.py` | 1 — plain butt splice |
| `patterns/splice/plain_splice_lap_joint_patterns.py` | 1 — plain splice lap |
| `patterns/onlypoop/relief_example_patterns.py` | 7 — relief cutting at raking angles (development only, tagged `poop`) |

Frames rather than patterns live under `patterns/structures/`, one `example` callable per
file: whole frames (a sawhorse, a shed, the tiny house) rather than single joints.

