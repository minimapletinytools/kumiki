"""Which features of a cut timber need to be solved for. See docs/internal/featuresolving-plan.md, Part 1."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterator, List

from .cutcsg import (CSGFeature, CurvedFaceFeature, CutCSG, FaceFeature, FeatureMarkingStatus, OwnedFeatureHit,
                     csg_children)
from .feature_paths import FeatureHandle
from .planar_region import face_reaches_surface
from .rule import V3, create_v3
from .timber import CutTimber

# Whether a flat face is on the finished surface: (face, root, near, reach) -> bool.
FaceTest = Callable[[FeatureHandle[FaceFeature], CutCSG, V3, float], bool]


class Reason(Enum):
    ON_SURFACE = "on_surface"
    CURVED = "curved"
    NON_REAL = "non_real"
    MARKED = "marked"
    EXTRA = "extra"


@dataclass(frozen=True)
class RequiredFeature:
    handle: FeatureHandle[CSGFeature]
    reason: Reason


def _nodes(root: CutCSG) -> Iterator[CutCSG]:
    yield root
    for child in csg_children(root):
        yield from _nodes(child)


def required_features(cut_timber: CutTimber, face_test: FaceTest = face_reaches_surface) -> List[RequiredFeature]:
    """The features of `cut_timber` that need solving, each with why.

    - marked NEVER_MARK: never; marked ALWAYS_MARK: always.
    - non-real (an axis, a reference plane): always.
    - flat faces: when `face_test` finds them on the finished surface. A default face with no
      plane (the cap of an end that runs to infinity) isn't there.
    - curved faces: always.
    - edges and points: only extras, since a primitive's own are solved through its faces.
    """
    root = cut_timber.render_timber_with_cuts_csg_local()
    timber = cut_timber.timber
    near = create_v3(0, 0, float(timber.length) / 2)
    reach = 4 * float(timber.length) + float(max(timber.size[0], timber.size[1]))

    required: List[RequiredFeature] = []
    for node in _nodes(root):
        for feature in node.get_declared_features():
            handle: FeatureHandle[CSGFeature] = FeatureHandle(
                timber=timber, hit=OwnedFeatureHit(feature=feature, owner=node))
            marking = feature.properties.marking_override
            status = marking.mark if marking is not None else FeatureMarkingStatus.OPTIONAL
            if status is FeatureMarkingStatus.NEVER_MARK:
                continue
            if status is FeatureMarkingStatus.ALWAYS_MARK:
                required.append(RequiredFeature(handle, Reason.MARKED))
            elif not feature.real:
                required.append(RequiredFeature(handle, Reason.NON_REAL))
            elif isinstance(feature, FaceFeature) and feature.locate_simple_unbounded(node) is not None:
                face = FeatureHandle(timber=timber, hit=OwnedFeatureHit(feature=feature, owner=node))
                if face_test(face, root, near, reach):
                    required.append(RequiredFeature(handle, Reason.ON_SURFACE))
            elif isinstance(feature, CurvedFaceFeature):
                required.append(RequiredFeature(handle, Reason.CURVED))
            elif feature.feature_key() is None:
                required.append(RequiredFeature(handle, Reason.EXTRA))
    return required
