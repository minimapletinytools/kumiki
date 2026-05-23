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
from kumiki.joints.workshop.mortise_and_tenon_joint import cut_mortise_and_tenon_joint_on_FAT
```

The top-level `from kumiki import *` re-exports everything from workshop, so existing
patterns don't need to change their import style.

## Stable Joint Requirements

TODO

## Promoting a joint

To promote a joint from `workshop` to stable:

1. Move the file (or the specific function) to `kumiki/joints/`.
2. Update `kumiki/__init__.py` to import from the new location.
3. Leave a deprecation shim in `workshop/` pointing to the new path if any external
   code imports it directly.
