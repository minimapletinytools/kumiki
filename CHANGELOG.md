# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
kumiki and kigumi share a single changelog and always share the same major.minor version;
each entry is split into `kumiki` / `kigumi` subsections where relevant.

## [Unreleased]

## [0.4.1] - 2026-07-08

### kumiki

#### Added

- Added a `multi_cross_lap_post` structure example that weaves three boards and houses them into a round post.
- Assembly ordering: `Joint.with_order()` assigns frame-level disassembly order to a joint's cuttings/accessories (cut functions author intra-joint sequencing and escape freedoms at cut time). `solve_frame_assembly` and the Kigumi viewer's new assembly timeline drive the resulting step-by-step disassembly sequence.

#### Changed

- **Breaking:** `cut_free_house_joint` now accepts `housed_timbers` as a list and builds one housing cut from all housed bodies.
- **Breaking:** `JointAccessory` renamed to `Accessory`.
  **Migrate:** replace `JointAccessory` references (imports, type hints, subclasses) with `Accessory`.
- **Breaking:** `Accessory.render_csg_local()` renamed to `get_csg_local()`.
  **Migrate:** rename the method in any custom `Accessory` subclass and at call sites.
- **Breaking:** `PerfectTimberWithin.get_perfect_timber_within_CSG_local()` renamed to `get_perfect_timber_within_csg_local()` (casing fix).
  **Migrate:** rename call sites.
- **Breaking:** `timber_from_directions()` renamed to `create_timber()` (now the sole `create_timber`, with `length` as the first positional parameter); the old `kumiki.construction.create_timber()` wrapper (which took `bottom_position` first) was removed.
  **Migrate:** rename `timber_from_directions(...)` calls to `create_timber(...)`; if you called the old `construction.create_timber(bottom_position, length, ...)` positionally, switch to keyword arguments or reorder to `create_timber(length, size, bottom_position, ...)`.
- **Breaking:** `kumiki.joints.workshop.shavings.notching` module renamed to `kumiki.joints.workshop.shavings.relief`; `ShoulderNotchCSGGeometry` renamed to `ShoulderReliefCSGGeometry`, `chop_notch_for_butt_joint_arrangement` renamed to `chop_relief_for_butt_joint_arrangement`.
  **Migrate:** update imports and call sites to the `relief` module and renamed symbols.
- **Breaking:** joint/arrangement validation (`require_check`) now raises `KumikiArrangementError` (a `ValueError` subclass) instead of `AssertionError`.
  **Migrate:** catch `KumikiArrangementError` (or `ValueError`) instead of `AssertionError` around joint/arrangement construction.
- Arrangement classes (`ButtJointTimberArrangement` and friends) no longer validate field types at construction; rely on static type checking instead of a runtime error for wrong-typed fields.

#### Fixed

- Implemented `cut_multi_cross_lap_joint` to build an ordered chain of cross-lap cuts with global boundary ratio placement.
- Implemented `make_compound_joint` to merge multiple joints while preserving all cuttings/accessories with unique keys.
- CSG boundary and containment checks (`HalfSpace`, `RectangularPrism`, `Cylinder`, `ConvexPolygonExtrusion`, and CSG-tree normal averaging) now consistently use tolerance-aware comparisons instead of exact equality, fixing false negatives near boundaries in float mode.
- `BoundingBox` gained an `is_empty` flag so an empty CSG result (`EmptyCSG`, a fully-consumed `Difference`, an all-empty `SolidUnion`) is no longer mistaken for a real zero-size box at the origin; the same bug was fixed in `SolidUnion`, `Intersection`, `Difference`, and the halfspace bounding-box-clip helper.
- Fixed an undefined-name bug (`Integer`) in `Timber.is_face_perfect`.
- `safe_normalize_vector`'s float-mode path now returns `Float` components directly instead of round-tripping through `Fraction.limit_denominator` to an approximate `Rational`, removing an unnecessary precision-lossy step.

#### Removed

- **Breaking:** `get_point_on_face_global` removed (was a deprecated alias); use `get_center_point_on_face_global` instead.
- Removed the unused internal `rendering_utils.py` module (FreeCAD/Fusion360-era, not part of the public API).

### kigumi

#### Added

- Assembly timeline: drive and step through a frame's solved disassembly sequence in the viewer.

#### Fixed

- Fixed `kigumi.updateKumiki` failing its version-compatibility check when a local dev install (`v.999`) was present, blocking updates.

## [0.4.0] - 2026-07-02

### kumiki

#### Added

- `attach_timber`, `attach_face_aligned_timber`, and `attach_plane_aligned_timber` for attaching
  a new timber to an existing one by direction, face, or angled plane.
- `attach_face_aligned_timber` / `attach_plane_aligned_timber` can now extend a timber directly to
  another target timber (instead of only a fixed numeric length), touching the target's centerline
  or the near/far boundary of its projected silhouette.
- `TimberEnd` (renamed from `TimberReferenceEnd`).

#### Changed

- **Breaking:** `attach_face_aligned_timber` / `attach_plane_aligned_timber` parameter
  `attached_timber_length` renamed to `attached_timber_length_or_target` (now accepts either a
  numeric length or a target timber).
  **Migrate:** rename the keyword argument at call sites; behavior is unchanged when passing a
  numeric value.
- **Breaking:** `attach_face_aligned_timber` / `attach_plane_aligned_timber` parameter
  `attached_timber_opposite_length` replaced by `attached_timber_stickout: Stickout`.
  **Migrate:** `attached_timber_opposite_length=x` becomes `attached_timber_stickout=Stickout(x)`.
- **Breaking:** `TimberReferenceEnd` renamed to `TimberEnd`.
  **Migrate:** replace all references to `TimberReferenceEnd` with `TimberEnd`.

#### Removed

- Removed the unused FreeCAD and Fusion360 renderer/export code.

### kigumi

#### Fixed

- Fixed install script.

#### Added

- Footprint rendering and footprint patterns.
