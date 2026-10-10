"""
Kumiki - Free joint construction functions
Contains functions for creating joints with flexible geometry matching.
"""

import warnings
from typing import Union, List

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from ..shavings import *


#.    _______
#.    \_____/ <- angle.  }depth 
#        ^
#        origin
#.    |-----| small width

class FreeDovetailShape():
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
    forward_length: Optional[Numeric]
    backward_length: Optional[Numeric]
    taper_angle: Numeric



def cut_free_dovetail_joint(dovetail_timber: TimberLike, receiving_timber: TimberLike, dovetail: FreeDovetailShape) -> Joint:
    # create a convex polygon extrusion from `dovetail`
    # remove the extrusion CSG from receiving timber
    # create a half space coincident the +y flat face of the dovetail pointing in the -y direction
    # then crop that half space with the forward backward ends of the dovetail shope formaing an prism that's infinite in 3 directions
    # remove the dovetail shape from the shape above
    # remove the resulting shape from the dovetail timber
    # return the joint
    pass

    