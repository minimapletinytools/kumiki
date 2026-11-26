<!-- 🤖🤖🤖🤖🤖🤖 -->
# Feature coverage

Which tests cover each finished feature of kumiki and Kigumi, its normal cases and its edge cases, and
what is left uncovered and why. Features still being designed (the drawing viewport layout model and its
UI) are left out until they settle.

Reviewed 2026-11-25. Line coverage then: kumiki and the runner 89% (`pytest --cov=kumiki --cov=kigumi`),
Kigumi's JavaScript 38% from unit tests alone (the views and the app shell are covered by the
integration suites instead).

## Where the tests are

| Kind | Where | Run with | Time |
|---|---|---|---|
| kumiki and the runner | `tests/` (pytest) | `pytest tests` | about 40 s |
| Kigumi units | `kigumi/__tests__/` (Jest) | `npm test` in `kigumi/` | about 5 s |
| Kigumi integration | `kigumi/test/app/scenarios/` (standalone app), `kigumi/test/suite/` (VS Code), `kigumi/hosts/pyodide/test/` (browser) | `npm run test:int -- --list` | 1 to 5 min a host |

Integration suites are listed in `kigumi/test/integration.js` with what each covers, its CI time and the
paths it depends on. **Core** suites are quick and always run. The rest run on a pull request only when a
file in their `paths` changes (`npm run test:int -- <host> --changed origin/main`). Everything runs on a
push to main. The slow ones are `app:drawings` (about 90 s), `web:browser` (90 s), `app:stl-placement`
(35 s), `web:phone` (28 s) and `app:shared` (21 s).

## kumiki

| Feature | Normal cases | Edge cases | Gaps |
|---|---|---|---|
| **Mortise and tenon** | blind and through, pegs, multiple pegs, peg depth and stickout, relative tenon sizing: `joints/mixed/test_mortise_and_tenon_joints.py` | draw-bore offset moves only the tenon's hole (`test_peg_with_tenon_hole_offset`); tenon reaching past its timber is refused (`test_a_tenon_that_would_reach_past_its_timber_is_refused`); relief on rough stock; angled brace into a rough post; offset tenon in an angled bored mortise; merged twin tenons | |
| **Wedged mortise and tenon** | kerfs, paired wedges, flared walls: `joints/mixed/test_wedged_mortise_and_tenon.py` | zero kerf; wedge with a peg; invalid wedge sizes; round tenons refuse a wedge; oblique walls; face-bored | |
| **Tusked tenon** | `test_joint_pattern_catalog.py`, naming in `joints/mixed/test_mortise_and_tenon_joints.py` | tusk clearance on rough stock | Geometry checked only through the pattern build and names, not a containment test. |
| **Dovetails** | free (`joints/free/test_free_dovetail_joint.py`), corner (`joints/corner/test_dovetail_corner_joint.py`), drop-in and wedged half dovetails (`joints/butt/`) | tapered, open ends past a long receiving timber, taper closing inside the material; corners at any angle, either end, half blind, zero flare, widest tail | |
| **Finger joints** | box corner and splice: `joints/test_finger_joints.py` | fixed width at the front, exact multiples, tapered last finger, invalid layouts | |
| **Laps, scarfs, splices** | cross laps, multi cross lap, mitered keyed lap, gooseneck, Kanawa Tsugi, butt splice: `joints/cross/`, `joints/corner/`, `joints/splice/` | key count by lap count; custom splice point | Kanawa Tsugi has 2 direct tests; most of its checks are in `test_joint_doc_drawings.py`. |
| **Butt joints** | tongue and fork, drop-in housed, splined opposing double butt with stubby tenons: `joints/butt/`, `joints/corner/` | arrangement refusals with the faces that would work | |
| **Decorative end cuts** | rounded end, angled end, path extrusion corner: `joints/decorative/test_decorative_joints.py` | distance from end equal to the radius (no warning) | |
| **Relief** | scribe, notch, sweep scribe, notch from shoulder or face: `joints/shavings/test_relief.py` | relief on rough stock in `joints/mixed/test_mortise_and_tenon_joints.py` | |
| **Assembly freedoms and solver** | per joint freedoms (`joints/test_assembly_freedoms.py`), solver (`test_assembly.py`) | rings needing simultaneous motion, rotations (Luban lock), unsolvable pairs, ordering and suborders | |
| **Timber construction** | create, attach face/plane aligned, join, split, stretch: `test_construction.py` | stickout references, extend to a rotated target, conflicting faces refused | |
| **FauxTimber** | `test_faux_timber.py` | end trims both ways, side stock that doesn't reach, X-ray sides remapped | |
| **STL, round and polygon timbers** | `test_stl_timber.py`, `test_timber.py` | open STL refused, invalid placement, Windows line endings in source edits, end cuts on a mesh | |
| **Rough stock and the perfect timber within** | `test_rough_with_perfect_features.py`, `test_timber.py` | asymmetric rough half sizes, rotated timbers, `rptw` vs `ptw` naming | |
| **CSG primitives and booleans** | `test_meowmeowcsg.py`, `test_pathcsg.py`, `test_triangles.py` | infinite ends, empty solids, coplanar cuts (`test_coplanar_cuts.py`), loft twist refused | |
| **Feature model** | declared, derived edges and points, kinds, groups: `test_meowmeowcsg.py`, `test_feature_kinds.py` | buried faces, abutting solids, flush cuts, a derived edge asked about itself | |
| **Feature lookup** | `joint.feature`, `cut.feature/face/edge/corner`, `MortiseAndTenonFeatures`: `test_feature_lookup.py` | missing names suggest close ones; index out of range; corner from a derived edge refused; `on=timber` for a peg hole (`test_peg_with_tenon_hole_offset`) | Constants exist for mortise and tenon only; other joint families still use string names. |
| **Feature extents and line cropping** | `test_edges_on_csg.py`, `test_feature_extent.py`, `test_crease_crop.py` | cylinders solved not bounded, lines on a boundary kept, cuts splitting an edge | |
| **Kiwari** | `test_kiwari.py`, `test_rule_dimensions.py`, `test_frame_decorators.py` | optional values, ratios, lengths typed as people write them | |
| **Tools, extra accessories, finishing** | `test_finishing.py`, `test_kigumi_finishing.py` | only a keyword-only `kigumi` is passed; extras kept, removed, cleared on rebuild; cancelled finishing | |
| **Router templates (sawhorse)** | `test_sawhorse_router_templates.py` | wide end square to the leg; each runout moves its end; templates shown only when asked | |
| **Symmetry, matching pieces** | `test_symmetry.py` | mirrored pieces | |
| **Export** | STL, OBJ, STEP: `test_blueprint.py` | accessories in or out | 3MF tests always skip in CI (its dependency isn't installed there). STEP runs where OCP is installed. `blueprint.py` is 40% covered: most of what's left is the 3MF and STEP paths. |
| **PNG rendering (kigumi_at_home)** | `test_kigumi_at_home.py` (matplotlib) | | The pyglet backend's tests skip in CI on purpose (they need a display). |

## Drawings

| Feature | Normal cases | Edge cases | Gaps |
|---|---|---|---|
| **Layout and named views** | `test_layout.py` | a view named by `id`, shared labels keep positions, duplicate ids refused, old position-keyed files (`test_kigumi_drawings_file.py`) | |
| **View (direction, scale, centre)** | `test_measurement_placement.py`, `test_kigumi_debug_drawing.py` | unknown world side refused | |
| **Measurements** | kinds, planes, angles, slide: `test_measurement_kinds.py`, `test_measurement_anchors.py`, `test_measurement_plane.py`, `test_measurement_slide.py`, `test_measurement_end_to_end.py` | end-on lines, oblique corners, perspective views check nothing | |
| **Placement** | `Auto`, `Offset`, `Beside`: `test_measurement_placement.py`, `test_dimension_placement.py` | a side the dimension runs across warns and auto-places; lane 1 a base gap past the work | |
| **Auto dimensioning** | `test_auto_dimensioning.py`, `test_kigumi_generated_drawings.py`, `test_kigumi_sawhorse_drawings.py` | sloped shoulders by angle, rough stock, mirrored pieces | |
| **Editing the layout on the sheet** | `test_kigumi_drawing_layout.py`, `viewport-layout.test.js`, `app:layout-edit` | a copy of a view the runner points by label; a view the code gains after the layout was saved; deleted views keep their measurements; the last view can't be deleted | Touch input isn't covered. |
| **with_drawings** | `test_with_drawings.py` | unknown view or piece names what there is | |
| **Hand-placed starter drawings** | `test_kigumi_starter_drawings.py` | every dimension resolves to its source value | |
| **Drawings file and overrides** | `test_kigumi_drawings_file.py` | dangling overrides, deleted code measurements, unplaceable ones kept | |
| **SVG and PNG export** | `test_svg_drawings.py`, `test_joint_doc_drawings.py`, `app:drawings` | true arcs, clipping by other members | |
| **X-ray** | `test_svg_drawings.py`, `test_drawing_reference_picks.py`, `app:drawings` | only from authored sides; clipped by other members; kept with a dimension | |
| **Reference lines where measured** | `jest:drawing-overlays`, `test_svg_drawings.py` | another member's line isn't this one's; old saved true or false read as where measured or off | Only the export and the overlay logic are unit tested; the setting's UI is exercised by `app:drawings`. |

## Kigumi

| Feature | Normal cases | Edge cases | Gaps |
|---|---|---|---|
| **Picking, hover, measuring in the view** | `test_kigumi_csg_navigation.py`, `test_kigumi_whole_ray.py`, `jest:pick-tolerances`, `jest:hover-state`, `app:drawings` | drilling down with ctrl, accessories answer without raising, tolerance per call | |
| **Layers tree, selection, tags** | `jest:layers-*`, `jest:selection-store`, `jest:tag-index` | locked rows don't select; extra accessory rows | |
| **Extra accessories** | runner: `test_kigumi_finishing.py`; tree: `jest:layers-accessory-rows`; app: `app:parameters` | deleted, cleared on rebuild, tinted | |
| **Kiwari panel and tools panel** | `app:parameters`, `vscode:parameters`, `jest:kiwari-values` | a typed runout reaches the tool | |
| **Display options** | units, edge mode, geometry mode, themes, grain, scale ruler: `jest:display-options-store`, `jest:units`, `jest:geometry-mode`, `jest:scale-ruler`, `app:viewer` | | Footprint colours have no test. |
| **Assembly timeline** | `jest:assembly-timeline`, `vscode:assembly` | | |
| **STL placement editor** | `jest:stl-placement`, `app:stl-placement` | | |
| **Agent and MCP** | tools: `jest:agent`, `jest:agent-loop`, `jest:frame-description`; MCP: `app:mcp`, `web:mcp` (needs a backend checkout) | `describe` with and without a timber; signed out | `web:mcp` runs only by hand. |
| **Sharing** | `jest:publishes`, `jest:shared-tools`, `app:shared`, `web:browser` | read-only source, copy to project | |
| **Projects** | new, open, close, switch, recent: `jest:project-tools`, `app:projects`, `app:switch-project`, `app:recent-folders` | unsaved edits on close | |
| **Explorer and sidebar** | `jest:sidebar-model`, `app:explorer`, `app:sidebar`, `vscode:fixture-switching` | no project open | |
| **Editor, tabs, go to file, quick pick** | `app:tabs-and-editors`, `app:go-to-file`, `app:quick-pick` | read-only files | |
| **Keyboard shortcuts** | `jest:keybindings`, `jest:key-match`, `app:keyboard-shortcuts` | | |
| **Touch and phone** | `jest:touch-navigation`, `web:phone` | | |
| **Languages** | `jest:i18n` (every key in both locales) | | |
| **Auto update** | `jest:auto-update`, `jest:update-check` | | |
| **Crash recovery and the log** | `app:crash-recovery`, `app:log` | | |
| **Starter project** | `jest:project-initializer` (embedded copy matches), `test_starter_frame.py`, `vscode:initialization` | | |

## Not covered

- `kumiki/librarian_cli.py` (the pattern librarian's command line) and `kigumi/dependency-discovery.py`
  have no tests at all.
- 3MF export, pyglet rendering and (where OCP is missing) STEP export skip in CI, as above.
- Footprint colour options.
- `web:mcp` needs a kigumi-backend checkout and runs only when named.
