---
applyTo: "girrafecad/**,tests/**"
---

# Kumiki Library Authoring Rules

## Running Tests

Always run all tests after making changes:
```bash
source .venv/bin/activate
python3 -m pytest tests/ -v
```

Always run the type checker after making changes:
```bash
uv run ty check
```

If making changes to the viewer, run viewer tests:
```bash
cd kumiki-viewer && npx jest && node ./test/run-extension-tests.js
```

## Key Files

### girrafecad/timber.py
Core immutable types: `Timber`, `TimberFace`, `TimberLongFace`, `TimberReferenceEnd`, etc. All timber-related geometric operations (axes, size, position). All timber-related core APIs and types live here.

### girrafecad/construction.py
Core construction logic and timber joinery helpers: joining timbers, computing join positions, projecting axes, relationships between multiple members. Canonical location for geometry construction logic beyond simple data definition.

### girrafecad/footprint.py
`Footprint` — key utility class for positioning timbers and cuts.

### girrafecad/joints/*_joints.py
Joints are split into separate files by group.

### girrafecad/rule.py
Math types, units, and math-related utilities. All math code must use these types and helpers.

### girrafecad/measuring.py
Measure/mark pattern for locating features on timbers and marking things relative to features.

## General Coding Philosophy

- Simplicity over performance — straightforward code, minimal indirections through abstract classes
- Clarity over conciseness — the API can be verbose so that what's happening is explicit from the surface
- All data is frozen (immutable); the API should feel like a functional API
  - Python is an implementation detail; this would ideally have been written in a functional language

## General Coding Conventions

- Always use SymPy types (Rational or Float) never Python floats
- Use math types in `rule.py`
- ALWAYS run tests after making changes
- ALWAYS run type checker after making changes

## Coding Conventions when Implementing Joints

Joints involve creating CSG cuts on one or more timbers. A typical joint implementation:

1. Validate input parameters
2. Locate key features (e.g. where the shoulder is for a mortise and tenon cut)
3. Pick a timber to start working on
4. Create a sensible `marking_transform : Transform` on that timber — a transform from which all further calculations are made. May be in local or global coordinates (if local, postfix with `_<timber_name>_local`)
    - e.g. for a tenon cut, `marking_transform` could be where the tenon centerline intersects the tenon shoulder pointing in the tenon direction
    - for marking transforms inside the timber pointing in the length/−length direction, the `+x` axis should line up with the timber's `+x` axis
    - for marking transforms on the surface of the timber, `+y` should point into the timber
5. Calculate positions from `marking_transform` to locate features and generate CSG cuts
6. Repeat steps 3–5 until all cuts are done
7. Return a joint object containing the cuts

Variable naming rules:
- ALWAYS postfix markings in global space with `_global`
- Postfix markings in local space with `_{timber_name}_local`, e.g. `some_feature_timberA_local`
- Omit the postfix only if there is exactly ONE timber in the current scope

Use nested functions to create local variable scopes where helpful (especially to keep naming simple).

## Coding Conventions when Writing Tests for Joints

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

Tests marked with a `# 🐪` have been hand verified to be relevant, never mark tests as `# 🐪` unless user gives the ok. Never delete tests marked with `# 🐪` and be a little more cautious when modifynig them. In contrasts, tests not morked with a `# 🐪` can be deleted and rewritten at will.