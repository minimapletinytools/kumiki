# Rewrite the left rail: info pane, unified list with embedded CSG trees, selection model

> **START MARKER — this commit is where the timber list view rewrite begins.**
> Everything below is the agreed design, captured before any of it was built. The
> commit that adds this file is the base to diff against (or reset to) while the
> rewrite is in progress.

## Context

The selection pane built in step 6D put the CSG feature tree in its own panel above the timber
list. In use this proved to be the wrong home: the CSG of a timber shows up in *two* natural
places — under the timber (all its cuttings) and under a joint (one cutting per member timber,
against the timber body so plane/plane intersections are visible) — and both of those places are
the timber list, not a separate pane. The selection pane shrinks to a small expandable **info
section** (never auto-expands, no tree), and the trees move into the list's existing
by-timbers / by-joints sections. Selection handling is rewritten around a single **CSG focus**
that coexists with multi-timber selection.

Decisions already made by the user:
- **Pick rule**: while timbers are selected, a 3D click CSG-picks into the nearest *selected*
  timber the ray hits, even if an unselected timber is nearer along the ray. If the ray hits
  only unselected timbers, select the nearest as usual. Empty space clears. Shift-click keeps
  toggling timber membership on the nearest hit.
- **Nested Difference**: plain explicit nodes — a `Difference` row with the base and each cut
  as ordinary children, role-marked ("base" / "− cut"). Only the **first tier** is special:
  the root row is the timber body, with one child row per cutting attributed to its joint.
- **Info pane collapsed state** (the default, and it never auto-expands): counts line +
  selection breadcrumb. Expanding adds the pick detail lines (feature type, joint, faces toward).
- Tree labels show **base type · tagged name** (e.g. `Prism · shoulder`). SolidUnion /
  Intersection rows stay as plain combinator header rows (they have no geometry of their own).
- Single selection in the CSG trees; multi-select stays for timbers only.
- Reveal rule: a viewer pick reveals + auto-expands in the **by-timbers** section, UNLESS the
  current CSG focus is already inside the **joint-section tree of the same cutting** — then the
  reveal happens there instead.

## Data flow (one payload, two views)

`get_csg_tree` already returns the whole rendered tree per timber
(`runner.serialize_cut_csg_tree`, kigumi/runner.py:1195), with `role` base/subtract and
`jointName` per top-level cut. Both list views derive from this one per-timber payload
client-side; no new runner request.

### Runner changes (kigumi/runner.py)

1. In `_serialize_csg_node`, on aligned top-level subtract children add:
   - `cutIndex`: index into `cut_timber.cuts` (it equals the subtract position; make it explicit).
   - `jointId`: the joint ticket's `kumiki_id` (str, matching the layers payload's joint `id`),
     via the existing `_joint_by_cutting_id`; null when no joint owns the cut.
   Keep `jointName` (display) — add a small `_joint_for_cutting(cut_timber, cutting)` returning
   the joint so name and id come from one lookup instead of two.
2. No other payload changes. `serialize_layers` already gives `joints[].members[]` with
   `timberKumikiEphemeralId` + `cutIndices` — exactly the join key the joint section needs.

## Client model (rewrite kigumi/webview/csg-tree-view.js)

Stays a pure, jest-covered module (same file/URI registration; contents rewritten). It becomes
the *model* for trees that the layers panel renders:

- `timberTreeNodes(payload)` → the by-timbers display tree: root = body node (the base child of
  the root Difference, or the root itself when the timber has no cuts), its children = the
  body's own subtree, followed by one node per cutting (labelled by joint: jointName, or the
  cut CSG's own label, else `cut <i>`), each cutting node's children = that cut CSG's subtree
  rendered explicit (Difference → base + "− cut" children).
- `jointCuttingTreeNodes(payload, cutIndex)` → the joint-section tree for one cutting:
  `[bodyNode, cuttingNode(cutIndex)]` — same builders, filtered to one cut, so plane/plane
  intersections against the body are representable later.
- `describeNode(node)` → `Kind · label` (+ role marker for base/cut).
- `nodeId(...)` → identity that embeds context so ids are unique inside the layers panel's
  single `expandedNodes` set: `csg:t:<timberKey>:<indexPath>` and
  `csg:j:<jointId>:<timberKey>:<cutIndex>:<indexPath>`.
- `findDeepestByPath(displayTree, csgPath)` → deepest display node whose CSG `path` matches
  (unchanged logic: untagged intermediates share paths, deepest wins).
- `cutIndexForPath(payload, csgPath)` → which cutting a resolved pick path belongs to (walk the
  root's subtract children; null when the pick is in the body).
- `revealTarget(csgFocus, pick)` → `{section: 'timbers'|'joints', ...}` implementing the
  UNLESS rule as a pure decision, so it is testable: joints-section only when
  `csgFocus.context.section === 'joints'` and same timberKey + cutIndex as the pick.

The old `shouldShowTree` / `treeTimberKey` / `flattenTree` / `revealPath` go away with the
selection-pane tree; flattening honouring expansion moves to the layers panel's row building
(which already works that way with `expandedNodes`).

## Selection store (rewrite kigumi/webview/selection-store.js)

New model, dropping the vestigial parts:

- `selectedTimbers: Set` — multi-select, as now (accessories keep riding this set).
- `csgFocus: { timberKey, path, featureLabel, cutIndex, context } | null` — the single CSG
  selection. `context` is `{section:'timbers'}` or `{section:'joints', jointId, cutIndex}`.
  Setting focus does **not** clear other selected timbers (user: "you can still select multiple
  timbers but click into just 1 of the CSG trees"); it does ensure `timberKey` is in
  `selectedTimbers`.
- Drop `selectedFeatures` entirely (only consumer is its own test + one cleanup site,
  kigumi/webview/viewer-app.js:2972). Feature selection is `csgFocus.featureLabel`. Measurement
  pairs (plan step 8) will get their own concept later.
- Drop `selectedLayerNode` as stored state; list-row highlight derives from
  `selectedTimbers`/`csgFocus` instead of a third parallel notion.
- Keep the API surface event-based (`onSelectionChanged`); methods:
  `selectTimber/toggleTimber/deselectTimber/clearTimbers`, `setCsgFocus/clearCsgFocus`,
  `selectJoint(jointId, timberKeys)` (= select member timbers, clear focus), `hasSelection`.
- Update kigumi/__tests__/selection-store.test.js for the new model.

## 3D pick flow (kigumi/webview/viewer-app.js)

- `_findMemberAtClientPoint` returns only the nearest hit today; add a variant returning all
  hits in ray order. `handleCanvasClick` becomes:
  1. shift-click → toggle timber on nearest hit (clears csgFocus if its timber got deselected).
  2. else if any hit's memberKey ∈ selectedTimbers → `findCSGAtPoint` on the nearest such hit
     (works with multi-selection now; currently gated on exactly-one-selected).
  3. else nearest hit → single-select that timber, clear focus.
  4. no hit → clear everything.
- `handleCSGSelectionResult`: compute `cutIndex` from the resolved path via the model, decide
  the reveal target with `revealTarget(csgFocus, pick)`, set
  `csgFocus = {timberKey, path, featureLabel, cutIndex, context: target}`, then tell the layers
  panel to reveal (auto-expand ancestors + mark row selected) in that section. Highlight-mesh
  handling stays as is.

## Layers panel (kigumi/webview/layers-panel.js)

- **By-timbers**: timber rows get `hasChildren: true`. Expanding requests the tree
  (`kigumi-request-csg-tree` event bubbled up; viewer-app fetches via the existing
  `requestCsgTree` message and calls `layersView.setCsgTree(timberKey, payload)`; panel caches
  payloads per timberKey and shows a loading row meanwhile). Child rows come from
  `timberTreeNodes` + `expandedNodes`, rowType `csg`, depth-indented, chevrons as today.
- **By-joints**: joint rows keep member rows; member rows become one row per **cutting**
  (per `members[].cutIndices` entry — label: timber name, plus `cut <i>` suffix only when a
  member has several cuts). Expanding a cutting row lazily requests that timber's tree and
  renders `jointCuttingTreeNodes(payload, cutIndex)` beneath it.
- Clicking a csg row → `selectionManager.setCsgFocus(...)` with the right context, and posts
  `findCSGByPath` (existing message, frame-view-session.js:962) so the 3D highlight follows the
  list — same round trip the old pane's `onCsgNodeActivated` did.
- `revealCsg({section, timberKey, jointId, cutIndex, csgPath})` public method: expands ancestor
  nodeIds (section → timber/joint → cutting → tree ancestors) and applies the selected style.
  Row selected-styling for csg rows keys off `csgFocus`, not `selectedLayerNode`.
- Delete the now-dead `selectLayerNode` plumbing that the store rewrite removes
  (`type:'csgNode'`/`'cutting'` descriptors, layers-panel.js:398–403 mapping).

## Info pane (kigumi/webview/viewer-app.js `_renderSelectionPanel` + viewer.css)

- Collapsed (default, never auto-expands): header + counts line + breadcrumb of the current
  selection/pick. Expanded: adds the detail lines (feature type, joint, faces toward) — same
  `lastPickDetail` data as today. All tree rendering/state
  (`csgTreePayload`, `expandedCsgNodes`, `_buildCsgTreeElement`, `_buildCsgTreeRow`,
  `ensureCsgTreeFor`, `revealCsgSelectionInTree`, `onCsgNodeActivated`) leaves viewer-app;
  fetch-and-cache moves behind the layers panel request event.
- CSS: `sp-tree`/`sp-node*` rules die; new `lp-row-csg` styles live with the other `lp-*` rules.
  The `.sp-panel` content-sizing rules and the left-rail-layout guard test stay.
- i18n: drop `viewer.selection.csgTree`/`csgTreeLoading` if unused; add keys for
  `viewer.layers.csg.loading`, `viewer.layers.csg.body`, `viewer.layers.csg.cut` (en + ja,
  keep both files at parity).

## Tests / verification

- **jest**: rewrite `csg-tree-view.test.js` for the new model (tree building for both views,
  explicit Difference rendering, first-tier organization, `cutIndexForPath`, `revealTarget`
  UNLESS-rule truth table, id namespacing); update `selection-store.test.js`;
  `left-rail-layout.test.js` should still pass unchanged. `npx jest` in kigumi/.
- **python**: extend tests/test_kigumi_csg_navigation.py for `cutIndex`/`jointId` on top-level
  subtract nodes (named joint, unnamed joint, hand-built CutTimber without joints → null).
  `make test`, `make typecheck`.
- `node --check` on every touched webview file.
- Manual: the user opens the viewer — verify tree under a timber row, tree under a joint
  cutting row, click-through pick on occluded selected timber, reveal honouring the UNLESS
  rule, info pane staying collapsed.

## Out of scope

- Derived edges in the trees (still not shown; only declared features/structure).
- Measurement pairs (plan step 8) — the dropped `selectedFeatures` will be superseded there.
- Highlighting the body/cutting mesh from joint-section rows beyond what `findCSGByPath`
  already provides.

Leave everything uncommitted for review, per the session's standing pattern.

## Starting state (as of 2026-08-24)

Branch `csg-feature-selection-steps-1-5` (main merged in). The step-6D selection pane is
**uncommitted** in the working tree (viewer-app.js, viewer.css, viewer.html, viewer.js,
layers-panel.js, i18n en/ja, csg-tree-view.js + its test, left-rail-layout.test.js). This
rewrite replaces most of that uncommitted work — treat it as raw material, not something to
preserve. Background/design record: `.claude/plans/csg-feature-selection-and-measurement.md`
(this rewrite is a redo of its step 6 part D, plus the selection-model refactor).
