# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
kumiki and kigumi share a single changelog and always share the same major.minor version;
each entry is split into `kumiki` / `kigumi` subsections where relevant.

## [Unreleased]

## [0.4.10] - 2026-08-22

### kumiki

#### Added

- Added a general path/arc extrusion CSG system in `kumiki/pathcsg.py`: `FancyPath` (a closed loop of `LineSegment`/`ArcSegment` pieces; `Path` is kept as an alias) and `PathExtrusion`, which extrudes an arbitrary, not-necessarily-convex 2D path along Z, with mesh (`decompose_path_into_convex_pieces`) and OCP export support. Now re-exported from the top-level `kumiki` package (`import kumiki; kumiki.FancyPath(...)`), previously only reachable via `kumiki.pathcsg`.
- Added `TimberShortEdge` (the 8 end-corner short edges, e.g. `TOP_BACK`), with `TimberFeature.short_edge()` / `TimberEdge.short_edge()` / `TimberEdge.long_edge()` conversions and a new `locate_short_edge` measuring helper. `mark_distance_from_corner_along_edge_by_intersecting_plane` / `_by_finding_closest_point_on_line` now also accept a `TimberShortEdge`.
- Implemented `cut_practice_path_extrusion_corner_end_decoration(timber, cut_corner, cut_path)`: cuts an arbitrary line/arc profile out of a timber's end corner (generalizing the rafter-tail scallop's single circular arc to any path), extruded across the timber's full rough width and subtracted.

#### Changed

- **Breaking:** Scalar values (`scalar()`, `inches()`, `feet()`, `mm()`, `cm()`, `m()`, `shaku()`, `sun()`, `bu()`, `degrees()`, `radians()`, and any arithmetic derived from them) are now plain Python `float` instead of sympy `Rational`/`Expr`. This removes sympy's exact-rational arithmetic entirely -- along with the substantial per-operation overhead of sympy's expression-construction pipeline it required -- in favor of ordinary double-precision floats. `Matrix` is no longer `sympy.Matrix`: it's a new, lightweight numpy-backed class supporting the same construction/indexing/multiplication semantics (`*` is matrix-multiply, not elementwise), but it is now immutable (`some_matrix[i, j] = x` raises `TypeError`) and no longer has a `.copy()` method (unnecessary once immutable). `Rational` is no longer importable from `kumiki.rule`.
  **Migrate:** Replace `isinstance(x, Rational)` checks with `isinstance(x, float)`. Replace any in-place `Matrix`/vector mutation with constructing a new one (e.g. `create_v3(...)`, `Matrix([...])`). Any code comparing computed values for exact equality (`a == b`) should switch to `safe_equality_test`/`safe_zero_test`, since float arithmetic can differ from the mathematically exact result by machine epsilon where exact rational arithmetic previously could not.
- **Breaking:** `cut_practice_rafter_tail_scallop_decoration` is renamed to `cut_practice_rafter_tail_scallop_corner_end_decoration`, and its `end_side: TimberEnd` / `cut_side: TimberLongFace` parameters are replaced by a single `short_edge: TimberShortEdge` parameter.
  **Migrate:** rename the call, and combine the old two args into the corresponding `TimberShortEdge` (e.g. `end_side=TimberEnd.TOP, cut_side=TimberLongFace.BACK` becomes `short_edge=TimberShortEdge.TOP_BACK`); a plain `TimberEdge` is also accepted and auto-converted.

#### Fixed

- Fixed `cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers` (Kanawa Tsugi joint): the center peg-hole geometry was wrong -- one side of the joint drew its vertical line to the hole's far corner while the other drew to the near corner, leaving a non-square hole. The vertical lines are now both tilted correctly to keep the hole square, and the Kusabi peg accessory is now tilted to match the scarf angle (previously left un-rotated, no longer matching the actual cut).
- Fixed `solve_assembly`'s simultaneous-step search (used for interlocked/radial disassembly sequences) to check cancellation throughout its heuristic seed search rather than only between top-level candidates, so a cancelled solve aborts immediately instead of running to completion first. Also capped the heuristic seeds tried per component -- the search's cost scaled with the number of scheduled coordinates and could dominate solve time on complex components.

### kigumi

#### Added

- Added three new viewer background themes ("Bloom", "Tide", "Sunbeam") using a new soft radial-gradient "blobs" background pattern, localized in English and Japanese.

#### Changed

- The viewer's default edge display mode changed from "overlay" to "no overlay".

#### Fixed

- Fixed the right-click face picker mislabeling faces on any CSG sub-feature built in its own local coordinate frame -- e.g. a tusked mortise-and-tenon's tenon tip at a BOTTOM-end joint reported "top" instead of "tenon_bot". The picker now prefers the feature's own declared name when one exists, and otherwise re-projects the matched face's normal into the timber's own six canonical directions instead of reusing the sub-feature's incidental local-frame label.

## [0.4.9] - 2026-08-15

### kumiki

#### Added

- Added `CutTimber.from_joints(timber, joints)`: builds a `CutTimber` by collecting every `Cutting` across a list of `Joint`s whose `.timber` is that exact timber (matched by identity, the same rule `Frame.from_joints` uses). Lets joint functions that need "this timber's actual body so far" (e.g. `cut_free_house_joint`'s `housed_timbers`) do so without hand-picking a `Joint.cuttings["timberA"/"timberB"]` key, which is easy to pair with the wrong timber.
- Added a rounded-end decorative cut: `cut_practice_rounded_end_decoration(timber, rounded_face, rounded_end, radius, distance_from_end, lateral_offset=0)`. Carves a single large-radius arc across the full width perpendicular to `rounded_face`/`rounded_end` -- a gentle bowed/bullnose end profile. `distance_from_end == radius` is tangent at the lateral center and recedes toward the corners (a continuous corner-to-corner bulge); less than `radius` leaves the center flat with only the corners filleted (a warning is raised in that case).
- Added `notch_from` (`NotchFrom.Shoulder | NotchFrom.Face`) to `ButtJointNotchReliefConfig`: `cut_mortise_and_tenon_joint_on_plane_aligned_timbers` / `_on_face_aligned_timbers` can now anchor the 2-sided notch relief to the mortise's entry face instead of the real (possibly inset) shoulder. Replaces the internal-only `DisableInsetShoulderNotchingReliefConfig` with a general `shoulder_relief_style` param (`None | Rough | PerfectOnly`) on `cut_mortise_and_tenon_joint`. Added `chop_rough_relief_on_long_faces_beyond_shoulder_plane` (`relief.py`) to trim the tenon's own rough-stock excess near the shoulder, which a tight `PerfectOnly` pocket no longer covers.
- Added a "coffee table" structure example (`patterns/structures/coffee_table.py`).
- `attach_plane_aligned_timber` / `attach_face_aligned_timber` now auto-flip `original_timber_long_face_that_attached_timber_points_to` to the opposite long face (with a warning) if the requested orientation would produce a non-positive attached-timber length, only raising the original assertion if both directions fail.

#### Changed

- **Breaking:** `export_cut_timber_stl` / `export_cut_timber_step` / `export_frame_stl` / `export_frame_obj` / `export_frame_3mf` (and the STEP frame export) gained a keyword-only `local: bool = True` parameter. Per-part files are now exported in each part's own local coordinates (bottom at the origin) by default, rather than always in global (assembled) coordinates; a `combined` merged file, when requested, is still always global.
  **Migrate:** pass `local=False` at call sites that relied on the old always-global behavior for individual part files.
- Removed the deprecated `normalize_vector` / `zero_test` (and `vector_magnitude` / `equality_test`) aliases from `rule.py`; all call sites across `kumiki/`, `patterns/`, and `tests/` now use `safe_normalize_vector` / `safe_zero_test` directly.
- Removed the broken `CSG_debug_patterns.py` example patterns.

#### Fixed

- Fixed `cut_free_house_joint`: the housed timber's body was built from its raw, un-extended box, so an end cut whose plane is skewed (e.g. a miter) -- where one corner of the cross-section reaches past the timber's own un-extended origin -- had that corner chopped off flat in the housing relief instead of leaving room for the full pointed tip. Now built from the same extended-then-cut body `CutTimber.render_timber_with_cuts_csg_local` already uses for rendering.

### kigumi

#### Added

- Added two new geometry render modes to the viewer's geometry dropdown: "perfect box (no joints)" and "rough box (no joints)" -- a plain rectangular box (no CSG joint cuts at all) sized to the timber's perfect or rough cross-section, cropped in length by the frame's aggregated end-cut trims. The existing "actual" mode is relabeled "rough (actual geometry)" for clarity against the new rough/perfect distinction.
- Added a right-click context menu on a timber (in 3D space or the timber list) with "export as stl" / "export as step", exporting just that one member.
- Added an orthographic/perspective camera projection toggle to the viewer.
- Added a folder watcher that automatically refreshes the Kigumi sidebar when new `.py` files are created in the workspace, gated by the `kigumi.sidebar.autoRefreshOnNewFile` setting (default on).

#### Fixed

- Fixed the right-click face picker reporting the wrong face name for the FRONT/BACK faces (a swapped-label bug in `_detect_face_label`).

## [0.4.8] - 2026-08-10

### kumiki

#### Added

- Added a corner (right-angle) mortise-and-tenon joint: `cut_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers`. `tenon_distance_from_end` positions the tenon along the joint-plane axis from the mortise timber's end face (0 = flush/exposed, i.e. equivalent to a tongue-and-fork corner joint); `tenon_lateral_offset` offsets it perpendicular to the joint plane. Each timber's stock is automatically end-cut flush with the other's outer face at the corner.
- Added `ButtJointNotchReliefConfig` (an alternative to `ButtJointScribeReliefConfig`) for `cut_mortise_and_tenon_joint` / `cut_mortise_and_tenon_joint_on_plane_aligned_timbers` / `cut_mortise_and_tenon_joint_on_face_aligned_timbers`: relieves only the material near an inset shoulder via a lofted frustum notch (4-sided in the general case, a cheaper 2-sided flat/flared form when the arrangement is plane-aligned) instead of scribing each timber's whole imperfect body onto the other.
- Added `ConvexPolygonSimpleLoft` CSG primitive (`kumiki/cutcsg.py`): a straight-line loft between two arbitrary index-matched convex polygons, with mesh and OCP export support -- the basis for the new notch-relief geometry above.
- `cut_mortise_and_tenon_joint_on_plane_aligned_timbers` / `cut_mortise_and_tenon_joint_on_face_aligned_timbers` gained `tenon_width_relative_to_joint` / `tenon_height_relative_to_joint`, sizing the tenon relative to the shared joint plane (width = parallel to it, height = perpendicular) instead of the tenon timber's raw local X/Y axes. Provide these two together, or `tenon_size` (now optional), not both.
- `cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers` / `cut_basic_tongue_and_fork_butt_joint_on_plane_aligned_timbers` gained `shoulder_inset`, and the tongue timber now gets a proper housing/shoulder cut when the shoulder is inset from its entry face (previously only the two cheek cuts were made, with no shoulder housing at all).

#### Changed

- **Breaking:** In `cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers` / `cut_basic_tongue_and_fork_butt_joint_on_plane_aligned_timbers`, `arrangement.butt_timber` and `arrangement.receiving_timber` swapped roles: `butt_timber` is now the fork (was the tongue) and `receiving_timber` is now the tongue (was the fork), matching how every other butt joint in this library assigns roles. The fork timber's end cut and slot depth were also fixed to correctly extend to the furthest tip for angled (non-perpendicular) joints, rather than just the centerline intersection.
  **Migrate:** swap which timber you pass as `butt_timber` vs. `receiving_timber` at call sites.
- **Breaking:** `tenon_size` is now optional and moved after `tenon_length` in `cut_mortise_and_tenon_joint_on_plane_aligned_timbers` / `cut_mortise_and_tenon_joint_on_face_aligned_timbers`'s parameter order (to make room for the new relative-sizing pair above).
  **Migrate:** pass `tenon_size` by keyword, or reorder positional args.
- `mortise_and_tenon_joints.py` split out of `butt_joints.py` into its own module. All functions are still re-exported from the top-level `kumiki` package, so `import kumiki; kumiki.cut_mortise_and_tenon_joint(...)` is unaffected -- only direct submodule imports (`from kumiki.joints.workshop.butt_joints import cut_mortise_and_tenon_joint`) need updating to `kumiki.joints.workshop.mortise_and_tenon_joints`.
- Cleaned up example pattern paths under `butt_joints/mortise_and_tenon/`, dropping a redundantly repeated `mortise_and_tenon_` prefix from leaf names (e.g. `mortise_and_tenon/mortise_and_tenon_double_angled` -> `mortise_and_tenon/double_angled`); removed the superseded `example_basic_mortise_and_tenon` and `example_mortise_and_tenon_45_degree_relative_tenon_size` patterns.

#### Fixed

- Fixed `chop_butt_joint_shoulder_notch_relief_4sided`'s dihedral-angle bisector: it used `Abs()` on the signed face-to-shoulder angle (making any two opposite faces always report an identical relief angle, even under a compound-angle approach where they genuinely differ) and had the reach/depth relationship along the bisector inverted. Both are fixed together (signed angle, `reach = depth * tan(dihedral / 2)`), verified by checking the actual tenon geometry stays fully cleared at every depth.
- Fixed `chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided` with the same signed-angle/reach-depth fix (computed per side instead of from one shared value), and:
  - quad-1's flared-axis extent now accounts for the oblique stretch where the tenon's perfect cross-section actually crosses the shoulder plane (previously used the un-stretched raw half-size, understating it for any raking approach).
  - the flat-axis boundary now reaches the FURTHER of both timbers' own rough edges (previously the receiving timber's perfect edge only), guaranteeing the relief is a full transverse cut across the receiving timber's entire width rather than a pocket that could stop partway across it.

#### Deprecated

- `chop_shoulder_notch_aligned_with_timber`, `chop_shoulder_notch_on_timber_face`, and `chop_relief_for_butt_joint_arrangement` (in `kumiki.joints.workshop.shavings.relief`) are marked for future removal, superseded by `chop_butt_joint_shoulder_notch_relief_4sided` / `chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided`. No deprecation warning emitted yet -- these still work as before.

## [0.4.7] - 2026-08-04

### kumiki

#### Added

- Added a tusked (keyed) through mortise-and-tenon joint: `cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers` (plus a `cut_basic_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers` convenience wrapper and pattern examples). The tenon's length is derived from an "opposite shoulder" reference on the far side of the receiving timber (`MeasureOppositeShoulderFrom` selects whether that's measured against the timber's perfect or rough boundary, with an optional `opposite_mortise_shoulder_inset`), and a tapered crosswise key (`TuskParameters`, entering from `TuskEntryFace.Front` or `.Top`, flush against the opposite shoulder plane on one side like the dovetail wedge) locks the joint, with a matching clearance cut automatically added to the receiving timber when its rough stock would otherwise block the key's slide-in path.

#### Changed

- **Breaking:** `cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers` no longer takes a separate `dovetail_top_side_on_butt_timber` parameter.
  **Migrate:** set `arrangement.top_face_on_butt_timber` instead.
- **Breaking:** renamed the "nominal size" (rough/as-sawn stock boundary) concept to "rough" throughout the timber sizing API -- "nominal" collided with the opposite meaning used in standard lumber terminology (a "2x4" is nominally 2"x4" but dressed/actual size is smaller). `Timber.nominal_half_sizes` / `Timber.from_perfect_timber_within(nominal_half_sizes=...)` are renamed to `rough_half_sizes`; `kumiki.timber_shavings.get_nominal_support_distance_from_centerline` / `get_nominal_support_distance` are renamed to `get_rough_support_distance_from_centerline` / `get_rough_support_distance`; `does_shoulder_plane_need_notching`'s `check_against_nominal_size` and `chop_relief_for_butt_joint_arrangement`'s `use_receiving_timber_nominal_size_for_butting_timber_relief_depth` are renamed to their `rough` equivalents; `kumiki.example_shavings.CanonicalSquareNominalHalfSizes` / `NominalTimberConfig` are renamed to `CanonicalSquareRoughHalfSizes` / `RoughTimberConfig`. None of these have compatibility shims.
  **Migrate:** rename call sites accordingly (`nominal` -> `rough`).
- `ButtJointTimberArrangement.check_plane_aligned()` now also requires `top_face_on_butt_timber` (when set) to not be parallel to the joint alignment plane; `check_face_aligned_and_orthogonal()` gained the same check. Previously neither method validated `top_face_on_butt_timber` at all, and only `check_plane_aligned()` validated `front_face_on_butt_timber`.
- **Breaking:** renamed two `DovetailTenonWedgeAccessoryParameters` fields for clarity: `wedge_tip_extra_length` -> `wedge_tip_stickout` (matching the `Stickout` terminology used elsewhere), and `wedge_base_extra_length` -> `wedge_back_extra_length`. No compatibility shim.
  **Migrate:** rename these two keyword arguments at any `DovetailTenonWedgeAccessoryParameters(...)` call site.

#### Deprecated

- `PerfectTimberWithin.get_nominal_half_sizes` / `get_nominal_size` / `get_nominal_size_in_face_normal_axis` / `get_half_nominal_size_in_face_normal_axis`, in favor of `get_rough_half_sizes` / `get_rough_size` / `get_rough_size_in_face_normal_axis` / `get_half_rough_size_in_face_normal_axis` (same rough/nominal rename as above). Unlike the renames above, these specific methods keep working -- they emit a `DeprecationWarning` and forward to the new names.

## [0.4.6] - 2026-07-31

### kigumi

#### Added

- Added localization support (English/Japanese, auto-detected from VS Code's display language) across the viewer webview, sidebar, and package.json contributions. No manual language override yet.
- Round accessories and timbers (pegs, dowels) now render two camera-facing silhouette lines tracing their true tangent outline, since `EdgesGeometry`'s fixed dihedral-angle threshold never picks up a cylinder's faceted barrel (only its flat end caps).
- Sidebar icons: pattern items now use the `library` codicon, folders that are also directly-openable patterns use `folder-library`, the top-level Frames root uses `home`, and the top-level Patterns root uses `book`.

#### Fixed

- Fixed clicking the top/bottom end faces of round timbers always reporting "cylindrical_surface" instead of "top"/"bottom" (the barrel's curved side still isn't split into left/right/front/back, which is correct/expected).
- Fixed reusing an existing viewer panel to open a different pattern (from the sidebar) leaving the previous pattern's parameter values applied — the panel now correctly resets to the new pattern's own parameter schema and defaults.

## [0.4.5] - 2026-07-26

### kumiki

#### Added

- Added a "learn to timber frame shed" structure example (a full 61-timber shed frame).

#### Fixed

- Fixed assembly freedom for the tongue-and-fork corner joint.
- Fixed assembly freedom for the keyed miter joint.

### kigumi

#### Added

- Added a footprint render color picker (four swatches: slate, moss, orange, and transparent to disable footprint rendering entirely); orange is now the default, and fill opacity was bumped up ~10 points across all colors.

#### Fixed

- Fixed a thread-safety bug in the Python runner: the main request loop and the background assembly-solve thread both wrote to stdout unsynchronized, letting a large response and a background solve result interleave and corrupt the newline-delimited JSON protocol. Writes are now serialized through a lock.
- Fixed a race where the webview's eager `requestLayersTree` request on mount kicked off a redundant background assembly solve competing with the initial `get_geometry` call for CPU/GIL time, badly inflating load time for complex frames. Removed the eager request entirely -- layers/assembly data is now always pushed proactively by the extension once it's actually ready (on refresh completion, or immediately from cache on a panel reopen).
- Fixed the assembly-preview timeline appearing to do nothing (no "still solving" indicator, nothing when finished) on slow solves: the background solve request's immediate acknowledgment was mistakenly posted to the webview as if it were the final result, prematurely clearing the "solving" state well before the real solve completed.

## [0.4.4] - 2026-07-25

### kumiki

#### Added

- Added `cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers` (Kanawa Tsugi style scarf joint): half-blind tenoned, dadoed, and rabbeted, with a Kusabi wedge peg accessory (plus a `cut_basic_` variant and a structure example).
- Added `set_mortise_shoulder_parallel_to_face` parameter to mortise-and-tenon joints.
- New assembly solver (moving-group closure + simultaneous escape) handles interlocked/simultaneous disassembly sequences the previous solver couldn't.
- `cut_lapped_gooseneck_joint_on_aligned_timbers` now authors an assembly freedom (lift-out along `front_face_on_timber1`); `cut_mortise_and_tenon_joint` with `bore_mortise_perpendicular_to_face=True` now authors an additional perpendicular assembly freedom.

#### Changed

- **Breaking:** removed `inset_notching_style` / `InsetShoulderNotchingStyle` from `cut_mortise_and_tenon_joint` — scribe notching is now the only behavior.
  **Migrate:** drop the `inset_notching_style` argument; scribe-style notching is applied automatically.
- Plain butt, plain butt splice, and plain miter joints now use `freed_after=0` for their assembly freedom instead of a nominal-travel hack (disassembly visualization already adds its own separation padding).

#### Fixed

- Fixed `create_horizontal_timber_on_footprint` placing mudsills straddling the footprint plane instead of sitting above it.
- Fixed a sign error in `chop_relief_for_butt_joint_arrangement` that could silently produce empty/degenerate geometry for butt joints anchored far from the global origin (e.g. wedged half-dovetail tie beams cut at both ends fell back to bounding-box placeholders, or crashed headless rendering).
- Fixed several other scribe-relief bugs.
- Fixed round mortise-and-tenon joints occasionally boring the mortise hole perpendicular to the tenon axis instead of parallel.
- Fixed odd-N stool disassembly (robust nullspace rank + exact LP backstop).

### kigumi

#### Added

- Integrated the new assembly solver into the viewer, solved in the background after the frame loads.
- Added `kigumi.viewer.assemblyPreview` VS Code setting (default off).
- Added a setting to show poop-tagged joints in the pattern book.

#### Fixed

- Fixed a duplicate-refresh bug in the viewer.
- Fixed an async event handling issue in the viewer/runner communication.

## [0.4.3] - 2026-07-18

### kumiki

#### Added

- Added `cut_dropin_housed_butt_joint_on_face_aligned_timbers` (plus a `cut_basic_` variant and pattern) for drop-in housed butt joints.
- Added `cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers` (plus a `cut_basic_` variant).
- Extended scribe relief to all valid butt joints, including a new `DropinButtJointSweepScribeReliefConfig` for drop-in variants.
- Added `stickout_length` to simple peg parameters.
- Tenon placement is now validated: cut functions raise if the tenon would exceed the tenon timber's boundaries.

#### Changed

- **Breaking:** joint cut functions renamed with suffixes stating their arrangement restrictions (`_on_face_aligned_timbers`, `_on_plane_aligned_timbers`, `_on_aligned_timbers`), e.g. `cut_basic_plain_cross_lap_joint` → `cut_basic_plain_cross_lap_joint_on_face_aligned_timbers`, `cut_multi_cross_lap_joint` → `cut_multi_cross_lap_joint_on_plane_aligned_timbers`, `cut_basic_lapped_gooseneck_joint` → `cut_basic_lapped_gooseneck_joint_on_aligned_timbers`.
  **Migrate:** append the arrangement suffix matching the joint's restriction; the pattern index / agent usage instructions list the new names.
- **Breaking:** `join_plane_aligned_on_place_aligned_timbers` renamed to `join_plane_aligned_on_plane_aligned_timbers` (typo fix).
- **Breaking:** the wedge in `cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers` is now required — `wedge_accessory_parameters` is a required parameter (it is physically required for the joint to assemble), and `cut_basic_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers` defaults `use_wedge=True`.
- **Breaking:** `DovetailTenonWedgeAccessoryParameters.wedge_small_height` replaced by `wedge_extra_height`: the wedge's small height is now `dovetail_depth + wedge_extra_height`, since a minimum of `dovetail_depth` is required for the joint to physically assemble.
  **Migrate:** remove `wedge_small_height` and, if a larger wedge is desired, set `wedge_extra_height` to the amount above `dovetail_depth`.
- Relicensed under the Mozilla Public License 2.0.

#### Fixed

- Wedged half dovetail assembly freedoms: disassembly now follows the diagonal direction determined by the wedge angle instead of straight along the butt axis.
- Fixed a scribe relief cutting bug.
- `cut_plain_miter_joint_on_face_aligned_timbers` now actually asserts that the timbers are face-aligned.

### kigumi

#### Changed

- Relicensed under the Mozilla Public License 2.0.

## [0.4.2] - 2026-07-12

### kumiki

#### Added

- Supported full compound (multi-axis) tenon and mortise cropping in `cut_mortise_and_tenon_joint` when `bore_mortise_perpendicular_to_face=True` is enabled, sizing the mortise hole correctly along both the receiving timber's length and width axes.

#### Fixed

- Fixed a bug where a perpendicular tenon entry on a raked joint with `bore_mortise_perpendicular_to_face=True` caused a division-by-zero that inflated the mortise hole size, cutting a channel along the entire length of the receiving timber.

### kigumi

#### Added

- Added edge thickness options and edge-mode selector (with independent selected transparency) to the Kigumi viewer.

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
