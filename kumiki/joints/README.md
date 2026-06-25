# Joints

This package contains joint construction functions for Kumiki timber frames.

## Structure

```
joints/
├── README.md          ← you are here
├── __init__.py
└── workshop/          ← joints under active development
    ├── basic_joints.py
    ├── build_a_butt.py
    ├── double_butt_joints.py
    ├── japanese_joints.py
    ├── shavings.py
    ├── mortise_and_tenon_joint.py
    └── plain_joints.py
```

## Workshop

All current joints live in `workshop/`. These are **in active development** — their
signatures, geometry, and behaviour may change without notice as the library matures.

Once a joint is considered stable (geometry is correct, API is settled, tests are solid)
it gets promoted up to the `joints/` package directly, where it becomes part of the
stable public API.

**Importing from workshop:**

```python
from kumiki.joints.workshop.basic_joints import cut_basic_butt_joint
from kumiki.joints.workshop.mortise_and_tenon_joint import cut_mortise_and_tenon_joint_on_face_aligned_timbers
```

The top-level `from kumiki import *` re-exports everything from workshop, so existing
patterns don't need to change their import style.

## Stable Joint Requirements
 
- must follow the joint style guide
- must have "descriptive" doc strings
    - what is a descriptive docstring? One high bar might be that it is specific enough that an AI agent should be able to reconstruct the joint function identically from just the docstring. However docstrings should also be written to be easily parseable by impatient humans as well.
- must support "notching", relief cuts such that parts of timber that extend beyond their perfect timber within do not intersect
- must have a patterns for each of its common use scenarios
- must contain at least the following 🐪 tests
    - one parameter validation test
    - one geometry "basic" test testing a "normal" configuration of the joint
    - one geometry test testing different accesory configurtions if allowed (e.g. 0 pegs, multiple pegs)
    - one geometry test testing non face aligned orientations in all axis supported by the joint
    - one geometry test using "extreme" parameter values (typically, 0, or matching/exceeding the the full dimension of the timber) where allowed by parameter validation
    - geometery tests must test points on the joint or boundary
        - for a 🐫 test, the geometery test should be parametric allowing a random range of configurations to be tested in a loop, but this is not a requirement


## Promoting a joint

To promote a joint from `workshop` to stable:

1. Move the file (or the specific function) to `kumiki/joints/`.
2. Update `kumiki/__init__.py` to import from the new location.
3. Leave a deprecation shim in `workshop/` pointing to the new path if any external
   code imports it directly.
