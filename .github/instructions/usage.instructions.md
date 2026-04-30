---
applyTo: "patterns/**, experiments/**"
---

# Kumiki Agent Instructions

Copy this file into your project's `.github/copilot-instructions.md` (or `.cursorrules`) to give your AI coding agent context for designing timber frames with Kumiki. Do not copy the applyTo field above.

---

## Imports

Always import via the top-level `giraffe` module:
```python
from giraffe import *
```

## Numeric Values

- **Always use SymPy types (Rational or Float) — never Python floats.**
- Use the `inches()` and `feet()` helpers for imperial measurements:
  ```python
  inches(3)               # 3 inches
  inches(3, 2)            # 3/2 inches = 1.5"
  feet(Rational(7, 2))    # 3.5 feet
  ```
- Use `mm()`, `cm()` and `m()` for metric
- Use `degrees()` and `radians()` for angles
- Use `Matrix([...])` for vectors, always with `Rational` or `Integer` values.

## Philosophy

TODO point to docs

## Creating Timbers

Timbers for a typical structure are usually defined 

- first create a `Footprint` for the footprint of the structure.
- use methods in `footprint.py` to define timbers on the footprint
    - ... TODO
- use methods in `construction.py` to define remaining timbers
    - `join_face_aligned_on_face_aligned_timbers` for connecting timbers at right angles
    - `join_timbers` for simple connections between two timbers
    - `create_axis_aligned_timber` for timbers aligned to cartesian axis
    - `timber_from_directions` for arbitrarily aligned timbers


## Cutting Joints

TODO 

TODO always use joints for basic_joints which provide sensible default parameters if no specifics about the joint were provided

## Combining everything into a Frame

Use `Frame.from_joints` to merge cuts on shared timbers across multiple joints:
```python
frame = Frame.from_joints([joint1, joint2, joint3], name="my_frame")
```

TODO how to actually return the frame for rendering (not through a pattern)

## Creating new Patterns


## General tips
- One dimension of the tenon should be sized to about 1/3 of the thickness of the mortise timber in the axis perpendicular to the the joining axis. This dimensioon should be perpendicular to the length of the mortise timber for strength. The other dimension of the tenon should be about 4/5 of the tenon timber in the matching axis.

