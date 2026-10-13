# runner.py review (2026-10-12)

`kigumi/runner.py` is 7,732 lines. Roughly where they go:

| lines | section |
|---|---|
| 37–612 | wire-form TypedDicts (~575) |
| 612–1566 | member entries, meshes, frame geometry (~950) |
| 1566–2253 | drawings: layouts, cameras, preview orientation (~690) |
| 2253–3894 | measurements: plane, kinds, verdicts, merge, file, settle (~1,640) |
| 3894–4848 | resolving anchors, spans, highlights, layers, CSG tree (~950) |
| 4848–5284 | parameters, slots, frame loading (~440) |
| 5284–7058 | picking: CSG navigation, highlight meshes, rays (~1,770) |
| 7058–7732 | patterns, request dispatch, main loop (~670) |

Largest functions: `handle_request` 446 lines (one `if command == ...` chain over 31 commands),
`_handle_find_csg_at_point` 264, `build_real_geometry` 160, `_cropped_edge_segments` 139,
`serialize_layers` 121, `_measure_span` 119, `_extract_highlight_mesh` 112.

## Findings

### Dead or test-only code
- Never used: `_labelled_candidates`, `_csg_roots_of`.
- Used only by tests: `_find_csg_by_labels`, `_roots_for_path`, `_timber_body_csg`,
  `_find_declared_feature`, `resolve_anchor`. The first four only forward to
  `kumiki.csg.feature_paths`, so the kumiki functions are tested only through runner wrappers
  (31 calls across `test_kigumi_csg_navigation.py`, `test_measurement_anchors.py`,
  `test_kigumi_drawings_file.py`).
- Commands with no caller in the extension: `get_member`, `list_tools`, `run_tool`. Tools are
  planned UI (TODO: "run @tools from the parameter section"), so keep those; `get_member` and its
  placeholder `"placeholder-member-geometry"` payload look abandoned.

### Two implementations of the same thing
- **Where a feature is, for measuring.** The runner's `_measure_span` (crops to the timber, handles
  edge-on faces, non-real lines, flush faces) and kumiki's `feature_solving._span` (declared extent
  only) both turn a feature into a `MeasureSpan`. They already disagree, which is how the auto
  dimensioning's lengths and the viewer's could drift apart. One home, in kumiki.
- **Vector math.** About a dozen list-of-float helpers (`_dot`, `_cross`, `_normalize`,
  `_unit_or_none`, `_inv_transform_point`, `_inv_transform_direction`, `_build_inv_transform_float`,
  `_direction_to_world`, `_vector3_to_floats`, ...), plus inline `dot`/`plus` lambdas, beside numpy
  and kumiki's own geometry. Fine for the hot picking path; elsewhere numpy would be shorter.

### Structure
- `handle_request` as a dispatch table (`COMMANDS = {"get_frame": _cmd_get_frame, ...}`), one small
  function per command. The 446-line chain becomes ~31 functions of 5–20 lines, and the command list
  in `make_ready_event` can be the table's keys, so the two can't drift.
- Most of the file isn't protocol: measuring, picking and drawing layout are geometry questions with
  a wire form at the end. Two ways to shrink it:
  1. **Move the geometry into kumiki** (`kumiki/drawings/` for spans, verdicts, measurement planes;
     a `kumiki/picking.py` for CSG navigation and highlight extraction). Tested and typed there,
     usable from the auto dimensioning, and the runner keeps only serialization and dispatch. Costs a
     kumiki minor bump each time the runner needs something new, which the version coupling already
     asks for.
  2. **Split the runner into sibling modules** (`kigumi/runner/picking.py`, `measurements.py`, ...).
     Cheaper, but the loader and tests load `runner.py` by path, and the reload logic purges modules,
     so each split needs care; and it only moves code around.
  (1) is the better long-term shape; (2) is a stopgap.
- The `TypedDict` block (575 lines) could move to `kigumi/runner_wire.py` once the runner can import
  siblings, or stay; it is declarations only.

### Tests
- `test_kigumi_csg_navigation.py` (145 tests, 2,924 lines) is the biggest. Mostly real picking
  behaviour, but the wrapper tests should call kumiki directly (and move to a kumiki test file).
- `test_kigumi_debug_drawing.py` (47): `TestDefaultDebugDrawing` (~145 lines) tests the debug
  drawing, which is marked "testing scaffolding" but still has a button. Delete both together if the
  scaffolding goes; the rest (selection drawings, preview camera, orientation) is real.
- Nothing else looked dead: skipped tests are optional-dependency skips, deselected ones are `gui`.

## Suggested order

1. Remove the dead functions and `get_member`; point the wrapper tests at kumiki and delete the
   wrappers. Small, safe.
2. Dispatch table for `handle_request`.
3. One `MeasureSpan` implementation, in kumiki, used by both the runner and auto dimensioning.
4. Move picking into kumiki, then measurements, section by section.
5. Decide on the debug drawing.
