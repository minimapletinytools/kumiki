# CSG feature selection and measurement: audit + design

## Context

We want three user-facing features on top of CSG feature selection:

1. **Richer feature selection display** — feature type, originating joint, position in an
   expandable CSG tree, and which local timber face the feature most points toward.
2. **Measurements in the viewer** — store one selected feature, click another, get a
   rendered dimension between them; measurements accumulate and are individually stylable.
3. **Automatic drawing generation** — tag named features so a drawing algorithm can
   decide what gets measured, from where, and in what order.

Before any of that, this documents what feature selection actually does today (it is
broken in ways that are invisible because they fail silently), and records the resolved
design for `CSGFeature`.

Sections "Diagnosis" and "Verification" are findings. Section "Resolved design" is the
spec to implement from.

---

## Diagnosis

### 1. There are two feature systems and the viewer uses the wrong one

`kumiki/cutcsg.py:85` defines the intended model: `CSGFeature` with `test_point`, plus
`CutCSG.get_all_features(point)` and `CutCSG.find_feature(point)` (`cutcsg.py:165`) which
walks the tree and returns the highest-priority hit.

kigumi calls none of it. `kigumi/runner.py` carries an independent reimplementation:

| function | line |
| --- | --- |
| `_is_point_inside_csg_float` | `runner.py:1558` |
| `_is_point_on_csg_boundary_float` | `runner.py:1607` |
| `_detect_face_label` | `runner.py:1716` |
| `_resolve_csg_at_path` | `runner.py:1803` |
| `_navigate_csg_one_level` | `runner.py:1855` |
| `_navigate_csg_to_leaf` | `runner.py:1903` |
| `_extract_highlight_mesh` | `runner.py:1925` |

These re-derive boundary membership and face naming from scratch in plain floats, via
`isinstance` dispatch on kumiki's primitives.

That split made sense when kumiki was sympy-backed and a symbolic point test was too slow
to run per raycast. **It is no longer sympy-backed.** `kumiki/rule.py` says so explicitly
in its module docstring: "All numeric values in this library are plain Python floats [...]
there is no lazy/symbolic expression tree." Measured on a mortise-and-tenon pattern, the
two paths cost the same order of magnitude (~1.1 ms vs ~0.6 ms for 28 points).

The remaining cost is maintaining two implementations, and they have already drifted:
different names, different primitive coverage, different notions of what a feature is.

### 2. `tag` → `label` rename broke every path lookup

Commit `9eab80f` ("add tags to timber and joits", 2026-05-15) renamed `CutCSG.tag` to
`CutCSG.label`. kigumi was never updated. There are **seven** `getattr(..., "tag", None)`
reads in `runner.py` and every one returns `None` against current kumiki. `getattr`'s
default swallows it, so nothing errors.

Consequences, all silent:

- **The breadcrumb path is always empty.** `_navigate_csg_one_level` only appends to the
  path when a child has a tag, so it never appends. Selection reports `path: []`.
- **Ctrl+click drilling is a no-op.** With no tags there is no hierarchy to drill through;
  `_navigate_csg_to_leaf` lands on a leaf primitive on the first hop, so plain click and
  ctrl+click behave identically.
- **The CSG tree panel is empty.** `_walk_tagged_csg` (`runner.py:1124`) collects only
  tagged nodes and returns `[]` for every timber tested.
- **`find_csg_by_path` is unreachable.** It raises unless `path` is non-empty, and nothing
  can produce a non-empty path.
- **Cutting names don't show.** `_serialize_cutting_summary` (`runner.py:850`) falls back
  to `"cut 1"` / `"end-cut 2"` even though ~20 of the 47 `Cutting(...)` constructions in
  the joint library do pass `label="mortise_and_tenon"` and similar.

### 3. Selection coverage is incidental, not designed

Two independent things gate selection: whether a primitive can *carry* a name, and whether
the picker can *find* a point on it. Different primitives fail at different stages.

| Primitive | Can name faces | `get_all_features` | Float boundary test | `_detect_face_label` | Net |
| --- | --- | --- | --- | --- | --- |
| `RectangularPrism` | yes, per `PrismFace` | yes | yes | yes | fully selectable |
| `HalfSpace` | one name, whole plane | yes | yes | reads `named_feature` | selectable, never named in practice |
| `Cylinder` | **no field at all** | **no** | yes | caps + barrel, unnamed | pickable, permanently anonymous |
| `ConvexPolygonExtrusion` | yes, per side/cap | yes | **not implemented** | **no** | unselectable in viewer |
| `PathExtrusion` | yes, per segment/cap | yes | **not implemented** | **no** | unselectable in viewer |
| `ConvexPolygonSimpleLoft` | **no field at all** | **no** | **not implemented** | **no** | unselectable, unnameable |
| `Intersection` | — | forwards | **not implemented** | — | invisible to picking |
| `SolidUnion` / `Difference` | — | forwards | yes | — | ok |

Anything `_is_point_on_csg_boundary_float` does not handle returns `False`, which makes
the surface invisible to the picker.

**The failure mode is a wrong answer, not a miss.** `_navigate_csg_one_level` walks the
`Difference`, finds no subtract child claiming the point, falls through to `node.base` (the
timber's own prism), and asks `_detect_face_label`, which finds no prism face within
epsilon and returns the literal string `"face"`. Clicking a dovetail cheek or a roundover
selects the whole timber body and labels it `face`.

### 4. `find_feature` works, but has no tolerance knob

`safe_compare` uses `EPSILON_FLOAT = 1e-10` (`rule.py:320`). Raycast hit points land on
boolean-mesh vertices nowhere near that exact — the runner uses `eps = 5e-4` for exactly
this reason.

Run `find_feature` as-is over the triangle centroids of a meshed cut timber and it returns
`None` for 26 of 28 points. Patch the epsilon to `5e-4` and it returns the same answers the
runner does. The API is right; it just cannot be told how close is close enough.

### 5. Named-feature coverage is one call site

Across the whole joint library there is exactly **one** `named_features=` call site
(`kumiki/joints/workshop/mortise_and_tenon_joints.py:335`, on the tenon prism). Concretely:

- The mortise hole prism has no `named_features`; its faces report generic
  `top`/`left`/… derived from the prism's own local frame.
- Shoulders are authored as `HalfSpace(label="shoulder")`, but the feature system reads
  `named_feature` — a *different field*. The shoulder plane is therefore never a named
  feature, and `_detect_face_label` returns the literal `"cut_plane"` for it.
- Six of the twelve joint modules — `butt`, `cross`, `compound`, `multi_butt`, `basic`, and
  all of `shavings/` (where relief cuts live) — set no `label` either.

### 6. There is no edge model, and no triangle provenance

What the viewer draws as edges is `THREE.EdgesGeometry(geometry, 25)` — a 25° dihedral
threshold over the triangulated mesh, purely cosmetic, with no back-reference to anything.
Edges are entirely greenfield.

Separately: `TriangleMesh.face_sources` (`kumiki/triangles.py:50`) exists but is only
populated for leaf primitives, and is dropped by `_mesh_union` / `_mesh_difference` /
`_mesh_intersection`, which return a mesh with `face_sources=None`. Preserving it through
booleans would give exact provenance and make picking O(1), but manifold's boolean does not
hand back a source map, so point-in-tree re-derivation stays the pragmatic answer.

### 7. PTW and rough prisms share face names

`_timber_face_tags()` (`timber.py:1667`) names both the PTW prism and the rough prism
`right` / `left` / `front` / `back` / `top` / `bottom`. A feature named `"right"` is
ambiguous between the two, and only the actual (rough) prism appears in the rendered tree.
Every rule in user-facing feature 3 turns on telling these apart.

---

## Resolved design

### D1 — Tolerance parameter on every point test (`cutcsg.py`, `pathcsg.py`)

Thread an explicit epsilon through the whole test surface, defaulting to today's behaviour
so existing callers do not shift:

```python
def contains_point(self, point: V3, eps: Numeric = EPSILON_FLOAT) -> bool: ...
def is_point_on_boundary(self, point: V3, eps: Numeric = EPSILON_FLOAT) -> bool: ...
def get_outward_normal(self, point: V3, eps: Numeric = EPSILON_FLOAT) -> Optional[Direction3D]: ...
def get_all_features(self, point: V3, eps: Numeric = EPSILON_FLOAT) -> List[CSGFeature]: ...
def find_feature(self, point: V3, eps: Numeric = EPSILON_FLOAT) -> Optional[CSGFeature]: ...

class CSGFeature:
    def test_point(self, point: V3, eps: Numeric = EPSILON_FLOAT) -> bool: ...
```

**Sign convention to preserve.** The float shadow relies on *negative* epsilon meaning
"strict interior": `Difference.is_point_on_boundary` calls `sub.contains_point(pt, -eps)`
so a point sitting exactly on a subtracted solid's face still counts as on the boundary
rather than removed. Keep that semantic when porting, or difference boundaries flicker at
cut planes.

kigumi then calls kumiki directly and the float shadow (finding 1) is deleted.

### D2 — Features are objects stored on the primitive (`cutcsg.py`, `pathcsg.py`)

An earlier revision of this section had a `NamedFeature` *declaration* struct stored on the
primitive, converted at query time into a separate `CSGFeature` carrying an `owner`. That
shape was built and then rejected as too complicated: one concept in two types, joined by a
`_metadata_from` copy bridge, and — worse — the matching logic written twice, since each
primitive's `get_all_features` restated what the corresponding feature's `test_point`
already did (127 duplicated lines across six overrides).

The root cause was constructing features lazily so they could hold `owner`. Removing that
constraint collapses the design:

```python
@dataclass(frozen=True)
class FeatureProperties:
    group: FeatureGroup = FeatureGroup.A
    real: bool = True
    priority: int = 0

@dataclass(frozen=True)
class CSGFeature(ABC):
    name: str
    properties: FeatureProperties = field(default_factory=FeatureProperties)

    @abstractmethod
    def test_point(self, owner: 'CutCSG', point: V3, eps=None) -> bool: ...
```

A feature holds no reference to its owner; the owner is an argument. That makes a feature
constructible *before* the primitive it belongs to, which is what lets the primitive store
it.

Each primitive declares its own private `_features` (kw-only) and overrides
`get_declared_features()` to expose it. It deliberately does NOT live on `CutCSG`: a
`SolidUnion`, `Difference` or `Intersection` has no surface of its own to name, only the
surfaces its children contribute, so putting the field on the base would offer every
compound node something meaningless. Keeping it off means giving one features is a
construction-time `TypeError` rather than something that half works until a query happens
to land on it.

`CutCSG.get_declared_features()` returns empty by default, which is exactly right for the
compound nodes, so `get_all_features` still has **one** implementation covering every
primitive:

```python
def get_all_features(self, point, eps=None):
    declared = self.get_declared_features()
    if not declared or not self.is_point_on_boundary(point, eps=eps):
        return []
    return [FeatureHit(feature=f, owner=self)
            for f in declared if f.test_point(self, point, eps=eps)]
```

Compound nodes (`SolidUnion`, `Difference`, `Intersection`) override it to gather from
their children.

Queries return a `FeatureHit(feature, owner)` pair, since a feature alone does not know
where it lives and step 4's `locate()` / `get_extent()` will need the owner. This is not
the two-type problem returning: the pair duplicates no metadata and has no copy bridge.
`FeatureHit.name` and `.properties` forward, so most call sites read unchanged.

Concrete feature classes:

| class | identified by |
| --- | --- |
| `HalfSpaceFeature` | nothing — a half-space has one face |
| `SimpleRectangularPrismFeature` | `PrismFace` |
| `SimpleCylinderFeature` | `CylinderPart` (TOP / BOTTOM / BARREL) |
| `SimpleConvexPolygonExtrusionFeature` | `ExtrusionFeatureKey` |
| `SimpleLoftFeature` | `ExtrusionFeatureKey` |
| `SimplePathExtrusionFeature` | `ExtrusionFeatureKey` |
| `ProgrammableCSGFeature` | an arbitrary predicate |

Every feature also answers `feature_type() -> CSGFeatureType` (FACE / EDGE / POINT). It is
an **abstract method, not a field**, so a feature cannot be told it is something it is not:
the six `Simple*` classes return FACE as a constant because that is what they name by
construction, and only `ProgrammableCSGFeature` -- whose kind genuinely varies with its
predicate -- stores one, in `declared_type`. Being abstract also means a new feature class
cannot forget to declare its kind.

Kept off `FeatureProperties` deliberately: the type says what a feature *is*, the
properties say how it should be *treated*. Step 8's measurement dispatch keys off the pair
of types.

`ProgrammableCSGFeature` is the extension point: a formula-defined region, half a face, or
an edge derived from two other features, with no new class and no change to the owner's
query path. Step 5's derived edges are expected to use it. Each simple class types its own
key concretely, so the `FeatureKey` union and its `isinstance` guards are gone.

`Cylinder` and `ConvexPolygonSimpleLoft` can now carry names at all, which they could not
before — a peg hole was permanently anonymous.

### D3 — Edges are the conjunction of their parents (`cutcsg.py`)

A `CSGFeature` is *already* implicitly bounded — by which points its `test_point` accepts.
So an edge needs no bounds of its own:

```python
@dataclass(frozen=True)
class DerivedEdgeFeature(CSGFeature):
    a: CSGFeature
    b: CSGFeature

    def test_point(self, owner, point, eps=None):
        return self.a.test_point(owner, point, eps) and self.b.test_point(owner, point, eps)
```

(Or a `ProgrammableCSGFeature` whose predicate is that conjunction, if it turns out no
extra class is warranted. Note both parents must share an owner for the single-owner form
above; an edge between features of two *different* primitives needs the pair of owners,
which is what `FeatureHit` already carries.)

Note the deliberate asymmetry: `locate()` returns an **unbounded** `Line` for the
measurement math ("as if they were infinite lines"), while `test_point` stays bounded for
picking. Same feature, two views, no conflict.

This also survives a face feature that is not a whole face (e.g. the lower triangle of a
prism face). Whatever partial region its `test_point` defines automatically bounds every
edge derived from it, with no extra machinery.

Cases to guard:

- **Parallel parents** — no intersection. Not an edge; skip.
- **Coincident parents** — the planes are the same. Not an edge either, but keep the
  relation: coplanarity is exactly the "rough face matches the perfect timber within" test
  that feature 3 needs.
- **Two unbounded parents** — two `HalfSpace` features conjoined give an unbounded line,
  because `HalfSpaceFeature.test_point` delegates to the infinite plane. Bounding must come
  from the enclosing solid in that case; crop explicitly rather than letting a dimension
  line run to the horizon.

**Naming:** the ordered pair of parent names, with a deterministic order so the same edge
gets the same identity regardless of which way traversal reached it — sort by
`(group, name)`. Reads well in a breadcrumb: `tenon_front x ptw.right`.

### D4 — Extent, for placing annotations (`cutcsg.py`, `runner.py`)

(The `CSGFeatureKind` half of this landed early, as `CSGFeatureType` on `CSGFeature` —
see D2. What remains here is the extent.)

Measurement rendering needs to know roughly *where* a feature is, separately from the
unbounded geometry it measures against:

```python
@dataclass(frozen=True)
class CSGFeatureExtent:
    anchor: V3                             # face center / edge midpoint / the point
    ends: Optional[Tuple[V3, V3]] = None   # edges: the two endpoints
    aabb: Optional[BoundingBox] = None     # faces: rough extent

class CSGFeature:
    def get_extent(self) -> CSGFeatureExtent: ...
```

Approximate is fine, and there is a nearly free way to get it for real features:
`_extract_highlight_mesh` already walks every triangle centroid to build the highlight
geometry. Compute the extent in that same pass — anchor is the centroid of matched
triangles, `aabb` is their bounds, and for an edge the two endpoints are the extreme
matched points along the line direction.

That is correct for free in the case that matters most: a face cropped by the CSG tree
reports the extent of what actually survives, not of the uncut primitive. Non-real features
have no triangles and need the analytic route (D5).

Anchor convention precedent already exists: `locate_face` (`measuring.py:419`) anchors its
`Plane` at the center of the face surface.

### D5 — Non-real features always win, and get cropped (`cutcsg.py`, viewer)

Pick order becomes, unconditionally:

1. Non-real features, tested directly with no mesh check.
2. Real features, gated on the point being on the rendered boundary.

**Snap tolerance.** A non-real feature is usually a line or a point, and you cannot click
exactly on a line. It needs a distinctly larger snap tolerance than the surface epsilon,
and ideally one derived from screen space rather than world space — otherwise a peg-hole
axis is unhittable zoomed out and greedy zoomed in. This is ordinary CAD snapping; it is a
second tolerance, not a second mechanism.

**Cropping.** A non-real feature's extent is its own geometry clipped to the enclosing
timber's **uncut** body (`get_extended_actual_csg_local`), *not* the cut result — a peg
hole is a void, so clipping to the cut result yields nothing. Clip the parametric line
against the base solid to find entry and exit; for an axis-aligned hole through a prism
that is exact and cheap.

Cropping to the primitive's own `start_distance`/`end_distance` alone is not enough: joint
code routinely over-extends primitives for robustness (the tenon prism's `back_extension`,
for one), so raw extents are longer than the visible feature.

Non-real features must also be *rendered* as visible, pickable overlay geometry so the user
knows they are there. Precedent: the `cylinderAxis` payload (`runner.py:566`) already drives
camera-facing tangent silhouettes for round accessories (`viewer-app.js:4424`).

### D6 — Reserved PTW and rough face names (`timber.py`)

Split `_timber_face_tags()`:

```
_ptw_face_tags()    ->  ptw.right,   ptw.left,   ptw.front,   ptw.back,   ptw.top,   ptw.bottom
_rough_face_tags()  ->  rough.right, rough.left, rough.front, rough.back, rough.top, rough.bottom
```

The `ptw.` and `rough.` prefixes are **reserved** — joint authors may not use them — and
every timber has exactly one set of each. That guarantees these faces are always uniquely
identifiable, which is what the drawing rules depend on.

The split is clean in the code: all four PTW paths route through
`_create_extended_rectangular_prism` (`timber.py:1679`) or
`get_perfect_timber_within_csg_local` (`timber.py:1009`); the rough prisms are the two
inline `Timber` constructions whose `named_features=` lines are at `timber.py:1204` and
`timber.py:1227`. Six call sites.

Viewer behaviour:

- Render PTW, rough, or both. `geometry-mode.js` already has the mode plumbing and the
  payloads (`perfectTimberWithinVertices`, `perfectBoxNoJoints`, `roughBoxNoJoints`).
- **For now:** a measurement draws only if the feature it references is currently rendered.
- **Pinned, not designed:** showing PTW measurements while rendering the rough timber.
  Do not build toward it yet.

### D7 — Joint attribution on CSG nodes (`timber.py`)

```python
@dataclass(frozen=True)
class Cutting:
    ...
    joint_ticket: Optional[JointTicket] = None
```

`Joint` (`timber.py:2399`) already holds both its `ticket` and its `cuttings` dict, so stamp
each cutting with the owning joint's ticket at `Joint` construction (via
`dataclasses.replace` — `Cutting` is frozen), and have `get_negative_csg_local()` carry it
onto the labelled wrapper node it already builds.

Every subtree of a cut then knows its joint, and no joint function has to pass anything.
This is what feature 1's "joint the feature came from" reads, and it is strictly better than
inferring it from the subtract index.

### D8 — Long center planes (`timber.py`, `measuring.py`)

Add two, named for the face pair they bisect (matching the existing `RIGHT_FRONT_EDGE`
convention), at enum values past the current contiguous 1–27 range so the `range()` guards
in `TimberFeature`'s converters stay valid:

```python
class TimberFeature(Enum):
    ...
    RIGHT_LEFT_CENTER_PLANE = 28   # normal along local X, contains the centerline
    FRONT_BACK_CENTER_PLANE = 29   # normal along local Y, contains the centerline

class TimberLongCenterPlane(Enum):
    RIGHT_LEFT = 28
    FRONT_BACK = 29
```

Plus a `center_plane()` converter alongside the existing `face()` / `edge()` /
`centerline()` ones, and a `locate_center_plane(timber, plane)` in `measuring.py` — the
geometry is already there via `locate_plane_from_centerline_in_direction`
(`measuring.py:585`).

The TOP/BOTTOM bisector is deliberately excluded: it is not a *long* plane, and it moves
whenever an end cut changes the timber's effective length, so it is a poor thing to measure
from.

### D9 — Reference faces: warn, don't assert (`timber.py`)

`_validate_reference_faces` (`timber.py:545`) currently hard-asserts that a reference face's
rough half-size equals its PTW half-size. Downgrade **that specific check** to
`warnings.warn`: a timber with no perfect faces still needs somewhere to measure from, and
the right answer there is to pick a face anyway and render the internal PTW face to carry
the measurements. Keep the "must be a valid `TimberLongFace`" assert as an assert.

While in there: the coincidence test duplicates `is_face_perfect` (`timber.py:1086`), which
already exists and handles all four long faces. Call it instead of reimplementing the
half-size comparison.

**TODO (recorded, not scheduled):** replace `reference_faces: tuple[str, ...]`
(`ticket.py:53`) with an ordered `reference_features` priority list — faces, edges, and
center planes, tried in order. Strictly more general, drops the rough ≡ perfect requirement
entirely, and is the natural home for the drawing generator's reference-priority tagging.
Left as a TODO because the feature identity work above must land first for it to have
anything to point at.

---

## Gaps by user-facing feature

### Feature 1 — richer selection display

Today the info line is a single string, `timberName > face (label)`, built in `updateInfo`
(`viewer-app.js`).

- **Feature type** — `CSGFeatureType` (FACE / EDGE / POINT) is on every feature and
  forwarded by `FeatureHit`. Done; the viewer just has to show it.
- **Joint it came from** — D7 delivers this directly.
- **Expandable CSG feature tree** — needs finding 2 fixed first; the hierarchy is already
  authored. Two-way binding is the new work: clicking a node highlights the feature in 3D,
  and picking in 3D reveals and selects the node. `SelectionStore` already has a `csgNode`
  layer-node shape (`{type:'csgNode', timberKey, path}`) to hang this on. Since this is
  explicitly a debugging tool, show the **whole** tree including untagged intermediates,
  not just the tagged nodes `_walk_tagged_csg` collects.
- **Which local timber face it points toward** — `get_closest_oriented_face_from_global_direction`
  (`timber.py:809`) already does this. Feed it the feature's outward normal at the pick
  point rather than the prism-axis approximation `_generic_label_in_timber_local_space`
  uses today.

### Feature 2 — stored feature + pairwise measurement

Nothing exists yet. `SelectionStore` has a `selectedFeatures` array, but nothing writes to
it from the CSG path — CSG selection goes to a separate `csgSelection` slot holding
`{timberKey, path, featureLabel}`, which is not a stable identity.

- A serialisable feature reference that survives a rebuild: timber key + CSG path + feature
  name. Needs finding 2 fixed.
- `locate()` → global `Point` / `Line` / `Plane` (D3), and `get_extent()` for annotation
  placement (D4).
- Local → global: the CSG tree is timber-local, so both sides of a cross-timber measurement
  lift through `timber.transform`. `adopt_csg` does this for whole trees.
- A measurement dispatch keyed on `(kindA, kindB, relationship)`. The relationship tests
  (`are_vectors_parallel`, `are_vectors_perpendicular`) are already in `rule.py`.
- Renderers: the viewer already bundles fat lines (`LineSegments2` / `LineMaterial`) and
  `CanvasTexture` sprites, so extension lines + dimension line + label is buildable with
  what is in the bundle.
- Per-measurement style overrides, and an accessory exclusion — member type is already
  tagged `'accessory'` vs `'timber'` in the mesh payload.
- Non-real features rendered as visible, pickable overlay geometry (D5).

### Feature 3 — drawing generation prerequisites

- **Reference faces** — `TimberTicket.reference_faces` exists and validates. D9 relaxes it;
  nothing consumes it yet and it is not in the viewer payload.
- **Center planes** — D8.
- **Reference edges** — an edge between two reference faces, i.e. D3's derivation. Falls out.
- **PTW / rough disambiguation** — D6. Load-bearing: every rule here turns on it.
- **PTW wireframe to measure from** — payloads and mode-swapping already exist. Rendering
  PTW as an overlay *alongside* actual geometry, rather than instead of it, is the new part.
- **Measurement tags** — the reference / priority / no-measure / ladder vocabulary from the
  4/14/2026 TODO notes. Lands as a field on `NamedFeature` (D2).
- **Ladders** — chains of feature-to-feature references, so they need stable feature
  identity across joints first. Same dependency as feature 2.

---

## Build order

1. ~~**Fix `tag` → `label` in `runner.py`.**~~ **DONE** -- see "Implementation notes".
2. ~~**Tolerance parameters, then delete the float shadow.**~~ **DONE** -- see
   "Implementation notes".
3. ~~**`NamedFeature` dataclass + reserved PTW/rough names.**~~ **DONE** -- see
   "Implementation notes".
4. ~~**Build out `CSGFeature`.**~~ **DONE** -- see "Implementation notes".
5. **Derive edges from face groups.** D3. A x B1 to start, with the parallel / coincident /
   unbounded guards and pair-derived naming.
6. **Joint attribution + the CSG feature tree UI.** D7 plus feature 1's expandable tree with
   two-way selection. This is the debugging surface for everything after it, which is a good
   reason to have it early.
7. **Name features across the joint library.** The long tail — one call site today.
   Prioritise `shavings/relief.py` and `build_a_butt.py`, which generate most of the
   geometry, and design defaults so common cases need no hand authoring.
8. **Feature identity + measurement pairs.** Feature 2: serialisable references, the
   pairwise dispatch table, the three.js dimension renderer, non-real overlay rendering.
9. **Reference features groundwork.** D8 and D9: center planes, the warning downgrade, and
   the recorded TODO for generalising `reference_faces`.

Steps 1 and 2 are worth doing regardless of where the rest lands — they remove a broken code
path and a redundant one.

---

## Implementation notes (steps 1-4)

### Step 1 -- `tag` -> `label`

All seven reads in `runner.py` retargeted. Since nothing consumed the wire keys yet
(`mergeCSGTreePayload` in `layers-panel.js` is a stub and the `cuts` payload has no JS
reader), the naming was made honest throughout rather than left half-renamed:

- `_walk_tagged_csg` -> `_walk_labeled_csg`, `_find_tagged` -> `_find_labeled`
- wire keys `"tag"` -> `"label"`, `"taggedCSGs"` -> `"labeledCSGs"`
- local names `base_tag` / `ch_tag` / `sub_tag` -> `*_label`

"Tagged" was actively misleading next to ticket `tags`, which are a real and separate
concept the same file also handles (`_normalize_ticket_tags`).

Regression coverage in `tests/test_kigumi_csg_navigation.py`. Reintroducing the exact
historical bug fails 7 of its tests. `test_cutcsg_label_field_is_named_label` asserts the
kumiki-side field name directly, so the next rename fails loudly rather than silently.

### Step 2 -- tolerance, and deleting the float shadow

**Implemented exactly as D1 specifies: an explicit parameter, threaded.** An earlier
attempt used a module-level tolerance scope instead, on the theory that an explicit
epsilon could not reach the helpers `PathExtrusion` delegates to. That was wrong, and the
numbers say so. Measuring the actual call closure by fixed point over the AST -- start at
the five query methods, keep any callee that reaches a tolerance-sensitive `safe_*`
primitive -- gives **14 method names**, not the whole of `pathcsg`:

```
contains_point            is_point_on_boundary     get_outward_normal
get_all_features          find_feature             test_point
contains_point_2d         is_point_on_boundary_2d  locate_boundary_segment
ray_crossings             closest_point            outward_local_normal
_monotonic_subranges      _point_on_side
```

Six of those were new (the `FancyPath` / `PathSegment` ones); the rest were already being
touched. Across all their class implementations that is 66 `def`s and 187 threaded call
sites, applied mechanically from the AST rather than by hand.

Deliberately excluded from the tolerance-sensitive set: `safe_norm`,
`safe_normalize_vector`, `safe_dot_product`, `safe_transform_vector`. Those are pure
arithmetic, and normalize's internal `EPSILON_FLOAT` is a degeneracy guard that should not
scale with a pick tolerance.

`rule.py` gained an optional `eps` on `safe_compare`, `safe_zero_test`,
`safe_equality_test`, `are_vectors_parallel` and `are_vectors_perpendicular`. All are
trailing optional parameters, so every existing call site in the library is unaffected.

**First bug found: `eps` did not mean the same thing on every primitive.** Several
containment tests compare a *squared* distance against the tolerance directly --
`safe_zero_test(distance_sq)` in `ConvexPolygonExtrusion._point_on_side`,
`ConvexPolygonSimpleLoft`, and `FancyPath.locate_boundary_segment`. Passing eps straight
through would have made `eps=5e-4` mean half a millimetre against a prism face but **22
millimetres** against a polygon edge. `_squared_eps()` now adapts the value at those eight
sites, so `eps` is a plain distance in model units everywhere. `None` passes through
unchanged, preserving the historical default (1e-10 on the squared value, an effective
linear tolerance of 1e-5).

**Second bug found: `ArcSegment.ray_crossings` domain error.** It computes
`sqrt(1 - sin_theta**2)` after a hit gate that accepts `y` within the comparison tolerance
of a monotonic subrange's endpoints. At a widened tolerance `sin_theta` lands far enough
outside [-1, 1] to blow past `rule.sqrt`'s own small-negative guard, raising
`ValueError: math domain error` on any path-extrusion pick. `sin_theta` is now clamped --
the gate has already established the point lies on the subrange, so the excess is noise.

**`_detect_face_label` rewritten.** Two layers now: kumiki's `find_feature` first (a
declared name always beats a geometric guess), then a generic fallback that names the face
by whichever of the timber's six local directions its *outward normal* points along. That
fallback replaces `_generic_label_in_timber_local_space`, which approximated the normal
from the prism's rotation axis and therefore only worked for `RectangularPrism`. The
normal-based version works for every primitive. `HalfSpace` still reports `cut_plane` and a
cylinder barrel still reports `cylindrical_surface`, since neither has a face in the
timber's sense.

**Verified equivalence before deleting.** Both implementations were run over every triangle
centroid of five patterns (524 surface points). `is_point_on_boundary` disagreed on 86
points, **all in the same direction** -- kumiki finds boundary where the shadow found none,
i.e. exactly the extrusion / path-extrusion / loft surfaces that were unselectable. Zero
regressions in the other direction.

`contains_point` disagreed on 122, mixed. Those come from kumiki's coincident-surface rule
in `Difference.contains_point` (base and subtract sharing a face plane, resolved by
comparing outward normals), which the shadow's `-eps` strict-interior test did not model.
It does not affect picking: `contains_point` survives only as a tie-break in
`_resolve_csg_at_path` when several children share a label, and the boundary answers -- what
picking actually uses -- agree everywhere.

**Performance.** kumiki is ~2x the shadow on a whole-tree walk (~72 us, once per click) and
~3.7x on the per-triangle leaf test used by highlight extraction. Worst realistic case
measured: a 3-cut timber with 572 triangles at 7.9 ms for the full highlight pass. Fine for
a click; revisit only if timbers get much denser.

**Result.** Previously unselectable geometry now resolves with real paths:

```
dovetail tongue -> ('sliding_dovetail', 'dovetail_tongue_profile')  ConvexPolygonExtrusion
dovetail housing -> ('sliding_dovetail', 'dovetail_housing')        ConvexPolygonExtrusion
path decoration -> ('path_extrusion_corner_end_decoration',)        PathExtrusion
roundovers      -> ('roundover_decoration', 'roundover_top_left')   Cylinder   (x12, each distinct)
```

### Step 3 -- feature classes, feature types, and reserved PTW/rough names

No compat shim: the old `List[Tuple[str, Face]]` form had 12 construction sites in total
(one in the joint library, eleven in tests), so a clean break was cheaper than carrying a
deprecation path on a published API.

**Feature classes (D2).** Built once around a stored `NamedFeature` declaration plus a
resolved `CSGFeature`, then rebuilt when that proved too complicated -- see D2 for the
shape that shipped and why. The rebuild deleted 127 lines of duplicated matching logic,
the `NamedFeature` type, `_metadata_from`, the `FeatureKey` union and every `isinstance`
guard that union forced, and replaced six per-primitive `get_all_features` overrides with
one implementation on `CutCSG`.

`priority` was previously hardcoded to 0 at all six construction sites, making
`find_feature`'s priority sort a no-op. It is now settable via `FeatureProperties` and
covered by a test.

**`CSGFeatureType` (D4, pulled forward).** FACE / EDGE / POINT, forwarded by `FeatureHit`.
First built as a field with a FACE default, then changed to an abstract method so it cannot
be set incorrectly -- a `SimpleRectangularPrismFeature` had no way to refuse `EDGE`, and
step 5 and step 8 both act on this, so a wrong value would propagate into derived edges and
measurement dispatch. As a method there is nothing to set: face-by-construction classes
return a constant, `ProgrammableCSGFeature` stores `declared_type`, and abstractness stops
a new class forgetting to declare its kind. Tests cover all three.

**`FeatureGroup` + `FEATURE_GROUP_PAIRS` (D3 groundwork).** A/B1/B2/C with
`feature_groups_intersect()`. A test asserts the table is symmetric in both directions, so
step 5 can rely on that rather than checking both orders.

**New key enum.** `CylinderPart` (TOP / BOTTOM / BARREL). The barrel is deliberately a
single feature: a bore wall is one thing to reference, and there is no non-arbitrary way
to divide a curved surface into named faces. (A `FeatureKey` union over every key type
existed in the first cut and is gone -- each Simple* class now types its own key.)

**`Cylinder` and `ConvexPolygonSimpleLoft` can now carry names**, which they could not
before -- a peg hole was permanently anonymous. Both needed a new feature class;
the loft also needed a `_point_on_side` helper, which tests against the cross-section at
the point's own height because its sides are ruled surfaces, not planes.

**Reserved `ptw.` / `rough.` prefixes (D6).** `_timber_face_tags()` split into
`_ptw_face_tags()` / `_rough_face_tags()`, both group B1. The rule applied: a prism's tag
set names *which prism it is*, not whether the two happen to coincide -- so a perfect
timber's actual body is still `rough.*`, and coincidence stays a separate question
answered by `is_face_perfect`. `_create_extended_rectangular_prism` serves both the actual
and the perfect paths, so it takes the tag set as a parameter; the four call sites were
assigned from their enclosing method (`get_extended_perfect_csg_local` -> ptw, the three
`get_extended_actual_csg_local` overrides -> rough).

**Runner cleanup that fell out.** `_declared_feature_names()` replaces two isinstance
ladders that only understood `RectangularPrism` and `HalfSpace`, so the CSG tree panel and
the member list's feature count now see cylinders, extrusions and lofts too.
`_handle_find_csg_by_path` had a latent bug -- it assigned a `PrismFace` enum to
`feature_target` and passed it where a CSG was expected. Unreachable while paths were
broken (step 1), live now; the mesh target stays the CSG and `feature_label` does the
per-face narrowing, which is how `_extract_highlight_mesh` already worked.

**Typecheck.** The wide `FeatureKey` union in the first cut produced 7 new `ty`
diagnostics where a key reached a helper expecting `int`. The redesign removes the union
entirely, so those cannot recur. Back to the 8 pre-existing diagnostics.

**A mistake worth recording.** Deleting the six obsolete `get_all_features` overrides by
AST line range, I sorted the ranges by class *name* instead of line number, so the
deletions applied out of order and corrupted unrelated method bodies in `cutcsg.py`.
Recovered by reverting `cutcsg.py` / `pathcsg.py` to the step-2 commit and reapplying the
redesign with anchor-based string replacement instead of line numbers -- cheap here only
because everything step 3 had added to those two files was superseded by the redesign
anyway. Delete by matching text, not by coordinates computed from a stale parse.


### Step 4 -- locate, extent, and non-real features

**Prerequisite: `kumiki/geometry.py`.** `locate()` returns `measuring.py`'s `Point` /
`Line` / `Plane`, but `measuring` imports `timber` imports `cutcsg`, so cutcsg could not
reach them. Those six primitives depend on nothing but `rule`, so they moved to a new
`geometry.py` below the whole chain; `measuring.py` re-exports them, so every existing
`from kumiki.measuring import Plane` still works.

**`locate(owner)` (D4).** Returns the unbounded geometry the feature lies on, in the
owner's (timber-local) space, or None. None is a real answer, not a gap: a cylinder's
barrel, a lofted side, and an extrusion side following a curved path segment are all
perfectly good features to select and highlight, but no single plane describes them, so
measurement has to decline rather than invent one. The same graceful-decline
`PathExtrusion.test_point` already made for curved segments.

Loft sides decline even though a pure per-axis taper *is* planar -- detecting that case is
worth doing when something actually needs to measure from a tapered side, and returning a
plane that is right for some lofts and wrong for others is worse than declining.

**`get_extent(owner)` (D4).** `CSGFeatureExtent(anchor, ends, aabb)`, analytic. Note it is
answerable where `locate()` is not: a cylinder barrel has no plane but a dimension line
still needs somewhere to attach, so it gets an anchor. A half-space is the reverse -- it
locates as a plane but has no extent at all, since the plane is unbounded.

The runner-side shortcut from D4 (deriving extents from the triangles
`_extract_highlight_mesh` already walks) is NOT built yet. It is still the right way to get
the extent of a face the CSG tree cropped; the analytic version describes the uncut
primitive.

**Non-real features (D5).** `get_all_features` now splits its work:

- real features are gated on the point being on this node's boundary,
- non-real features are not, because they name nothing a boolean could have removed.

`find_feature` sorts by `(real, priority)`, so a non-real feature outranks a real one
outright -- selecting a line inside a solid is a deliberate snap, and a surface it happens
to sit on should not steal the click.

`snap_eps` is a second, separate tolerance for the non-real tests, defaulting to `eps`. It
wants to be much larger in practice: you cannot click exactly on a line.

**A gating bug found while building it.** `Difference` and `Intersection` early-returned
when the point was off their own boundary, which would have made non-real features
unreachable in exactly their motivating case -- a bore's centre axis lies in the void the
bore made, never on the cut solid's surface. Replaced with
`_drop_real_hits_off_boundary()`: traverse once, then drop only the *real* hits if this
node's surface does not survive at that point. Preserves the previous behaviour for real
features exactly.

**Where `_features` lives.** First put on `CutCSG` so it was declared once, with an assert
in each compound `get_all_features` to catch the unsupported case. Moved onto the
primitives instead: a compound node has no surface of its own to name, so offering it the
field at all was the wrong shape, and the assert was a symptom. Now giving one features is
a construction-time `TypeError` -- caught always, rather than only when a query lands on
the feature -- and no assert is needed.

**`crop_line_to_csg()` (D5).** Clips an infinite line to the span inside a solid, by
sampling then bisecting the two crossings. Deliberately a free function, not a method:
the relevant solid is the enclosing timber, and a feature's owner (the bore primitive)
knows nothing about it, so the caller supplies it. Tested including the trap the plan
called out -- clipping a bore axis to the *cut* solid finds nothing, because the bore is a
void; it has to be the uncut body.

**A bug `ty` caught that the tests did not.** `PathSegment.start` / `.end` are properties,
and the new `locate()` called them as methods. No test covered path-extrusion `locate()`
at the time, so it would have shipped. Fixed, and `TestPathExtrusionLocate` now covers
straight sides, caps, curved-side decline, and extent.


### Follow-ups noticed while in there

- Some cuts produce a doubled path segment, e.g.
  `('sliding_dovetail', 'sliding_dovetail', 'dovetail_tongue_profile')`, because
  `Cutting.label` and the inner CSG's own `label` are the same string. Cosmetic, and it
  comes from the joint authoring rather than the navigation -- worth collapsing when step 7
  passes through the joint library.
- `ConvexPolygonExtrusion.get_outward_normal` returns `None` for a few points (edges and
  corners), which falls back to the bare label `"face"`. Pre-existing; not a regression.
- `cutcsg.py`'s stale "uses SymPy symbolic math" docstring is fixed.

---

## Inventory: what already exists

| Need | What exists | Where |
| --- | --- | --- |
| Geometric vocabulary | `Point`, `Line`, `Plane`, `UnsignedPlane`, `HalfPlane`, `Space` — all unbounded | `measuring.py` |
| Feature enum for timbers | `TimberFeature`: faces 1–6, centerline 7, long edges 8–11, short edges 12–19, corners 20–27 | `timber.py:45` |
| Parallel / perpendicular tests | `are_vectors_parallel`, `are_vectors_perpendicular`, `safe_compare` | `rule.py` |
| "Which face does this point toward" | `get_closest_oriented_face_from_global_direction` + long/end variants | `timber.py:809` |
| Perfect-face predicates | `is_face_perfect(face)`, `is_perfect_timber()` — the rough ≡ PTW test | `timber.py:1086`, `:1110` |
| Imperfect region as CSG | `get_imperfect_fringe_csg_local()` = actual minus PTW | `timber.py:1128` |
| Reference-face validation | `_validate_reference_faces` (duplicates `is_face_perfect`) | `timber.py:545` |
| Face-center anchor convention | `locate_face` returns a `Plane` anchored at the face center; `locate_edge` returns a `Line` | `measuring.py:419`, `:447` |
| Center-plane geometry | `locate_plane_from_centerline_in_direction` — needs only an enum + wrapper | `measuring.py:585` |
| PTW / rough geometry in viewer | `perfectTimberWithin`, `perfectBoxNoJoints`, `roughBoxNoJoints` payloads + client-side swap | `runner.py`, `geometry-mode.js` |
| Dimension-line rendering | `LineSegments2` + `LineMaterial` (real linewidth), `CanvasTexture` sprites | `webview/vendor`, `viewer-app.js` |
| Non-real overlay precedent | `cylinderAxis` payload driving camera-facing tangent silhouettes | `runner.py:566`, `viewer-app.js:4424` |
| Joint provenance | `Frame.source_joints`, `CutTimber.joints`, `Cutting` ↔ `Joint` via `Joint.cuttings` | `timber.py` |
| Local ↔ global CSG transport | `adopt_csg`, `translate_csg` | `cutcsg.py` |

---

## Verification

Findings were verified against the working tree at `a70403e` by triangulating the cut
timbers of the mortise-and-tenon, sliding-dovetail, path-extrusion and roundover patterns
and running the runner's own picker over every triangle centroid.

`find_feature` over meshed centroids, default epsilon vs. patched:

```
# default EPSILON_FLOAT = 1e-10
symbolic find_feature over 28 pts: 1.11 ms
Counter({None: 26, 'bottom': 2})

# same call, EPSILON_FLOAT patched to 5e-4
butt_timber      {'bottom': 2, 'left': 2, 'back': 2, 'front': 2, 'right': 2,
                  'tenon_back': 2, 'tenon_left': 2, 'tenon_front': 2,
                  'tenon_right': 2, 'tenon_top': 2, None: 8}
receiving_timber {'back': 2, 'bottom': 2, 'left': 2, 'front': 8,
                  'top': 2, 'right': 2, None: 10}
```

The residual `None`s are the shoulder plane (8 tris, `label=` not `named_feature=`) and the
mortise hole (10 tris, no `named_features` at all).

Runner picker over every triangle, `(path, node type, node label, reported face label) -> count`:

```
=== sliding dovetail, end_to_face_butt_timber
    ((), 'RectangularPrism', None, 'face') -> 10        # the dovetail itself
    ((), 'RectangularPrism', 'dovetail_shortened_clearance', 'bottom') -> 4
    ((), 'RectangularPrism', 'dovetail_length_clearance', 'bottom') -> 4

=== path extrusion corner end decoration
    ((), 'RectangularPrism', None, 'face') -> 18        # the whole decoration
    ((), 'RectangularPrism', None, 'back') -> 11

=== roundover decoration
    ((), 'Cylinder', None, 'cylindrical_surface') -> 192  # pickable, no name
```

Note the empty `()` path in every row — that is finding 2.

CSG tree of a basic mortise and tenon, showing labels present but `tag` absent:

```
--- butt_timber
  root: Difference  label: None   tag: MISSING
  _walk_tagged_csg collected: []
    Difference
       RectangularPrism   named_features=[right, left, front, back, top, bottom]
       SolidUnion         label=mortise_and_tenon
          Difference
             HalfSpace          label=shoulder       named_features=None
             RectangularPrism   label=tenon          named_features=[tenon_right,
                                    tenon_left, tenon_front, tenon_back, tenon_top]
          HalfSpace

--- receiving_timber
  _walk_tagged_csg collected: []
    Difference
       RectangularPrism   named_features=[right, left, front, back, top, bottom]
       SolidUnion         label=mortise_and_tenon
          RectangularPrism   label=mortise_hole    named_features=None
```

---

## Loose ends

- `cutcsg.py`'s module docstring still claims "All operations use SymPy symbolic math for
  exact computation." Stale since the float migration.
- `.claude/plans/assembly-solver-v2.md` refers to `docs/plans/assembly-ordering.md`; the
  file actually lives at `.claude/plans/assembly-ordering.md`.
- `docs/concepts.md` has a `### reference faces` heading with body `TODO`. D6/D8/D9 give it
  something to say.
