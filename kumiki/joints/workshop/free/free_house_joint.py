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


def cut_free_house_joint(
    housing_timber: TimberLike,
    housed_timbers: List[Union[TimberLike, CutTimber]],
) -> Joint:
    """
    Creates a generic house joint where the housing timber is cut to receive one or more housed timbers.
    Each housed timber may be a CutTimber, in which case the housing cut follows that CutTimber's
    actual remaining body.

    Args:
        housing_timber: Timber that will be cut to house the housed timbers
        housed_timbers: Timbers that will be housed

    Returns:
        Joint with the cut housing timber keyed "housing_timber", and each housed timber
        unmodified, keyed "housed_timber_1", "housed_timber_2", ... in input order. No
        assembly freedoms are set (the connections are treated as rigid).
    """
    assert len(housed_timbers) > 0, "housed_timbers must contain at least one timber"

    def _compute_housed_body_in_housing_local(housed_timber: Union[TimberLike, CutTimber]) -> CutCSG:
        underlying = housed_timber.timber if isinstance(housed_timber, CutTimber) else housed_timber
        if not underlying.is_perfect_timber():
            warnings.warn(
                f"cut_free_house_joint: housed_timber (type {type(underlying).__name__}) is not a perfect "
                f"timber. The housing cut is based on its actual geometry and may produce unexpected results.",
                stacklevel=2,
            )

        if isinstance(housed_timber, CutTimber):
            housed_prism_in_housing = adopt_csg(
                housed_timber.timber.transform,
                housing_timber.transform,
                housed_timber._extended_timber_without_cuts_csg_local(),
            )

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                housed_aabb = housed_prism_in_housing.get_aabb()

            half_w = housing_timber.size[0] / scalar(2)
            half_h = housing_timber.size[1] / scalar(2)

            def _take_max(a: Numeric, b: Numeric) -> Numeric:
                return a if safe_compare(a, b, Comparison.GE) else b

            def _take_min(a: Numeric, b: Numeric) -> Numeric:
                return a if safe_compare(a, b, Comparison.LE) else b

            def _is_outside_housing_cross_section(csg_in_housing_local: CutCSG) -> bool:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    aabb = csg_in_housing_local.get_aabb()
                if aabb.is_empty:
                    return True
                if any(v is None for v in (aabb.min_x, aabb.max_x, aabb.min_y, aabb.max_y)):
                    return False
                assert aabb.min_x is not None and aabb.max_x is not None
                assert aabb.min_y is not None and aabb.max_y is not None
                cx_min: Numeric = _take_max(aabb.min_x, housed_aabb.min_x) if housed_aabb.min_x is not None else aabb.min_x
                cx_max: Numeric = _take_min(aabb.max_x, housed_aabb.max_x) if housed_aabb.max_x is not None else aabb.max_x
                cy_min: Numeric = _take_max(aabb.min_y, housed_aabb.min_y) if housed_aabb.min_y is not None else aabb.min_y
                cy_max: Numeric = _take_min(aabb.max_y, housed_aabb.max_y) if housed_aabb.max_y is not None else aabb.max_y
                if safe_compare(cx_min, cx_max, Comparison.GT) or safe_compare(cy_min, cy_max, Comparison.GT):
                    return True
                return (
                    safe_compare(cx_min, half_w, Comparison.GT)
                    or safe_compare(cx_max, -half_w, Comparison.LT)
                    or safe_compare(cy_min, half_h, Comparison.GT)
                    or safe_compare(cy_max, -half_h, Comparison.LT)
                )

            def _prune_csg(csg: CutCSG) -> Optional[CutCSG]:
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

            relevant_cuts = []
            for cut in housed_timber.cuts:
                cut_csg = cut.get_negative_csg_local()
                if cut_csg is None:
                    continue
                neg_in_housing = adopt_csg(
                    housed_timber.timber.transform,
                    housing_timber.transform,
                    cut_csg,
                )
                pruned = _prune_csg(neg_in_housing)
                if pruned is not None:
                    relevant_cuts.append(pruned)

            return Difference(
                housed_prism_in_housing, relevant_cuts,
                label=CutCSGLabel("housed_timber_body"),
            ) if relevant_cuts else housed_prism_in_housing

        return adopt_csg(
            housed_timber.transform,
            housing_timber.transform,
            housed_timber.get_actual_csg_local(),
        )

    housed_negative_csgs = [_compute_housed_body_in_housing_local(housed_timber) for housed_timber in housed_timbers]
    housing_negative_csg = (
        housed_negative_csgs[0] if len(housed_negative_csgs) == 1
        else SolidUnion(children=housed_negative_csgs, label=CutCSGLabel("housed_timbers"))
    )
    cut_housing = Cutting(
        timber=housing_timber,
        negative_csg=housing_negative_csg,
        label=CutCSGLabel("housing_cut"),
    )

    cuttings: dict[str, Cutting] = {"housing_timber": cut_housing}
    for i, housed_timber in enumerate(housed_timbers, start=1):
        cuttings[f"housed_timber_{i}"] = Cutting(
            timber=housed_timber.timber if isinstance(housed_timber, CutTimber) else housed_timber,
        )

    return Joint(
        cuttings=cuttings,
        ticket=JointTicket(joint_type="free_house"),
        jointAccessories={},
    )
