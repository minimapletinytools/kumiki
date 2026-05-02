
# Coordinate System
Kumiki uses a right-hand coordinate system.

- XY is the "ground" and Z is "up" 

- +X/-x is also "right"/"left"
- +Y/-Y is also "forward"/"back"
- +Z/-Z is also "up"/"down" or "top"/"bottom"


# Features
We will refer to the following geometric concepts and their corresponding physical features

- Point / Vertex
- Line / Edge
- Plane / Face

Since faces live on solid objects, they are "sided" objects:

- we say 2 faces are *oriented* if they share the same normal, and *opposite* if their normals are opposites

# Timber

A *Timber* is one of the fundamental building blocks of your structure and the majority of Kumiki is designed around this class.

```
class Timber:
    length : float
    size : V2
    bottom_position : V3
    length_direction : TimberFace
    width_direction : TimberFace
```


## timber position and orientation

Timbers are referenced in their own local coordinate system.

The *bottom point* of a timber is on the bottom face of the timber and in the center of its cross section. The bottom point is located at the origin of the timber's local coordinate system.

The *centerline* of the timber is the line that runs from bottom to top.

By default, a timber is oriented with its bottom cross section centered on the XY plane and running up in the Y direction. We use the following names for each axis

- Z axis: *length axis* of the timber
- X axis: *width axis* of the timber
- Y axis: *height axis* of the timber

To orient the timber we position, we often position the +Z and +X axis of the timber.

- A timber is *axis aligned* if its length vector is parallel to the +Z axis and its face vectors are parallel to either the X or Y axis.
- Timbers are *face aligned* if each of the 6 faces of one timber is parallel with one of the 6 faces of the other timbers. 
- Timbers are *plane aligned* if 2 of the 4 long faces on one timber are parallel to 2 of 4 long faces on the other timbers. These faces are parallel to the *parallel face plane*.

We often do not care to distinguish between 2 opposing faces on a timber thus:

- the *width-sides* of a timber are the 2 faces perpendicular to its local X axis
- the *height-sides* of a timber are the 2 faces perpendicular to its local Y axis
- the *ends* of a timber are the 2 faces perpendicular to its local Z axis

When we do care about referencing a specific face, we may do so relative to its local coordinate system. We may refer to each face with the following names:

```
class TimberFace(Enum):
    TOP = 1 # the face vector with normal vector in the +Z axis direction
    BOTTOM = 2 # the face vector with normal vector in the -Z axis direction
    RIGHT = 3 # the face vector with normal vector in the +X axis direction
    FRONT = 4 # the face vector with normal vector in the +Y axis direction
    LEFT = 5 # the face vector with normal vector in the -X axis direction
    BACK = 6 # the face vector with normal vector in the -Y axis direction
```

### measuring and marking

Joint functions take measurents for its features relative to one of the features on one of the timbers in the joint arrangement. Often you may want to position the joint feature relative to some other featuer perhaps on a different timber. Functions in `measuring.py` are designed to help you do this. TLDR; you `locate` a  feature you want to mesaure from, and then you `mark` that feature onto the feature that the joint function needs. If you don't understand what I mean by this no worries, because the AI does understand :|.

## member names

When timbers are part of a structure, they may be referred to as members. Members have no logical distinction from each other as far as Kumiki is concerned, but the concepts are useful for explaining the intended use of various functions and you may also want to use these names to organize your projects. It is also useful to describe them as such as the AI will understand things like "beams" being horizontal members. The remainder of this doc will assume knowledge of various member names to elaborate certain concepts.


# Footprint

A support class representing the footprint of the structure in the XY plane to help position and orient timbers. Footprints are always defined at Z=0 and timbers defined on the footprint are always have their bottom surface at Z=0 in global space.


```
class Footprint:
    # a list of points defining the corners of the footprint, the last point is connected to the first point
    corners : list[V2]
```

## inside, outside, sides and corners

Footprints consist of a set of boundary corners that form a non intersecting boundary consisting of boundary sides. This boundary defines an inside and outside to the boundary which are used to position timbers around the boundary. 


```
class FootprintLocation(Enum):
    INSIDE = 1
    CENTER = 2
    OUTSIDE = 3
```

Timbers are positioned either on boundary sides or boundary corners. They can either be positioned "inside", "outside", "on center". Each boundary corner and boundary side also have a notion of inside and outside. 

- For boundary sides, the inside side is simply the side of the boundary side that is towards the inside of the boundary and the outside the opposite.
- For boundary corners it is a little more complicated because we want to orient vertices of posts around the inside/outside of the boundary corner. This is elaborated in the "From a Footprint" section of "Creating Timbers"

# Creating Timbers

## Out of Nowhere

You can use methods like `create_timber` and  `create_axis_aligned_timber` to create timbers in arbitrary places in space. In most cases it is better not to create timbers "out of nowhere"

## From a Footprint

When starting your structure, it's often best to create timbers from a footprint. This defines the boundary and foundation of your structure. This approach is also appropriate for smaller things like furnture and so on. Mudsills and Posts can be created on the *inside*, *outside* and *center* of a footprint.


### mudsills go on boundary sides

use `create_horizontal_timber_on_footprint` to create "mudsills" on your footprint.

- A mudsill on a boundary side of a footprint will have its length run from one boundary corner to the other boundary corner of the boundary side.
- A mudsill on the inside/outside of a boundary side will have an edge lying on the boundary side with the mudsill on the inside/outside side of the boundary side.
- A mudsill on center of a boundary side will have its midline lying on the same plane 

### posts go on points on boundary sides

- use `create_vertical_timber_on_footprint_side` to create "posts" on the sides of your footprint.

- A post can be positioned on a point along a boundary side. 
- If the post is on center, it will have its center of the bottom face lying on the point, and 2 of the edges of the bottom face will be parallel to the boundary side.
- If the post is inside/outside, it will have one edge of the bottom face lying on the boundary side with the center of that edge coincident with the point, with the rest of the post inside/outside of the boundary side.

### posts go on boundary corners

use `create_vertical_timber_on_footprint_corner` to create "posts" on the corners of your footprint

- A post can be positioned on the inside/outside of a boundary corner IF the boundary corner is orthogonal, i.e. the two boundary sides coming out of the boundary corner are perpendicular.
- If it is on the inside of the boundary corner, position the post such that it overlaps with the inside of the boundary, has one vertex of its bottom face lying on the boundary corner, and has 2 edges of its bottom face aligning with the 2 boundary sides coming out of the boundary corner. 
- If it is on the outside of the boundary corner, then position the post first on the inside of the boundary corner, and take the vertex of its bottom face that is opposite to the vertex lying on the boundary corner and move it so that the opposite vertex is instead on the boundary corner.


## Joining Timbers
 
Use joint timber methods to two timbers with a spanning timber (for example, adding a joist between 2 posts).

If you want to maintain face alignment, use `join_face_aligned_on_face_aligned_timbers` which will ensure all created timbers are joined. The joining timber will be perpendicular and face aligned with the input timbers or it will error if not possible.

Otherwise, use `join_timbers` which will create a new timber connecting the centerlines of the input timbers.

## Extending or Splitting Timbers

- Use split_timber to split a timber in two. The input timber should be discarded. This is useful for splitting long timbers for splice joints.
- Use stretch_timber to an extend a timber. The input timber should be discarded.

# Joints 

Once your timbers have been created, it's time to cut them to make joints.

TODO


