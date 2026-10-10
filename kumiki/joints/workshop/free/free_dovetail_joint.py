"""
Kumiki - Free joint construction functions
Contains functions for creating joints with flexible geometry matching.
"""

from dataclasses import dataclass
from typing import Optional

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from ..shavings import *


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
    # None means infinite
    forward_length: Optional[Numeric] = None
    backward_length: Optional[Numeric] = None
    taper_angle: Numeric = scalar(0)

    def __post_init__(self):
        assert safe_compare(self.width, 0, Comparison.GT), "a dovetail needs a positive width"
        assert safe_compare(self.depth, 0, Comparison.GT), "a dovetail needs a positive depth"
        if not safe_zero_test(self.taper_angle):
            assert self.forward_length is not None and self.backward_length is not None, \
                "a tapered dovetail needs finite forward and backward lengths"
            assert safe_compare(self._half_width_at(self.forward_length), 0, Comparison.GT) \
                and safe_compare(self._half_width_at(-self.backward_length), 0, Comparison.GT), \
                "the taper closes the dovetail to nothing within its length"

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
                                          end_distance=self.forward_length, label=CutCSGLabel("dovetail"))
        assert start is not None and self.forward_length is not None
        return ConvexPolygonSimpleLoft(bottom_points=self.profile_at(start),
                                       top_points=self.profile_at(self.forward_length),
                                       bottom_points_z_pos=start, top_points_z_pos=self.forward_length,
                                       label=CutCSGLabel("dovetail"))


def cut_free_dovetail_joint(dovetail_timber: TimberLike, receiving_timber: TimberLike,
                            dovetail: FreeDovetailShape) -> Joint:
    """A dovetail of any shape and placement: the receiving timber gets the socket, the dovetail timber the tongue.

    The dovetail timber keeps the tongue and everything on the +y side of the dovetail's wide face;
    between the dovetail's ends, everything else on the -y side of that face is cut away. That
    face is the joint's shoulder.
    """
    # create a convex polygon extrusion from `dovetail`
    dovetail_csg = dovetail.csg()

    # remove the extrusion CSG from receiving timber
    socket = adopt_csg(dovetail.origin, receiving_timber.transform, dovetail_csg)

    # create a half space coincident the +y flat face of the dovetail pointing in the -y direction
    region: CutCSG = HalfSpace(normal=create_v3(0, -1, 0), offset=-dovetail.depth,
                               feature_overrides=[shoulder_override(HALF_SPACE_PLANE, name="shoulder")],
                               label=CutCSGLabel("shoulder"))
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
