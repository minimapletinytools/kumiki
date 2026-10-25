"""
Kumiki - Free joint construction functions
Contains functions for creating joints with flexible geometry matching.
"""

from dataclasses import dataclass, replace
from typing import Optional

from kumiki.timber import *
from kumiki.timber import _get_rough_size_and_offset
from kumiki.construction import *
from kumiki.rule import *
from kumiki.csg.cutcsg import (
    END_CAP, START_CAP, FeatureCategory, FeatureGroup, FeatureOverride, FeatureProperties, arris_against_cap,
    side_key,
)
from ..shavings import *


#: The dovetail's faces, by profile edge (see profile_at) and end. CROSSING, like a cross lap's: they
#: meet both timbers' bodies, so the socket's and the tongue's outlines are edges to measure to.
_DOVETAIL_FEATURE = FeatureProperties(group=FeatureGroup.CROSSING)
_SIDE_NAMES = ("dovetail_neck", "dovetail_right_flank", "dovetail_wide_face", "dovetail_left_flank")
_END_NAMES = ("dovetail_backward_end", "dovetail_forward_end")
_DOVETAIL_FACES = [
    *(FeatureOverride(side_key(side), name, _DOVETAIL_FEATURE) for side, name in enumerate(_SIDE_NAMES)),
    FeatureOverride(START_CAP, _END_NAMES[0], _DOVETAIL_FEATURE),
    FeatureOverride(END_CAP, _END_NAMES[1], _DOVETAIL_FEATURE),
]
#: Its edges, named by the two faces they join: along its length between neighbouring sides,
#: and round each end. CROSSING too, so where one leaves a timber's face is a point to measure to.
_DOVETAIL_EDGES = [
    override
    for side, name in enumerate(_SIDE_NAMES)
    for override in (
        FeatureOverride((FeatureCategory.ARRIS, side), f"{name}×{_SIDE_NAMES[(side + 1) % 4]}", _DOVETAIL_FEATURE),
        FeatureOverride(arris_against_cap(side, 4, end=False), f"{name}×{_END_NAMES[0]}", _DOVETAIL_FEATURE),
        FeatureOverride(arris_against_cap(side, 4, end=True), f"{name}×{_END_NAMES[1]}", _DOVETAIL_FEATURE),
    )
]
_DOVETAIL_FEATURES = [*_DOVETAIL_FACES, *_DOVETAIL_EDGES]


_END_CLEARANCE = mm(5)


def _rough_box_corners(timber: TimberLike) -> List[V3]:
    """The eight corners of `timber`'s rough box over its length, in world space."""
    size, offset = _get_rough_size_and_offset(timber)
    return [timber.transform.local_to_global(create_v3(offset[0] + sx * size[0] / 2, offset[1] + sy * size[1] / 2, z))
            for sx in (-1, 1) for sy in (-1, 1) for z in (scalar(0), timber.length)]


#.    _______
#.    \_____/ <- angle.  }depth
#        ^
#        origin
#.    |-----| small width

@dataclass(frozen=True)
class FreeDovetailShape:
    # origin in world space
    # the +z direction is the forward extrusion direction of the dovetail shape
    # the "width" of the dovetail is measured in the x axis at the origin
    # the "depth" of the dovetail is measured in the +y axis, with the smaller width towards the -y side
    # a positive taper angle means it tapers towards the +z side
    origin: Transform
    width: Numeric
    depth: Numeric
    dovetail_angle: Numeric
    # None runs it through both timbers: cut_free_dovetail_joint sets it from their bounding boxes
    forward_length: Optional[Numeric] = None
    backward_length: Optional[Numeric] = None
    taper_angle: Numeric = scalar(0)

    def __post_init__(self):
        assert safe_compare(self.width, 0, Comparison.GT), "a dovetail needs a positive width"
        assert safe_compare(self.depth, 0, Comparison.GT), "a dovetail needs a positive depth"
        assert safe_compare(self.dovetail_angle, 0, Comparison.GT), \
            "a dovetail's angle must be positive: it widens away from its neck, toward +y"
        if not safe_zero_test(self.taper_angle) and self.forward_length is not None \
                and self.backward_length is not None:
            assert safe_compare(self._half_width_at(self.forward_length), 0, Comparison.GT) \
                and safe_compare(self._half_width_at(-self.backward_length), 0, Comparison.GT), \
                "the taper closes the dovetail to nothing within its length"

    def through(self, *timbers: TimberLike) -> 'FreeDovetailShape':
        """This dovetail with each open (None) end run just past `timbers`' rough bounding boxes."""
        if self.forward_length is not None and self.backward_length is not None:
            return self
        along = self.origin.orientation.matrix[:, 2]
        reach = [safe_dot_product(corner - self.origin.position, along)
                 for timber in timbers for corner in _rough_box_corners(timber)]
        # A little past the farthest corner, so an end never lands on a timber's face.
        forward = self.forward_length
        if forward is None:
            forward = max(max(reach), scalar(0)) + _END_CLEARANCE
        backward = self.backward_length
        if backward is None:
            backward = max(-min(reach), scalar(0)) + _END_CLEARANCE
        return replace(self, forward_length=forward, backward_length=backward)

    def _half_width_at(self, z: Numeric) -> Numeric:
        """Half the small width at `z` along the dovetail, narrowing toward +z by the taper."""
        return self.width / scalar(2) - z * tan(self.taper_angle)

    def profile_at(self, z: Numeric) -> List[V2]:
        """The dovetail's cross section at `z`, in its own x/y: small width at y=0, flaring to y=depth."""
        half = self._half_width_at(z)
        flare = self.depth * tan(self.dovetail_angle)
        return [create_v2(-half, scalar(0)), create_v2(half, scalar(0)),
                create_v2(half + flare, self.depth), create_v2(-half - flare, self.depth)]

    def csg(self) -> CutCSG:
        """The dovetail as a solid, in its own frame (`origin`'s local space)."""
        start = None if self.backward_length is None else -self.backward_length
        if safe_zero_test(self.taper_angle):
            return ConvexPolygonExtrusion(points=self.profile_at(scalar(0)), start_distance=start,
                                          end_distance=self.forward_length, feature_overrides=_DOVETAIL_FEATURES,
                                          label=CutCSGLabel("dovetail"))
        assert start is not None and self.forward_length is not None, \
            "a tapered dovetail needs both ends: set them, or resolve them with through()"
        return ConvexPolygonSimpleLoft(bottom_points=self.profile_at(start),
                                       top_points=self.profile_at(self.forward_length),
                                       bottom_points_z_pos=start, top_points_z_pos=self.forward_length,
                                       feature_overrides=_DOVETAIL_FEATURES, label=CutCSGLabel("dovetail"))


def cut_free_dovetail_joint(dovetail_timber: TimberLike, receiving_timber: TimberLike,
                            dovetail: FreeDovetailShape) -> Joint:
    """A dovetail of any shape and placement: the receiving timber gets the socket, the dovetail timber the tongue.

    The tongue's neck is the dovetail's narrow face, at its origin, and it widens toward its tip
    along +y -- so the dovetail timber should lie on the -y side of the dovetail shape origin, and it tapers towards +y.
    Between the dovetail's ends, everything of the dovetail timber past the narrow face in +y is cut away except the tongue. That face is the joint's shoulder.
    """
    dovetail = dovetail.through(dovetail_timber, receiving_timber)
    # create a convex polygon extrusion from `dovetail`
    dovetail_csg = dovetail.csg()

    # remove the extrusion CSG from receiving timber
    socket = adopt_csg(dovetail.origin, receiving_timber.transform, dovetail_csg)

    # create a half space coincident the narrow (-y) face of the dovetail, its neck, covering the +y side
    region: CutCSG = HalfSpace(normal=create_v3(0, 1, 0), offset=scalar(0),
                               feature_overrides=[shoulder_override(HALF_SPACE_PLANE, name="shoulder")],
                               label=CutCSGLabel("shoulder"))

    # TODO use Difference not intersection, Difference is more efficient
    # then crop that half space with the forward backward ends of the dovetail shape forming a prism
    # that's infinite in 3 directions
    if dovetail.forward_length is not None:
        region = Intersection(left=region, right=HalfSpace(
            normal=create_v3(0, 0, -1), offset=-dovetail.forward_length, label=CutCSGLabel("forward_end")))
    if dovetail.backward_length is not None:
        region = Intersection(left=region, right=HalfSpace(
            normal=create_v3(0, 0, 1), offset=-dovetail.backward_length, label=CutCSGLabel("backward_end")))

    # remove the dovetail shape from the shape above
    waste = Difference(region, [dovetail_csg], label=CutCSGLabel("tongue_waste"))

    # remove the resulting shape from the dovetail timber
    tongue_cut = adopt_csg(dovetail.origin, dovetail_timber.transform, waste)

    # return the joint
    return Joint(
        cuttings={
            "dovetail_timber": Cutting(timber=dovetail_timber, negative_csg=tongue_cut,
                                       label=CutCSGLabel("free_dovetail")),
            "receiving_timber": Cutting(timber=receiving_timber, negative_csg=socket,
                                        label=CutCSGLabel("free_dovetail")),
        },
        ticket=JointTicket(joint_type="free_dovetail"),
        jointAccessories={},
    )
