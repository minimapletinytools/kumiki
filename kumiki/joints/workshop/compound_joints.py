"""
Kumiki - Compound joint construction functions
Contains functions for creating complex joints that combine multiple joint types.
"""

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .shavings import *


# chatGPT translates this to Japanese as:
# 小根付き通しほぞの十字相欠き梁組
# kone-tsuki tōshi-hozo no jūji aigaki harigumi
def cut_cross_lap_beam_assembly_on_post_with_stepped_mortise_and_tenon(
        # arrangement.cross_timber_1 is always assumed to be the "bottom" in the cross lap joint
        arrangement: CrossCapJointTimberArrangement,

        # the size of the tenon as it passes through cross_timber_1 measured relative to post_timber
        tenon_size_in_cross_timber_1: V2,
        # the size of the tenon as it passes through cross_timber_2 measured relative to post_timber, must be smaller than tenon_size_in_cross_timber_1
        tenon_size_in_cross_timber_2: V2,

        # length of the tenon, stops exactly at the face of cross_timber_2 if None
        tenon_length: Optional[Numeric] = None,
        # depth of the mortise through both cross timbers mesaured from the face of cross_timber_1, through mortise if None
        mortise_depth: Optional[Numeric] = None,

        # location of the cross lap cut measured from the bottom of cross_timber_2, 0 means the cut is at the bottom of cross_timber_2 (relative to the joint)
        cross_lap_cut_ratio: Numeric = scalar(1, 2),
        ):
    raise NotImplementedError("cross lap beam assembly on post with stepped mortise and tenon not implemented yet")
