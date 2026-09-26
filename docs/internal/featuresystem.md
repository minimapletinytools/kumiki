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

TODO markdown table node name | node type (primitive/composite) | has curves | feature support (full or partial) | TODO figure out the rest of the collumns

## The CSG Feature System

Each CSG leaf node declares a set of `default_features` and instances may also add their own "named features" which name default features or add entirely new features. The default feature set represents all the normal features of that primitive.


### derived features

Flat face and straight edge features can be assigned a "FeatureGroup" which determines which features in a CutTimber can combine to produce derived features. That is, 2 faces producing an edge, or a face and an edge producing a point.

Note that the feature derivation system currently does NOT support the following:

- derived point features produced from 2 edges
- derived features produced from curved features
- derived features produced from derived features


## Limitations

TODO document limitations of the system right now, e.g. limited support for curved surfaces, edge geomeetry information etc.

# The Measurement/Drawing System 

TODO
