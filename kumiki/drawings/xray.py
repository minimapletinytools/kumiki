"""Resolve the timber sides from which a drawing may reveal a feature."""

import numpy as np

from ..csg.carriers import CarrierRef
from ..csg.cutcsg import (CSGFeatureType, CutCSG, DerivedEdgeFeature, DerivedPointFeature,
                          OwnedFeatureHit)
from ..csg.identity_memo import memo_by_identity
from ..rule import as_ndarray
from ..timber import PerfectTimberWithin
from ..timber_features import TimberFace


@memo_by_identity
def _tagged_keys(owner: CutCSG):
    return {f.feature_key(): f.properties.xray_from_faces for f in owner.get_declared_features()
            if f.feature_key() is not None and f.properties.xray_from_faces}


def xray_sides(hit: OwnedFeatureHit) -> frozenset[TimberFace]:
    """Return the sides revealing a feature or an edge or corner incident to a tagged face."""
    feature = hit.feature
    sides = feature.properties.xray_from_faces
    if isinstance(feature, (DerivedPointFeature, DerivedEdgeFeature)):
        return sides.union(*(xray_sides(parent) for parent in feature.parents if parent is not None))
    if feature.feature_type() in (CSGFeatureType.EDGE, CSGFeatureType.POINT):
        keys = _tagged_keys(hit.owner)
        if keys:
            for ref in feature.solve_recipe(hit.owner) or ():
                if isinstance(ref, CarrierRef) and ref.owner is hit.owner:
                    sides = sides.union(keys.get(ref.local, ()))
    return sides


def xray_from_view(hit: OwnedFeatureHit, timber: PerfectTimberWithin, look: np.ndarray) -> bool:
    """Return whether the unit world-space camera direction looks through an authored timber side."""
    return any(float(as_ndarray(timber.get_face_direction_global(side)) @ look) < -1 + 1e-8
               for side in xray_sides(hit))
