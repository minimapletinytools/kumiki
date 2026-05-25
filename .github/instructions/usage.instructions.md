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

As a primer before working with Kumiki, pleaes see docs/concepts.md for an overview of the core concepts and philosophy behind Kumiki's design.

## Creating Timbers

Timbers for a typical structure are usually defined 

- first create a `Footprint` for the footprint of the structure.
- then use methods in `footprint.py` to define timbers directly on the footprint (touching the ground)
    - `create_horizontal_timber_on_footprint`
    - `create_vertical_timber_on_footprint`
- use methods in `construction.py` to define remaining timbers based on existing timbers
    - `join_face_aligned_on_face_aligned_timbers` for connecting timbers at right angles
    - `join_timbers` for simple connections between two timbers
    - `create_axis_aligned_timber` for timbers aligned to cartesian axis
    - `timber_from_directions` for arbitrarily aligned timbers

## Cutting Joints

Once timbers have been laid out, use the various `cut_*` methods to cut joints joining the timbers. There are many types of joints. 

Almost all joints have a `cut_basic_*` variation inside of basic_joints.py which take minimal parameters. Always use the basic variants until the user provides specific requirements.

### finding joint parameters

Joint parameters are always set relative to one of the features on one of the timbers in the arrangement. Oftentimes the user will want to set the parameter relative to some other feature. Use the methods in measuring.py to convert measurements between features.

### default joints for generic designs

If the user does not specify which joint, use the following (or one of its variants) as defaults:

- for butt joints use cut_mortise_and_tenon_joint
- for corner joints use cut_plain_miter_joint or cut_plain_corner_lap_joint
- for splice joint use cut_plain_splice_lap_joint_on_aligned_timbers
- for cross joints use cut_plain_cross_lap_joint

### default joints for timber frames

- for beam-to-post joints use cut_mortise_and_tenon_joint, with a peg if the beam butts into the post, and without a peg if the beam sits above the post
- for tie-beams or beams under substantial loads, consider using cut_wedged_half_dovetail_mortise_and_tenon_joint instead as it's much stronger
- for rafter-to-rafter joints use cut_tongue_and_fork_corner_joint
- for mudsill splice joints use cut_lapped_gooseneck_joint with the gooseneck facing upwards
- for mudsill corner joints use either 
    - cut_plain_corner_lap_joint (simplest)
    - cut_mortise_and_tenon_joint (more complicated)
    - cut_mitered_and_keyed_lap_joint (most complicated, no end grain exposed)
- for joist-to-beam or joist-to-mudsill joints use 
    - cut_dropin_housed_butt_joint (simplest)
    - cut_housed_dovetail_butt_joint (if joist needs to resist spreading forces)

## Combining everything into a Frame

Your file should typically have some `example` function that returns a Frame

Use `Frame.from_joints` to merge cuts on shared timbers across multiple joints. 

```python
def example():
    # establish footprint
    # create timbers
    # create joints
    # merge into. aframe and return the results
    return Frame.from_joints([joint1, joint2, joint3], name="my_frame")
```

The `example` function name is special, it is what kigumi will scan for and render when opening your file.

# Creating new Patterns

TODO



