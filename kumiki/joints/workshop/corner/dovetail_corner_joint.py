"""
Kumiki - Dovetail corner joint construction function
"""

from __future__ import annotations

from typing import List, Optional

from kumiki.construction import CornerJointTimberArrangement
from kumiki.rule import Numeric
from kumiki.timber import Joint


#TODO freeze me
class SingleDovetailSizeParameter:
    """       
        ______
    ____\\   /_______ }depth
          ^ small_width
    """
    angle: Numeric # 0 is perpendicular
    small_width: Numeric
    depth: Optional[Numeric] # set to none for dovetails to go all the way through, set to less than that for half blind dovetails. Full blind dovetails are done with another joint


# dovetail measurement starts from front_face_on_timber1
# distances are measured from the CENTERs of the dovetails, starting from front_face_on_timber1 and then from the center of one dovetail to the next
# dovetails positives are cut into timber1, negatives are cut into timber2
def cut_dovetail_corner_joint(arrangement: CornerJointTimberArrangement, distances: List[Numeric], dovetails: List[SingleDovetailSizeParameter]) -> Joint:
    # assert orthogonal
    # determine the face in timber2 that dovetails enter in
    # assert all depth is <= the dimension of timber2 in the face axis computed above
    # create a new list of tuples of dovetail parameters with non optional depth

    # determine the outside face on timber1 and front_face_on_timber1 to determine the starting measuring space 
    # for each dovetail
    # advance by distances[i] from the previosu dovetail
    # draw the dovetail profile (see the dropin dovetail joint in butt joints, try and extract the dovetail drawing method into a shared funciton if appropriate but it's so simple so mayb enot worth bothering to do)
    # extrude, take a prism around it to get the positives for timber 1 cut directly into timbre2 for the negative
    #

    # set the maybe end cuts (matches plain miter joint end cuts) 
    # note that techincally timber1 could have a shorter maybe end cut if all the tenons are half blind but we don't bother with that. please preserve this comment
    raise NotImplementedError("This function is not implemented yet.")
