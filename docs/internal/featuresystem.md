# Introduction
This doc describes the kumiki geometry feature system.

kumiki implements its own CSG (constructive solid geometry) system to generate all timber and joint geometry. 

# Files

- cutcsg.py: the main csg classes live here
- pathcsg.py: adds PathExtrusion csg class
- geometry.py: contains shared geometry feature classes like Plane Line Vertex etc
- drawing.py: contains all code relate to generating measurements from CSG features

# Overview

## How kumiki CSGs are created 

`Timber`s produce a `RectangularPrism` CSG representing its volume. It actually produces 2 CSGs, one for its rough volume and one for its "perfect timber within" (PTW). Note that its ends may be extended to infinity if any Joint on it declares itself to be an end joint.

`Joint`s on a timber produce a `negative_csg` that is cut of the timber's prism to produce the joint.

Since a timber may contain many joints, `Joint`s are assembled into `CutTimber`s which combine all joints on a timber. The final CSG is the timber's CSG with each joint's `negative_csg` removed from it. 
Again, whether either of the timber's ends are extended to infinity depend if any of the joint's are "end joints" on that end. Whether the PTW or rough prism is used depends on what the renderer wants. Note that the same `negative_csg` is used for both PTW and rough timber prisms, thus all joints must declare their `negative_csg` as if they were cutting out of the rough timber always.

## How CSGs are rendered

`triangles.py` contains logic to convert CSGs into meshes. The raw geometry is passed as a blob and rendered kigumi or written to stl `blueprint.py`. `blueprint.py` also contains logic to directly render the CSG into a step file.

# The CSG System

The CSG system declares is hierarchical, with various primitives as its leaf nodes and a handful of compositing nodes. Which nodes and their features/limitations are documented in a table below

## Capabilities

The CSG feature tree can answer the following questions

TODO  document limitations of each of these functions

- contains_point: answers whether a point is contained in the CSG
- is_point_on_boundary: answers whether a point is on the boundary of the CSG
- get_outward_normal: returns the outward normal of a boundary point on the CSG


## The CSG Nodes

| Node Name | Node Type (primitive/composite) | contains_curves | File | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `EmptyCSG` | Primitive | No | `cutcsg.py` | Empty solid containing no points; returns `False` for point containment/boundary tests and yields an empty AABB. |
| `HalfSpace` | Primitive | No | `cutcsg.py` | Infinite half-space defined by a normal vector and signed offset (`P · normal >= offset`). Boundary is a single unbounded planar face. |
| `RectangularPrism` | Primitive | No | `cutcsg.py` | Box primitive with rectangular cross-section `(width, height)` along local Z; can be finite or semi-infinite/infinite on either end. Declares planar face, arris (edge), and corner vertex features. |
| `Cylinder` | Primitive | Yes | `cutcsg.py` | Extrusion with circular cross-section defined by axis, radius, and optional infinite ends. Lateral surface is a curved face (`CURVED_FACE`); end caps are planar. Also declares an internal axis feature (`LINE`, non-real). |
| `ConvexPolygonExtrusion` | Primitive | No | `cutcsg.py` | Extrusion of a 2D convex polygon along local Z with optional infinite ends. All side faces and end caps are planar. |
| `ConvexPolygonSimpleLoft` | Primitive | No | `cutcsg.py` | Straight-line loft between two 2D convex polygons in parallel planes. Requires planar non-twisted side faces (`_sides_are_planar`) and finite length; no curved surfaces. |
| `PathExtrusion` | Primitive | Yes (if path has `ArcSegment`s) | `pathcsg.py` | Extrusion of a closed 2D `FancyPath` along local Z. Supports non-convex profiles; straight segments yield planar faces (`FlatSide`), while arc segments yield curved lateral surfaces (`CurvedSide`, `CURVED_FACE`). |
| `SolidUnion` | Composite | Dependent on children | `cutcsg.py` | Boolean union combining multiple child nodes. Point is in union if inside any child; cancels internal boundary faces where children meet. |
| `Intersection` | Composite | Dependent on children | `cutcsg.py` | Boolean intersection of two child nodes (`left` and `right`). Point is inside if contained in both children. |
| `Difference` | Composite | Dependent on children | `cutcsg.py` | Boolean difference subtracting a list of `subtract` child nodes from a `base` node (`base - subtract[0] - subtract[1] ...`). Outward normals along cut cavities are inverted. | 

## The CSG Feature System

Each CSG leaf node declares a set of `default_features`: every face, arris and corner of that primitive, each at a `FeatureKey` (a `FeatureCategory` and an index, printed as `side.0`, `arris.5`, `cap.1`) and named after that key until someone names it otherwise.

An instance adds to these in two separate ways:

- `feature_overrides`: `FeatureOverride(key, name, properties)` renames a default and/or replaces its `FeatureProperties` (everything in `FeatureProperties`, including `real`, can change). It carries no geometry, so an override can never move or reshape what it names. Keys come from helpers: `prism_face_key`, `prism_arris_key`, `prism_corner_key`, `side_key`, `START_CAP` / `END_CAP`, `HALF_SPACE_PLANE`, `CYLINDER_BARREL`.
- `extra_features`: features with geometry of their own that no default names, e.g. `CylinderAxisFeature` or a `ProgrammableEdgeFeature`. An extra must not report a `FeatureKey`; one that does is naming a default and belongs in `feature_overrides`.

Both are checked when the primitive is constructed. Overriding a key the primitive doesn't have, overriding a key twice, a keyed extra, or two features with the same name raise `ValueError`. `PathExtrusion` has no defaults yet, so its named sides are extras.

Features themselves are bounded geometric primitives

```
class CSGFeatureType(Enum):
    FACE = 1
    EDGE = 2
    POINT = 3
    CURVED_FACE = 4
```

and represented in the `CSGFeature` class. However the `CSGFeature` may not have all the required information to know the feature geometry so many of its methods require passing in the owning CSG object.

Declared features on a CSG can be queried at a point using `collect_feature_hits` and `find_all_features` will also return derived features (see below)

### derived features

Flat face and straight edge features can be assigned a "FeatureGroup" which determines which features in a CutTimber can combine to produce derived features. That is, 2 faces producing an edge, or a face and an edge producing a point.

Note that the feature derivation system currently does NOT support the following:

- derived point features produced from 2 edges
- derived features produced from curved features
- derived features produced from derived features


## Interacting with the CSG System 

### selecting features (technically a kigumi thing)


#### feature priority

TODO fetaure hit priority system here


## Limitations

The CSG system has the following limitations

- boundary point comuptations may break in certain cases, in particular if we have `Difference` B C being removed from A, and B and C share a point on faces with opposite normals, and that point is contained in A, that point will be reported as on the boundary of the final difference when it should not be. (this should be fixable)
- an edge cut in half by a another CSG is still reported as a single edge feature spanning the gap. e.g. ---☐--- It is still able to compute its segments for rendering the edge though.
- curved surfaces do not form derived features
- edge edge intersections to not form derived features

# The Measurement/Drawing System 

TODO
