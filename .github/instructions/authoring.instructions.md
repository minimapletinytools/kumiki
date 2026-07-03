---
applyTo: "kumiki/**,tests/**"
---

# Kumiki Library Authoring Rules

## Running Tests

For Python library changes in `kumiki/**` or `tests/**`, always run:
```bash
source .venv/bin/activate
python3 -m pytest tests/ -v
```

Then always run type checking:
```bash
uv run ty check
```

For Kigumi changes in `kigumi/**`, always run the fast baseline tests:
```bash
cd kigumi && npx jest && npm run test:ext:initial
```

If your Kigumi change touches a specific feature area, also run relevant complex tests (targeted when possible):
```bash
cd kigumi && npm run test:ext:complex:grep -- "<feature or test name>"
```

Run the full complex suite before merging broader Kigumi changes:
```bash
cd kigumi && npm run test:ext:complex
```

## Key Files

### kumiki/timber.py
Core immutable types: `Timber`, `TimberFace`, `TimberLongFace`, `TimberEnd`, etc. All timber-related geometric operations (axes, size, position). All timber-related core APIs and types live here.

### kumiki/construction.py
Core construction logic and timber joinery helpers: joining timbers, computing join positions, projecting axes, relationships between multiple members. Canonical location for geometry construction logic beyond simple data definition.

### kumiki/footprint.py
`Footprint` — key utility class for positioning timbers and cuts.

### kumiki/joints/*_joints.py
Joints are split into separate files by group.

### kumiki/rule.py
Math types, units, and math-related utilities. All math code must use these types and helpers.

### kumiki/measuring.py
Measure/mark pattern for locating features on timbers and marking things relative to features.

## Understanding Kumiki

Please see docs/concepts.md to understand the core concepts and architecture of Kumiki.

## General Coding Philosophy

- Simplicity over performance — straightforward code, minimal indirections through abstract classes
- Clarity over conciseness — the API can be verbose so that what's happening is explicit from the surface
- All data is frozen (immutable); the API should feel like a functional API
  - Python is an implementation detail; this would ideally have been written in a functional language

## General Coding Conventions

- Use math types in `rule.py`
- ALWAYS run tests after making changes
- ALWAYS run type checker after making changes
- For Kigumi, ALWAYS run the fast baseline suite first, then add targeted complex tests when the touched feature requires it

## Coding Conventions for Authoring Joints

Joints involve creating CSG cuts on one or more timbers. A typical joint implementation:

1. Validate input parameters
2. Locate key features (e.g. where the shoulder is for a mortise and tenon cut)
3. Pick a timber to start working on
4. Optionally, create a sensible `marking_space : MarkingSpace` on that timber — a transform from which further calculations can be made from. May be in local or global coordinates (if local, postfix with `_<timber_name>_local`)
    - e.g. for a tenon cut, `marking_space` could be where the tenon centerline intersects the tenon shoulder pointing in the tenon direction
    - for marking spaces inside the timber pointing in the length/−length direction, the `+x` axis should line up with the timber's `+x` axis
    - for marking spaces on the surface of the timber, `+y` should point into the timber
5. Calculate parameters to generate CSG cuts, either from global features, or locally relative to `marking_space`
    - it is often useful to convert back and forth from global and local coordinates. Make sure local coordinates are always clearly marked with the `<timber_name>_local` postfix to avoid confusion
    - there are many helper methods to do this, please see other joints for examples
6. Repeat steps 3–5 until all cuts are done
7. Add notch cuts--in most casees, the standard notching pattern for the arrangement will be sufficient (see notching pattern below)
8. If the joint is at the end of any one of the timbers, set `maybe_top/bottom_end_cut_distance_from_bottom` for that timber to allow the proper rough end cuts to be generated
9. Return a joint object containing the cuts

### Joint Style Guide

Function naming rules:
- all joint functions are prefixed with cut_*
- TODO arrangement invariant naming rules

Argument rules:
- the retun type of all cut_ functions should be `Joint`
- the first argument should always be an `arrangement: Arrangement` object containing all the timbers and parameters for the joint.
- the last argument should alwasy be the notching configuration object IF notching is supported

Variable naming rules:
- ALWAYS postfix markings in global space with `_global`
- Postfix markings in local space with `_{timber_name}_local`, e.g. `some_feature_timberA_local`
- Omit the {timber_name} postfix only if there is exactly ONE timber in the current scope

Use nested functions to create local variable scopes where helpful (especially to keep naming simple).

### Assertions

In general, any assumption or constraint on the input parameters should be asserted with an informative error message. 
The arrangement classes have several built in checks to help with this. 

### the notching pattern

A notch is a cutout timbers in a joint to create clearance. 

Notching timbers is needed such that timbers that extend beyond their perfect timber within (imperfect timbers) can be joined together consistently without collision. It is also used when insetting a timber into the face of another timber. Almost all joints will need notching.

The `notching.py` file contains sets of notching utility methods including a set of scribe-based notching utilities that should work for almost all joints.

Joints should only notch if necessary (i.e. input timber is imperfect or there is an inset) to avoid CSG bloat.

### the build-a-butt-joint-pattern

Butt joints typically compose of 

- some "tenon" like insertion on the butt timber that inserts into some "mortise" like hole in the receiving timber.
- some shoulder pattern between the butt and receiving timber.
- accessories to complete the joint

These can sometimes be interchanged. The `build-a-butt.py` file deconstructs these operations so they can be composed to build a variety of butt joints. Butt joints should make use of build-a-butt whenever possible.

### pegging

Pegs (AKA draw bores, komisen) are often used in mortise-and-tenon-like joints to tighten the joint. Pegs may be positioned generically for most butt joints based on where the tenon centerline meets joint shoulder using the `compute_peg_positions` function in `build_a_butt.py`.

### Testing Joints

Each joint must have at least one "general" test that:

1. Creates the joint with normal parameters
2. Validates the joint object (right number of cuts, right accessory types, etc.)
3. Picks key points on key features and tests that those points are/are not contained in cut timbers or on their boundary
    - Often done by picking a line through the joint and testing points along it
4. Where appropriate, inspects the returned CSG objects to verify specific cuts (e.g. a `HalfSpace` matching the shoulder)

Additional tests (not required but encouraged):

1. Loop over multiple normal configurations (different timber orientations) — always generalize check functions
2. Test specific parameter effects
3. Test that invalid configurations raise errors
4. Test degenerate / edge cases (e.g. tenon length of 0)

Do not write too many tests that aren't actually testing geometry. We want quality over quantity. Look for tests marked with `# 🐪` for examples of good tests. In particular, look at the ones in `test_plain_joints.py`

Tests marked with a `# 🐪` have been hand verified to be relevant, never mark tests as `# 🐪` unless the user gives the ok. Never delete tests marked with `# 🐪` and be more cautious when modifying them. In contrast, tests not marked with a `# 🐪` can be deleted and rewritten.


## Authoring Patterns and Example Frames

Patterns are simple examples demonstrating joints or other deconstruted concepts in Kumiki. They are intended to be used as a reference source.

- pattern should always use canonical arrangement in example_shavings.py when possible. 
- each joint should have at least one pattern
- if a joint has multiple patterns, they should all be in a subfolder named after the joint

Kumiki also ships with a few example Frames that demonstrate how to put everything together. In general, follow agent_usage_instructions.md for authoring patterns and example frames.

### How patterns and frames get discovered

The librarian (`kumiki/librarian.py`) scans source files to find patterns and frame examples without importing them. In short: a module-level `patterns = [...]` list is how patterns are found, and a module-level `example` (or `build_frame`) — ideally, but not strictly required to be, annotated `-> Frame` — is how frame examples are found. See the module docstring in `kumiki/librarian.py` for the exact detection rules and how the pattern-index cache works.