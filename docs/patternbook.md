# Writing pattern files

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

### Where a pattern is built

A pattern function is not given a position. Kigumi always builds it at the origin, and `pattern.raise_at(center)` moves the result to `center` afterwards (the grid view uses this to lay patterns out side by side).

A builder may still take an optional `position` so a script or a test can place it, as long as it defaults to the origin -- Kigumi never passes it. With a kiwari, `k` comes first and `position` after it, ideally keyword-only:

```python
@pattern("my_category/basic_joint")
def basic_joint(position=None) -> Joint:
    position = position if position is not None else create_v3(0, 0, 0)
    ...


@pattern("my_category/round_or_square", kiwari=ROUND_STOCK)
def round_or_square(k: Optional[Kiwari] = None, *, position=None) -> Joint:
    ...
```

A function that needs a position with no default, like `make_timbers(center)`, is wrapped in a pattern that calls it at the origin:

```python
@pattern("my_category/timber_list")
def timber_list() -> Frame:
    return Frame(cut_timbers=make_timbers(create_v3(0, 0, 0)), name="My Joint")
```

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

Which joint suits which job, with the pattern file to start from for each, is in `api_cheat_sheet.md` ("Which joint for the job").

Joint pattern categories mirror `kumiki/joints/workshop/`: `board`, `butt`,
`corner`, `cross`, `decorative`, `free`, `mixed`, and `splice`. Basic recipes live
under `basic_joints`. A folder is only a folder; its leaf paths identify variants.

Use Kiwari for dimensions, positions, notching, and peg shapes. Keep separate
variants for different timber angles, alignment requirements, through/stopped
mortises, and through/half-blind dovetails. The pattern source is the reference
for the exact geometry and API call.


Frames rather than patterns live under `patterns/structures/`, one `example` callable per
file: whole frames (a sawhorse, a shed, the tiny house) rather than single joints.

