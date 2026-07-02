"""
Kumiki - Free joint construction functions
Contains functions for creating joints with flexible geometry matching.
"""

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .shavings import *


def cut_free_house_joint(housing_timber: TimberLike, housed_timber: Union[TimberLike, CutTimber]) -> Joint:
    """
    Creates a generic house joint where the housing timber is cut to receive the housed timber.
    The housed_timber can be a CutTimber which houses the CutTimber's geometry.

    Args:
        housing_timber: Timber that will be cut to house the housed timber
        housed_timber: Timber that will be housed
    """
    import warnings
    from kumiki.cutcsg import adopt_csg, Difference, SolidUnion

    # if housed_timber is not perfect, output a warning indicating that cuts will be dependent on imperfect size
    # TODO flag joints or even CSG features (using tickets) that have cuts measured from imperfect features!!
    underlying = housed_timber.timber if isinstance(housed_timber, CutTimber) else housed_timber
    if not underlying.is_perfect_timber():
        warnings.warn(
            f"cut_free_house_joint: housed_timber (type {type(underlying).__name__}) is not a perfect "
            f"timber. The housing cut is based on its actual geometry and may produce unexpected results.",
            stacklevel=2,
        )

    if isinstance(housed_timber, CutTimber):
        # if housed_timber is a CutTimber
        # The volume to remove from the housing_timber is the CutTimber's actual body shape:
        #   housed_prism - (cuts on the housed_timber that intersect the housing_timber)
        # This correctly models the notch matching the housed piece including any mortises in it.

        # Housed timber's actual prism in housing_timber's local space
        housed_prism_in_housing = adopt_csg(
            housed_timber.timber.transform,
            housing_timber.transform,
            housed_timber.timber.get_actual_csg_local(),
        )

        # AABB of the housed_timber's prism in housing_timber's local space (used for pruning below)
        housed_aabb = housed_prism_in_housing.get_aabb()

        # Housing_timber cross-section half-extents (in its own local space).
        half_w = housing_timber.size[0] / scalar(2)
        half_h = housing_timber.size[1] / scalar(2)

        def _take_max(a: Numeric, b: Numeric) -> Numeric:
            return a if safe_compare(a, b, Comparison.GE) else b

        def _take_min(a: Numeric, b: Numeric) -> Numeric:
            return a if safe_compare(a, b, Comparison.LE) else b

        # TODO TEST THIS, add some examples to test this
        def _is_outside_housing_cross_section(csg_in_housing_local: CutCSG) -> bool:
            # find the four long face planes of the AABB of the housing_timber
            # check whether CutTimber's CSG geometry lives entirely on the external side of the 4 planes
            # specifically, for each CSG leaf feature in the CutTimber's negative_csg, see if that feature
            # INTERSECTED with the housed_timbers actual AABB is entirely contained in the external side of the plane
            # if this is the case, that means that CSG feature does not actually affect the housed timber
            # and can be removed from the tree
            aabb = csg_in_housing_local.get_aabb()
            # Unbounded (e.g. HalfSpace) → conservatively keep
            if any(v is None for v in (aabb.min_x, aabb.max_x, aabb.min_y, aabb.max_y)):
                return False
            # After the check above all four x/y bounds are non-None
            assert aabb.min_x is not None and aabb.max_x is not None
            assert aabb.min_y is not None and aabb.max_y is not None
            # Clip the leaf's AABB to the housed_timber's AABB
            cx_min: Numeric = _take_max(aabb.min_x, housed_aabb.min_x) if housed_aabb.min_x is not None else aabb.min_x
            cx_max: Numeric = _take_min(aabb.max_x, housed_aabb.max_x) if housed_aabb.max_x is not None else aabb.max_x
            cy_min: Numeric = _take_max(aabb.min_y, housed_aabb.min_y) if housed_aabb.min_y is not None else aabb.min_y
            cy_max: Numeric = _take_min(aabb.max_y, housed_aabb.max_y) if housed_aabb.max_y is not None else aabb.max_y
            # If the clip is empty, the feature does not overlap with the housed_timber at all
            if safe_compare(cx_min, cx_max, Comparison.GT) or safe_compare(cy_min, cy_max, Comparison.GT):
                return True
            # Check if the clipped AABB is entirely beyond one of the four housing_timber long-face planes
            return (
                safe_compare(cx_min, half_w, Comparison.GT)     # right of right face
                or safe_compare(cx_max, -half_w, Comparison.LT) # left of left face
                or safe_compare(cy_min, half_h, Comparison.GT)  # above front face
                or safe_compare(cy_max, -half_h, Comparison.LT) # below back face
            )

        def _prune_csg(csg: CutCSG) -> Optional[CutCSG]:
            # generated the pruned CSG tree of the housed_timber as the negative_csg for the housing timber's cut
            # Recurse into SolidUnion to prune children individually; treat all other nodes atomically.
            if isinstance(csg, SolidUnion):
                kept = []
                for child in csg.children:
                    pruned = _prune_csg(child)
                    if pruned is not None:
                        kept.append(pruned)
                if not kept:
                    return None
                return kept[0] if len(kept) == 1 else SolidUnion(children=kept, label=csg.label)
            return None if _is_outside_housing_cross_section(csg) else csg

        # Collect and prune each cut's negative CSG, transformed to housing_timber's local space
        relevant_cuts = []
        for cut in housed_timber.cuts:
            neg_in_housing = adopt_csg(
                housed_timber.timber.transform,
                housing_timber.transform,
                cut.get_negative_csg_local(),
            )
            pruned = _prune_csg(neg_in_housing)
            if pruned is not None:
                relevant_cuts.append(pruned)

        # negative_csg = housed_prism minus the relevant cuts = the actual body of the housed_timber
        negative_csg = Difference(housed_prism_in_housing, relevant_cuts) if relevant_cuts else housed_prism_in_housing
        cut_housing = Cutting(timber=housing_timber, negative_csg=negative_csg)
        cut_housed = Cutting(timber=housed_timber.timber)

    else:
        # if housed_timber is a TimberLike, use its actual CSG as the negative_csg for the housing timber's cut
        negative_csg = adopt_csg(
            housed_timber.transform,
            housing_timber.transform,
            housed_timber.get_actual_csg_local(),
        )
        cut_housing = Cutting(timber=housing_timber, negative_csg=negative_csg)
        cut_housed = Cutting(timber=housed_timber)

    return Joint(
        cuttings={"housing_timber": cut_housing, "housed_timber": cut_housed},
        ticket=JointTicket(joint_type="free_house"),
        jointAccessories={},
    )
