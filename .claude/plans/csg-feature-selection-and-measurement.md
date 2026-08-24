# CSG feature selection and measurement: audit + design

## Status — step 6 part A done (2026-08-23)

Steps 1-5 are done, plus part A of step 6. All committed on branch
**`csg-feature-selection-steps-1-5`**, unpushed, with `main` merged in. Land with:

```
git checkout main && git merge --ff-only csg-feature-selection-steps-1-5
```

Suite at the tip: **1020 python + 9 gui + 213 jest passing**, and `make typecheck` now
passes clean -- the eight long-standing diagnostics were cleared in `6375cd5`, so a new
error finally has somewhere to stand out. `uv.lock` no longer goes dirty on every `uv run`
(`1028300`).

### What works now

Clicking a timber in kigumi resolves to a named CSG feature with a real breadcrumb path.
Every primitive can name features; features know their own type, geometry and rough extent;
tolerances are a coherent per-type struct that scales with zoom; and edges derive from
declared face pairs. Clicking an arris returns e.g. `rough.front x rough.right` through the
existing runner path.

| # | Step | Commit |
| --- | --- | --- |
| 1 | Fix `tag` -> `label` in runner.py | `8b43c83` |
| 2 | Tolerance on the point queries; delete kigumi's float shadow | `638fcb9` |
| 3 | Real feature model: `CSGFeature`, `feature_type()`, reserved `ptw.`/`rough.` names | `f828b14` |
| 4 | `locate()`, `get_extent()`, non-real features, `crop_line_to_csg` | `a06b1a8` |
| — | One epsilon constant; `FeatureTestTolerances` | `cc9467a` |
| — | `safe_zero_test_sq` | `d9e03c6` |
| — | Rename epsilons -> test tolerances | `c3f1a04` |
| 5 | Derive edges where declared faces meet | `dce0689` |

### Picking up: step 6, parts B-D

Part A is done (`1f7997a`): picking now reports `jointName`, derived rather than stored --
see D7 for why the stored version was built and rejected. What is left:

- **B (python).** `serialize_cut_csg_tree` should walk the whole timber's rendered CSG
  rather than one cutting's negative, include untagged intermediates, and carry per-node
  feature metadata.
- **C (python).** `find_csg_at_point` still needs `featureType` and `facesToward`.
  `jointName` landed with part A.
- **D (js).** `mergeCSGTreePayload` in `layers-panel.js` is a stub; the multi-line info
  panel and two-way tree binding are the remaining work.

### Original step 6 outline

**Joint attribution + the CSG feature tree UI.** Outlined in full below under "Build order",
but the short version is that the transport already exists end to end and only the two ends
are missing:

- **A (python).** `Cutting.joint_ticket`, stamped in `Joint.__post_init__` via
  `object.__setattr__` so none of the 32 `Joint(...)` call sites change.
- **B (python).** `serialize_cut_csg_tree` should walk the whole timber's rendered CSG
  rather than one cutting's negative, include untagged intermediates, and carry per-node
  feature metadata.
- **C (python).** `find_csg_at_point` gains `featureType`, `jointName`, `facesToward` --
  all three now have their data.
- **D (js).** `mergeCSGTreePayload` in `layers-panel.js` is a stub; the multi-line info
  panel and two-way tree binding are the remaining work.

A-C are testable python; D is JS with no harness beyond jest on pure modules. Doing A-C
first means a clean stopping point either way.

**Two decisions left open**, both in the step 6 outline: whether the CSG tree gets its own
pane or joins the layers panel (leaning own pane -- different lifetime, follows selection),
and whether derived edges appear in the tree at all (leaning no -- they belong to a *pair*,
not a node, so showing them per-node would mislead).

### Then

7 -- name features across the joint library (still one call site; `shavings/relief.py` and
`build_a_butt.py` generate most of the geometry). 8 -- measurement pairs, feature 2 proper.
9 -- reference features, center planes, the `reference_faces` warning downgrade.

### Known gaps, deliberate

- **A derived edge's `get_extent` is approximate.** `ends` is None and `anchor` is the
  infinite line's closest point to the origin, which need not be near the real edge.
  Harmless for picking; step 8 needs it fixed, which means cropping to the enclosing
  timber. Documented at the method.
- **A leaf query cannot see cross-primitive edges.** A tenon cheek meeting the timber body
  needs a node that sees both, and kigumi picking queries the leaf. Step 6/8.
- **Runner-side extent from triangles** (D4) not built -- the analytic version describes
  the uncut primitive, not what survived the CSG tree.
- **Coincident faces** are not detected as a coplanarity relation. That is the
  rough-matches-PTW test and belongs with step 9.
- **Derived edges are re-derived per query.** Caching belongs in a field separate from
  `_features`, which is authored rather than derived.

---

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

(Superseded in part: the feature *queries* now take a `FeatureTestTolerances` struct rather than
a bare `eps` — see "Feature epsilons" below. The lower-level point tests still take a plain
`eps` as described here.)

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
    a: OwnedFeatureHit      # parent feature + the primitive it lives on
    b: OwnedFeatureHit

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.EDGE

    def test_point(self, owner, point, test_tolerance=None):
        return (self.a.feature.test_point(self.a.owner, point, test_tolerance)
            and self.b.feature.test_point(self.b.owner, point, test_tolerance))

    def locate(self, owner) -> Optional[Line]:
        return intersect_planes(self.a.locate(), self.b.locate())
```

The two parents generally live on *different* primitives -- that is the whole point of
A x B1, a joint feature meeting the timber body -- so each is carried as an
`OwnedFeatureHit` (feature + the primitive it belongs to). The derived edge's own owner,
the one a query reports, is the **compound node** (`Difference` / `SolidUnion` /
`Intersection`) containing both: the first node in the tree that can see the pair at all.

Note the deliberate asymmetry: `locate()` returns an **unbounded** `Line` for the
measurement math ("as if they were infinite lines"), while `test_point` stays bounded for
picking. Same feature, two views, no conflict.

This also survives a face feature that is not a whole face (e.g. the lower triangle of a
prism face). Whatever partial region its `test_point` defines automatically bounds every
edge derived from it, with no extra machinery.

#### Finding them: two gathers

Derived edges cannot be inferred from the face hits a normal query returns. A face hit is
established at the *face* tolerance, and an edge wants the *edge* tolerance -- near an
edge, "within 0.5mm of both planes" is only about 0.7mm from the edge, so the 2mm snap
would never apply and `CSGFeatureType.EDGE` having its own tolerance would be pointless.

So `get_all_features` gathers twice, because "near enough to count" means a different
distance depending on what is being asked:

```python
tolerances = DEFAULT if test_tolerances is None else test_tolerances
hits = self.collect_hits(point, tolerances)                       # each at its own type
faces = faces_of(self.collect_hits(point, uniform(tolerances.edge)))
return _sort_feature_hits(hits + derive_edge_hits(self, faces))
```

`collect_hits` is the only recursive method. It tests each feature at the tolerance its own
type calls for, right where the feature is, and gates real ones on their primitive's
boundary. Compound nodes override nothing else: they extend the gather over their children
and apply `_drop_real_hits_off_boundary` at their own level.

An earlier version instead gathered once at `max(face, edge, point)` and refined that twice.
It works, but it needs `test_point` to be monotonic in its tolerance -- a subtle constraint
on every future implementation, and one that is easy to violate without noticing. Two plain
gathers cost a second traversal of a tree tens of nodes deep and need no invariant at all.

**Derivation runs in `get_all_features`, not in the gather**, and so happens once, at
whichever node the caller asked about. Putting it in `collect_hits` would either recurse
into itself or have every nested compound re-derive what its parent derives. Because of
that, nothing is deduplicated -- and nothing should be: two tenons on one timber
legitimately declare the same face names, so their edges share a name while being genuinely
different edges.

**A primitive derives its own arrises too**, since the logic lives on the base class rather
than on the compound nodes. That matters practically: kigumi picking navigates to a leaf
primitive and queries *that*, so it is what makes edges reachable from the viewer at all.

Caching the derived edges rather than re-deriving per query is the obvious later
optimisation, and belongs in a separate field from `_features` (which is authored, not
derived).

#### Cases to guard

- **Parallel parents** — no intersection. Not an edge; reject cheaply at derivation via
  `are_vectors_parallel`.
- **A non-planar parent** — `locate()` returns None for a cylinder barrel, a lofted side,
  or an extrusion side following a curved segment. The edge is still pickable; it just
  cannot be located, the same graceful decline `locate()` already makes.
- **Two unbounded parents** — two `HalfSpace` features conjoined give an unbounded line,
  because `HalfSpaceFeature.test_point` delegates to the infinite plane. Crop with
  `crop_line_to_csg` rather than letting a dimension line run to the horizon.
- **Coincident parents** — the planes are the same. Not an edge, and deliberately **out of
  scope here**: the relation is exactly the "rough face matches the perfect timber within"
  test, which belongs with the reference-face work in D9.

**Naming:** the ordered pair of parent names, with a deterministic order so the same edge
gets the same identity regardless of which way traversal reached it — sort by
`(group, name)`. Reads well in a breadcrumb: `tenon_front x ptw.right`.

**Ordering:** a derived edge outranks its own parent faces when both claim a point.
Selecting an edge is the more specific answer, and the existing `(real, priority)` sort in
`find_feature` needs the edge to come first.

#### Group assignment

PTW faces move from B1 to **B2**. B1 pairs only with A, which means two PTW faces never
form an edge -- and a timber's own four long arrises are exactly that. Feature 3 wants
them: a reference edge is defined as the edge between two reference faces. B2 pairs with A
*and* with itself, which is what timber faces actually want. Rough faces follow.

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

### D7 — Joint attribution is derived, not stored (`kigumi/runner.py`)

An earlier version of this section put a `joint_ticket` on `Cutting`, stamped by
`Joint.__post_init__`, and carried it onto CSG nodes via a `CutCSG.joint_ticket` field. That
was built and rejected. Three things were wrong with it:

- **It duplicated state that already has an owner.** `Joint.cuttings` *is* the
  relationship. A reverse pointer is a second copy to keep in sync, and `with_order()`
  rebuilds cuttings via `replace()`, so they genuinely can drift.
- **It made `cutcsg.py` import a construction concept.** A pure geometry module should not
  know what a joint is.
- **It cost six extra call sites** in `translate_csg` / `adopt_csg` purely to stop the
  field being silently dropped on rebuild -- a lot of surface for metadata. It also broke
  a test immediately: `replace()` in `__post_init__` fails on the `MockCutting` test double.

The mapping is already derivable from data that exists:

```
Frame.source_joints                   populated by Frame.from_joints
joint.cuttings.values()               every Cutting, with its Joint
render_timber_with_cuts_csg_local()   Difference(body, [cut.get_negative_csg_local() ...])
                                      subtract[i] <-> cut_timber.cuts[i], same order
```

So the runner does it: `_joint_by_cutting_id(cut_timber)` builds `{id(cutting): joint}`
from `CutTimber.joints`, and `_cutting_for_node(local_csg, cut_timber, target)` finds which
subtract subtree contains the picked node by identity. The one positional assumption --
that subtract order matches cuts order -- is read in a single function, next to the single
function that creates it, and is length-checked; everything else is identity-based.

`find_csg_at_point` returns `jointName`, or None for the timber's own body, which no joint
produced.

The one change to kumiki is populating `CutTimber.joints`, which existed but was only ever
initialised to `[]`. Reading that rather than `Frame.source_joints` keeps attribution local
to the timber being picked -- no frame is threaded through, and a Frame assembled by any
other route does not silently lose joint names. A `CutTimber` built by hand has no joints
and so declines, which is the honest answer.

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
5. ~~**Derive edges from face groups.**~~ **DONE** -- see "Implementation notes".
6. **Joint attribution + the CSG feature tree UI.** D7 plus feature 1's expandable tree
   with two-way selection. The debugging surface for everything after it, and the last
   piece of user-facing feature 1.

   The transport already exists end to end -- only the two ends are missing:

   | piece | state |
   | --- | --- |
   | `requestCSGTree` -> `serialize_cut_csg_tree` -> `csgTree` message | works |
   | `mergeCSGTreePayload` in `layers-panel.js` | **stub, renders nothing** |
   | `requestCSGByPath` -> `_handle_find_csg_by_path` -> highlight | works |
   | `selectionManager.selectCSG(timberKey, path, featureLabel)` | exists |
   | `csgNode` layer-node shape `{type, timberKey, path}` | exists |

   **A. Joint attribution (python).** `Cutting.joint_ticket`, stamped in
   `Joint.__post_init__` via `object.__setattr__` -- `Joint` is frozen, and `timber.py`
   already uses `__post_init__` elsewhere. None of the 32 `Joint(...)` construction sites
   change, and `with_order`'s `replace()` re-stamps idempotently.
   `get_negative_csg_local()` then carries it onto the labelled wrapper it already builds.

   **B. Tree payload (python).** Three changes to `serialize_cut_csg_tree`:
   walk the whole timber's `render_timber_with_cuts_csg_local()` rather than one cutting's
   negative CSG (that is the tree picking actually runs against); include untagged
   intermediates, since those are exactly what you need to see when something is wrong;
   and carry per-node feature metadata (name, type, group, real).

   **C. Enrich the pick result (python).** `find_csg_at_point` returns
   `{path, featureLabel, highlightMesh, stats}`; feature 1 wants three more, all of which
   now have their data: `featureType` from `hit.feature_type()`, `jointName` from A, and
   `facesToward` from `get_closest_oriented_face_from_global_direction` fed the feature's
   outward normal at the pick point -- replacing `_generic_label_in_timber_local_space`,
   which approximates from the prism's rotation axis and only works for RectangularPrism.

   **D. UI (js).** Multi-line info panel, and `mergeCSGTreePayload` actually rendering.
   Two-way binding: click a tree node -> `requestCSGByPath` -> highlight; pick in 3D ->
   reveal and select the node.

   A-C are testable python; D is JS with no harness beyond jest on pure modules. Doing
   A-C first gives a clean stopping point either way.

   **Open decisions.** (i) Whether the CSG tree gets its own pane or joins the layers
   panel. The panel's hierarchy machinery exists but is organised around members and
   joints; a per-timber CSG tree is a different axis with a different lifetime (it follows
   selection, not the frame). Leaning: own pane. (ii) Whether derived edges appear in the
   tree. They are not declared on any node -- they are computed per query from face pairs
   -- so listing them per node would misrepresent them as belonging to one. Leaning: omit
   from the tree, show in the selection info line, revisit if that turns out to be what
   needs debugging.
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

## Implementation notes (steps 1-5)

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


### Feature epsilons, and collapsing EPSILON_FLOAT

**One tolerance constant.** `rule.py` had two: `EPSILON_FLOAT` (1e-10) behind the `safe_*`
comparisons and `EPSILON_GENERIC` (1e-8) behind `Matrix.equals` and `sqrt`'s
small-negative guard. Two thresholds a hundred times apart with no rule for which applied
where is a trap, so `EPSILON_FLOAT` is gone and `EPSILON_GENERIC` is the single fallback.
The whole suite passes at the looser value.

**`FeatureTestTolerances` (face / edge / point).** Replaces the `eps` + `snap_eps` pair on
`get_all_features` / `find_feature`. Type is the better key than realness: a *real* derived
edge is exactly as unclickable as a non-real centre axis, so the wider tolerance should
follow the kind of geometry, not whether the CSG tree could have cut it. `real` still
governs the boundary gate and the priority ordering; it no longer governs tolerance.

Defaults are picking-shaped -- 0.5mm / 2mm / 4mm -- because picking is what feature
queries exist for: a raycast hit lands on a vertex of the triangulated mesh, not on the
analytic surface, and at `EPSILON_GENERIC` almost none would register.
They are called *test tolerances*, not epsilons, deliberately: an epsilon absorbs float
error and `EPSILON_GENERIC` is sized for that, while these absorb the gap between meshed
and analytic geometry plus however far a click lands from a target it cannot hit exactly.
Several orders of magnitude apart, and chosen rather than derived. The parameter on
`get_all_features` / `find_feature` is `test_tolerances` and the one on
`CSGFeature.test_point` is `test_tolerance`, so the distinction is visible at the call
site; the lower-level point tests keep a plain `eps`.

`FeatureTestTolerances.exact()` gives the analytic tolerance for code that wants it, and
`.uniform(eps)` one value for all three. `*` and `/` scale all three at once, because how
much slack a snap needs is a screen-space question: a viewport holds one struct describing
the tolerances at a reference zoom and scales it by world-units-per-pixel per query. A
non-positive factor raises rather than producing a silently nonsensical tolerance. The boundary gate inside `get_all_features` uses
`face`, being a surface question whatever kinds of feature hang off it.

**A bug the looser default exposed.** The AST rewrite that threaded `eps` through the query
closure also threaded it into seven *degeneracy* guards -- `safe_zero_test(edge_length_sq)`
in the extrusion, loft and `LineSegment.closest_point`. Those compare a SQUARED length, so
a pick tolerance of 5e-4 declared any edge shorter than ~22mm to be zero-length, and real
faces of small parts silently stopped resolving. Whether an edge is degenerate is a
property of the shape, not of how close the caller clicked, so those guards now take the
default tolerance and never the query's. Regression test added with a deliberately tiny
(20mm) profile.

That is the second bug of exactly this shape -- squared quantity, linear tolerance -- after
`_squared_eps` earlier.

**`safe_zero_test_sq()` closes the class of bug.** `rule.py` now has a helper that takes a
LINEAR tolerance for a SQUARED value and squares it internally, so `eps` means a distance
in model units at every call site. All 23 squared-quantity tests across `cutcsg`,
`pathcsg` and the joint library go through it, and `_squared_eps` -- which required
remembering to wrap, and was silently wrong if you forgot -- is deleted.

Its default is `EPSILON_GENERIC` treated as a linear distance, which is 10,000x tighter
than the old `safe_zero_test(v_sq)` default it replaces (that compared a squared value
against a linear 1e-8, i.e. an effective 1e-4 distance). The suite passes at the stricter
value, so nothing was relying on the looser one. It also makes degeneracy mean what it
says: only a genuinely zero-length edge is degenerate, not one under 0.1mm.


### Step 5 -- derived edges

Built as planned, with one correction found while testing.

**Two gathers, not one gather plus refinement.** The first cut derived edges straight from
a wide gather, which let the *widest* tolerance in play set the edge snap -- a 2mm edge
tolerance snapped from 3mm because a 4mm point tolerance had set the gather width. The
first fix refined before pairing, which was correct but leaned on `test_point` being
monotonic in its tolerance. The version that shipped drops that: `collect_hits` takes the
whole tolerance struct and tests each feature at its own type's tolerance directly, and
`get_all_features` simply gathers a second time at the edge tolerance for the faces it
pairs. No invariant, no refinement stage. See D3.

That also collapsed the structure. `collect_hits` is the only recursive method; the three
compound overrides are five or six lines of gathering each and override nothing else;
`get_all_features` is a short non-recursive gather-derive-sort. Deduplication went away
with it -- and was a latent bug, since it would have collapsed two genuinely different
edges that happened to share a name.

**Pieces.** `intersect_planes` / `planes_are_parallel` in `geometry.py`;
`DerivedEdgeFeature` with a `derive()` factory carrying the group, face-type, and
parallel checks; `collect_face_hits` recursing the subtree on every compound node;
`derive_edge_hits` pairing what it returns; `_finalize_feature_hits` deduplicating and
ordering. `FeatureHit` is now `OwnedFeatureHit` and forwards `locate` / `get_extent`, since
a derived edge holds two of them.

**Ordering** is now `(real, specificity, priority)`, where specificity is POINT < EDGE <
FACE. A point sits on an edge sits on a face, so the narrowest claimant is the better
answer, and an edge beats the two faces that formed it.

**Deduplication is by name, and only for derived edges.** Every compound node derives over
its own subtree, so a nested one reports edges its parent reports again; deterministic
naming makes collapsing them exact. Authored features are deliberately not deduplicated --
two tenons on one timber legitimately both declare `tenon_right`, and those are two faces,
not one seen twice.

**PTW and rough faces moved B1 -> B2** so a timber's own arrises derive. Verified on a real
mortise-and-tenon: clicking the rough.right/rough.front arris returns
`rough.front×rough.right` located exactly on the arris, and the snap boundary tracks the
edge tolerance as it is varied.

**Reaches the viewer already.** Because derivation lives on the base class, a leaf
primitive derives its own arrises -- and `_detect_face_label` queries exactly that, the
leaf `_navigate_csg_to_leaf` reached. Clicking an arris on a real mortise-and-tenon returns
`rough.front x rough.right` through the existing runner path, with no kigumi change.

What a leaf query does NOT see is an edge between features on *different* primitives -- a
tenon cheek meeting the timber body -- since those need a node that can see both. Surfacing
those means having the picking path query the root as well, which is step 6/8 work.

**A pre-existing gap this exposed.** `SolidUnion` gathered its children's hits without
re-gating on its own boundary, unlike `Difference` and `Intersection`. A small member's
face buried inside a larger one was therefore reported as if it were surface -- and once
edges arrived, derived a spurious arris there too. Fixed by applying
`_drop_real_hits_off_boundary` in `SolidUnion.collect_hits` as well, which
`is_point_on_boundary` already supports (it rejects points strictly inside a sibling).

**Known weakness: a derived edge's extent.** `get_extent` returns only an anchor, and that
anchor is the point on the infinite line closest to the origin -- which is not necessarily
anywhere near the piece of edge that actually exists. `ends` is None. Fine for picking,
which only needs `test_point`, but step 8 will need the real endpoints, which means
cropping the line to the solid (`crop_line_to_csg`) at a level that knows the enclosing
timber.

**Deferred.** Caching derived edges instead of re-deriving per query (belongs in a separate
field from `_features`, which is authored rather than derived); edge x edge -> point;
coincident faces as a coplanarity relation, which is D9's reference work.


### Follow-ups noticed while in there

- ~~**`CutTimber.joints` is dead.**~~ **FIXED.** Both `CutTimber.from_joints` and
  `Frame.from_joints` now populate it, deduplicated by joint (a joint can hold more than
  one cutting for the same timber) and in joint order.
- ~~**`Frame.source_joints` is `Optional`.**~~ **MOOT.** Fixing the above removed the
  dependency: `_joint_by_cutting_id` reads `CutTimber.joints`, so attribution is local to
  the timber being picked and no frame is threaded through. A `CutTimber` built by hand
  still declines rather than guessing, which is the honest answer -- built by hand, there
  is no joint to name.

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
