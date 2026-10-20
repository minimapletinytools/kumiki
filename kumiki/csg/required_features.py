"""Which features of a cut timber need to be solved for. See docs/internal/featuresolving-plan.md, Part 1."""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Iterator, List

from .cutcsg import (CSGFeature, CurvedFaceFeature, CutCSG, FaceFeature, FeatureMarkingStatus, FeaturePurpose,
                     OwnedFeatureHit, csg_children, measured_by_default)
from .feature_paths import FeatureHandle
from .feature_extent import extents_of

if TYPE_CHECKING:
    from ..timber import CutTimber

# Whether a flat face is on the finished surface of its timber's tree: (face, root) -> bool.
FaceTest = Callable[[FeatureHandle[FaceFeature], CutCSG], bool]


def on_finished_surface(face: FeatureHandle[FaceFeature], root: CutCSG) -> bool:
    """cross_sections.face_reaches_surface, read off the tree's FeatureExtents: the face is cut once,
    and kept for whatever else asks where it is. A tree that can't be cut counts as on the surface."""
    extent = extents_of(root, face.timber).of(face.feature, face.owner)
    return extent is None or not extent.is_empty


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


def required_features(cut_timber: 'CutTimber', face_test: FaceTest = on_finished_surface,
                      include_unmeasured: bool = False) -> List[RequiredFeature]:
    """The features of `cut_timber` that need solving, each with why.

    - rough stock's own faces and relief (measured_by_default): never, unless `include_unmeasured`.
    - marked NEVER_MARK: never; marked ALWAYS_MARK: always.
    - non-real (an axis, a reference plane): always.
    - flat faces: when `face_test` finds them on the finished surface. A default face with no
      plane (the cap of an end that runs to infinity) isn't there.
    - curved faces: always.
    - edges and points: only extras, since a primitive's own are solved through its faces.

    Over the drawn tree -- the rough body carrying every perfect plane, with the cuts -- which is
    what the solver works on.
    """
    root = cut_timber.render_timber_with_cuts_csg_local()
    timber = cut_timber.timber

    required: List[RequiredFeature] = []
    for node in _nodes(root):
        for feature in node.get_declared_features():
            handle: FeatureHandle[CSGFeature] = FeatureHandle(
                timber=timber, hit=OwnedFeatureHit(feature=feature, owner=node))
            marking = feature.properties.marking_override
            status = marking.mark if marking is not None else FeatureMarkingStatus.OPTIONAL
            if status is FeatureMarkingStatus.NEVER_MARK:
                continue
            if not measured_by_default(feature.properties.purpose) and not include_unmeasured:
                continue
            if status is FeatureMarkingStatus.ALWAYS_MARK:
                required.append(RequiredFeature(handle, Reason.MARKED))
            elif not feature.real:
                required.append(RequiredFeature(handle, Reason.NON_REAL))
            elif isinstance(feature, FaceFeature) and feature.locate_simple_unbounded(node) is not None:
                face = FeatureHandle(timber=timber, hit=OwnedFeatureHit(feature=feature, owner=node))
                if face_test(face, root):
                    required.append(RequiredFeature(handle, Reason.ON_SURFACE))
            elif isinstance(feature, CurvedFaceFeature):
                required.append(RequiredFeature(handle, Reason.CURVED))
            elif feature.feature_key() is None:
                required.append(RequiredFeature(handle, Reason.EXTRA))
    return required


def planning_features(cut_timber: 'CutTimber', face_test: FaceTest = on_finished_surface) -> List[RequiredFeature]:
    """The required features a planning drawing solves for: the perfect timber within and its joints' shoulder planes."""
    # TODO figure out what do here, we probably want to return centerplanes as well?
    body = cut_timber.get_extended_rough_csg_with_perfect_features_local()
    return [required for required in required_features(cut_timber, face_test)
            if required.handle.owner is body or required.handle.feature.properties.purpose is FeaturePurpose.SHOULDER]
