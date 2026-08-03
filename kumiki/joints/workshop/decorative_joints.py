"""
Kumiki - Decorative joint construction functions
"""


def cut_practice_roundover_decoration(timber: TimberLike, edges: List[TimberEdge], radius: Number)
    """
    Cuts a roundover of radius `radius` along edges of timber.
    Short edges (edges on the timber ends) are at the declared length of the timber rather than the maybe_end_cut length (which is not known here).
    Note, this does not check if round radii overlap.

    """

    # for each edge, find the adjacent face normal axis and check that the length in those axis are at least radius

    # create a helper function for making a roundover cut along an edge
    # to make a roundover cut, pick one end of the edge (where it reaches the actual timber dimension)
    # go inwards by radius at 45 degrees and create a cylinder that reaches to the other end
    # then create a rectangular prism from the edge corner ot the radius point that reaches to the other end, except this time edge corner should be actual dimension corner so that imperfect parts of the timber are removed
    # difference the cylinder from the prism to get our negative CSG

    # call the helper on all edges and return the decorative joint