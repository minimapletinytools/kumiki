# Pattern System

## Overview

A pattern file marks each of its patterns with `@pattern`, directly above the function that builds it. The Kigumi viewer scans these files and lists the patterns in its sidebar.

## Writing a pattern file

```python
from typing import Optional
from kumiki import *

ROUND_STOCK = kiwari(round_timbers=kiwari.flag(False, about="Use round timbers"))


@pattern("my_category/basic_joint", tags=["main"])
def basic_joint(position=None) -> Joint:
    ...  # returns a joint


@pattern("my_category/round_or_square", kiwari=ROUND_STOCK)
def round_or_square(k: Optional[Kiwari] = None) -> Frame:
    k = ROUND_STOCK.resolve(k)
    ...  # returns a Frame, using k.flag("round_timbers")


@pattern("my_category/csg_shape", tags=["poop"])
def csg_shape() -> CutCSG:
    ...  # returns a CutCSG
```

`@pattern(path, tags=[...], kiwari=...)`:

| Argument | Description |
|----------|-------------|
| `path` | Required. Hierarchical, like `"category/name"`. Each segment is an implicit tag. |
| `tags` | Optional. See special tags below. |
| `kiwari` | Optional. The numbers this pattern can be adjusted by in Kigumi's parameters panel. Each pattern declares its own. |

The function is checked when the file is loaded, and one that doesn't fit is skipped with the reason:

- It takes `(k: Kiwari)` if the pattern declares a kiwari (`Optional[Kiwari]` is fine), and nothing otherwise. Further parameters are allowed if they have defaults, such as `position=None`.
- Its return annotation is `Joint`, `Frame` or `CutCSG`. A joint is shown as a frame of its timbers; a `CutCSG` makes it a CSG pattern.

The decorator only marks the function, so it is still an ordinary function to call from a script or a test.

A file with `@pattern` functions is a pattern book: any `@frame` functions in it are not shown.

### Special tags

| Tag | Meaning |
|-----|---------|
| `main` | Default pattern shown when file is first opened in viewer. |
| `poop` | Hidden from sidebar (excluded at display level). |

## Path conventions

- Use `snake_case` segments: `"corner_joints/cut_plain_miter_joint"`
- The last segment becomes the display name in the sidebar
- Path segments are implicit tags (e.g. `"corner_joints"` and `"cut_plain_miter_joint"`)

## Sidebar display

The Kigumi sidebar shows patterns in two modes:

- **Hierarchical** (default): patterns grouped by their source file
- **Flat**: all patterns sorted alphabetically

Patterns tagged `poop` are filtered out of the sidebar entirely. Patterns tagged `main` are raised first when a file is opened.

## Raising a pattern from code

`kumiki.frame_decorators.module_patterns(module)` gives a module's patterns as `Pattern` objects, in source order:

```python
patterns, rejected = module_patterns(my_pattern_module)
patterns[0].raise_at()  # at the origin
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

