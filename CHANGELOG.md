# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
kumiki and kigumi share a single changelog and always share the same major.minor version;
each entry is split into `kumiki` / `kigumi` subsections where relevant.

## [Unreleased]

### kumiki

#### Added

- Added a `multi_cross_lap_post` structure example that weaves three boards and houses them into a round post.

#### Changed

- **Breaking:** `cut_free_house_joint` now accepts `housed_timbers` as a list and builds one housing cut from all housed bodies.

#### Fixed

- Implemented `cut_multi_cross_lap_joint` to build an ordered chain of cross-lap cuts with global boundary ratio placement.
- Implemented `make_compound_joint` to merge multiple joints while preserving all cuttings/accessories with unique keys.

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
