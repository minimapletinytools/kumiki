"""FeatureHandle, a reference to a feature on a timber, and its wire form FeaturePath.

TODO rename this file to "FeatureHandle"
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, Sequence, Tuple, Union

from .cutcsg import (CSGFeature, CutCSG, DerivedEdgeFeature, DerivedPointFeature, Difference, F_co,
                     OwnedFeatureHit, SolidUnion, csg_children, shared_ancestor)
from ..identity import (DerivedFeaturePath, FeaturePath, FeatureRef, ResolvedJointPath,
                       ResolvedTimberPath, SingleFeaturePath)

if TYPE_CHECKING:
    from ..timber import CutTimber, Cutting, Frame, PerfectTimberWithin


def hit_identity(feature: CSGFeature, owner: CutCSG) -> Tuple:
    """Return a hashable key for a feature: `(id(owner), name)`, or for a derived feature its parents' keys."""
    if isinstance(feature, (DerivedEdgeFeature, DerivedPointFeature)):
        return (type(feature).__name__,
                tuple(hit_identity(parent.feature, parent.owner) for parent in feature.parents if parent is not None))
    return (id(owner), feature.name)


@dataclass(frozen=True, eq=False)
class FeatureHandle(Generic[F_co]):
    """A feature on one timber: the timber and the hit (feature plus owning node).

    Equal when on the same timber object with the same hit_identity.
    """
    timber: 'PerfectTimberWithin'
    hit: OwnedFeatureHit[F_co]

    @property
    def feature(self) -> F_co:
        return self.hit.feature

    @property
    def owner(self) -> CutCSG:
        return self.hit.owner

    def __eq__(self, other) -> bool:
        return (isinstance(other, FeatureHandle) and self.timber is other.timber
                and hit_identity(self.feature, self.owner) == hit_identity(other.feature, other.owner))

    def __hash__(self) -> int:
        return hash((id(self.timber), hit_identity(self.hit.feature, self.hit.owner)))


def label_name(labeled: Union[CutCSG, 'Cutting']) -> Optional[str]:
    """Return the label name of a CSG node or Cutting, or None."""
    return labeled.label.name


def _labelled_children(node: CutCSG) -> List[CutCSG]:
    """Return the labelled nodes a path step under `node` can name, in document order.

    Looks through unlabelled unions and differences.
    """
    found: List[CutCSG] = []

    def gather(current: CutCSG) -> None:
        children = [current.base, *current.subtract] if isinstance(current, Difference) else csg_children(current)
        for child in children:
            if label_name(child) is not None:
                found.append(child)
            elif isinstance(child, (SolidUnion, Difference)):
                gather(child)

    gather(node)
    return found


def labelled_candidates(node: CutCSG, label: str) -> List[CutCSG]:
    """Return the nodes under `node` labelled `label`, in document order."""
    return [child for child in _labelled_children(node) if label_name(child) == label]


def candidate_segments(node: CutCSG) -> Dict[int, str]:
    """Return each nameable node's path segment (`label`, then `label#1`, ...), keyed by id."""
    seen: Dict[str, int] = {}
    segments: Dict[int, str] = {}
    for child in _labelled_children(node):
        label = label_name(child)
        assert label is not None
        occurrence = seen.get(label, 0)
        seen[label] = occurrence + 1
        segments[id(child)] = label if occurrence == 0 else f"{label}#{occurrence}"
    return segments


def walk_labels(csg: CutCSG, labels: Sequence[str]) -> Tuple[CutCSG, int]:
    """Follow path steps (`label` or `label#n`) down from `csg` as far as they go.

    Returns the node reached and how many steps were taken.
    """
    node = csg
    for taken, segment in enumerate(labels):
        wanted = ResolvedJointPath.parse(segment)
        candidates = labelled_candidates(node, wanted.path)
        if wanted.occurrence >= len(candidates):
            return node, taken
        node = candidates[wanted.occurrence]
    return node, len(labels)


def find_csg_by_labels(csg: CutCSG, labels: Sequence[str]) -> Optional[CutCSG]:
    """Return the node `labels` lead to from `csg`, or None. If `csg` is labelled, it matches the first step."""
    remaining = tuple(labels)
    label = label_name(csg)
    if label is not None:
        if not remaining:
            return csg
        if label != ResolvedJointPath.parse(remaining[0]).path:
            return None
        remaining = remaining[1:]
    node, taken = walk_labels(csg, remaining)
    return node if taken == len(remaining) else None


def node_positions(root: CutCSG) -> Dict[int, Tuple[int, int, List[str]]]:
    """Return every node under `root`, keyed by id, as (depth, document order, label path)."""
    positions: Dict[int, Tuple[int, int, List[str]]] = {}
    order = 0

    def walk(node: CutCSG, depth: int, path: List[str], segments: Dict[int, str]) -> None:
        nonlocal order
        step = segments.get(id(node))
        node_path = path + [step] if step else path
        positions[id(node)] = (depth, order, node_path)
        order += 1
        below = candidate_segments(node) if step else segments
        for child in csg_children(node):
            walk(child, depth + 1, node_path, below)

    walk(root, 0, [], candidate_segments(root))
    return positions


def timber_body_csg(cut_timber: 'CutTimber') -> CutCSG:
    """Return the uncut body of the cut timber's drawn tree."""
    rendered = cut_timber.render_timber_with_cuts_csg_local()
    return rendered.base if isinstance(rendered, Difference) else rendered


def roots_for_path(cut_timber: 'CutTimber', labels: Sequence[str]) -> Tuple[List[CutCSG], Tuple[str, ...]]:
    """Return the trees a path may start in, and the rest of the path.

    If the first step names one of the timber's cuts, that cut alone; otherwise every cut and the body.
    """
    labels = tuple(labels)
    cuts = list(cut_timber.cuts)
    every: List[CutCSG] = [cut.negative_csg for cut in cuts if cut.negative_csg is not None]
    every.append(timber_body_csg(cut_timber))
    if not labels:
        return every, labels

    wanted = ResolvedJointPath.parse(labels[0])
    matching = [cut.negative_csg for cut in cuts if label_name(cut) == wanted.path]
    if not matching:
        return every, labels
    chosen = [root for root in matching[wanted.occurrence:wanted.occurrence + 1] if root is not None]
    return chosen, labels[1:]


def find_declared_feature(cut_timber: 'CutTimber', ref: FeatureRef) -> Optional[OwnedFeatureHit]:
    """Return the declared feature `ref` names on the timber, with its node, or None."""
    roots, labels = roots_for_path(cut_timber, ref.csg_path)
    for root in roots:
        node = find_csg_by_labels(root, labels)
        if node is None:
            continue
        for feature in node.get_declared_features():
            if feature.name == ref.feature:
                return OwnedFeatureHit(feature=feature, owner=node)
    return None


def find_feature(cut_timber: 'CutTimber', csg_path: Sequence[str], feature: str) -> Optional[FeatureHandle]:
    """Return a handle to the declared feature at `csg_path` named `feature`, or None."""
    hit = find_declared_feature(cut_timber, FeatureRef(csg_path=tuple(csg_path), feature=feature))
    return None if hit is None else FeatureHandle(timber=cut_timber.timber, hit=hit)


def serialize_feature_path(path: FeaturePath) -> Dict[str, Any]:
    """Return the JSON form of a FeaturePath."""
    if isinstance(path, DerivedFeaturePath):
        return {
            "kind": "point" if path.feature_type == "POINT" else "edge",
            "timber": str(path.timber),
            "a": {"csgPath": list(path.a.csg_path), "feature": path.a.feature},
            "b": {"csgPath": list(path.b.csg_path), "feature": path.b.feature},
            "type": path.feature_type,
        }
    assert isinstance(path, SingleFeaturePath)
    return {
        "timber": str(path.timber),
        "csgPath": list(path.csg_path),
        "feature": path.feature,
        "type": path.feature_type,
    }


def deserialize_feature_path(source: Any) -> Optional[FeaturePath]:
    """Parse a FeaturePath from its JSON form, or None if malformed."""
    if not isinstance(source, dict):
        return None
    timber = ResolvedTimberPath.parse(str(source.get("timber") or ""))

    def ref(part: Any) -> FeatureRef:
        part = part if isinstance(part, dict) else {}
        steps = part.get("csgPath")
        return FeatureRef(
            csg_path=tuple(str(step) for step in steps) if isinstance(steps, list) else (),
            feature=part.get("feature"),
        )

    kind = source.get("kind")
    if kind in ("edge", "point"):
        return DerivedFeaturePath(
            timber=timber, a=ref(source.get("a")), b=ref(source.get("b")),
            kind="POINT" if kind == "point" else "EDGE",
        )
    return SingleFeaturePath(
        timber=timber, ref=ref(source),
        feature_type=str(source.get("type")) if source.get("type") else None,
    )


def to_feature_path(handle: FeatureHandle, frame: 'Frame') -> Optional[FeaturePath]:
    """Return the FeaturePath of a handle, or None if its timber or node isn't in `frame`."""
    cut_timber = frame.cut_timber_of(handle.timber)
    timber_path = frame.resolved_timber_path_of(handle.timber)
    if cut_timber is None or timber_path is None:
        return None
    positions = node_positions(cut_timber.render_timber_with_cuts_csg_local())

    def ref(hit: OwnedFeatureHit) -> Optional[FeatureRef]:
        position = positions.get(id(hit.owner))
        return None if position is None else FeatureRef(tuple(position[2]), hit.feature.name)

    feature = handle.feature
    if isinstance(feature, (DerivedEdgeFeature, DerivedPointFeature)):
        a, b = (ref(parent) for parent in feature.parents)
        if a is None or b is None:
            return None
        return DerivedFeaturePath(timber=timber_path, a=a, b=b,
                                  kind="POINT" if isinstance(feature, DerivedPointFeature) else "EDGE")
    single = ref(handle.hit)
    if single is None:
        return None
    return SingleFeaturePath(timber=timber_path, ref=single, feature_type=feature.feature_type().name)


def resolve_feature_path(path: FeaturePath, frame: 'Frame') -> Optional[FeatureHandle]:
    """Return the handle `path` names in `frame`, or None. Derived features are re-derived from their parents."""
    cut_timber = frame.cut_timber_at(path.timber)
    if cut_timber is None:
        return None
    if isinstance(path, DerivedFeaturePath):
        first = find_declared_feature(cut_timber, path.a)
        second = find_declared_feature(cut_timber, path.b)
        if first is None or second is None:
            return None
        # Named by both its faces, so an edge derives whatever their groups.
        derived = (DerivedPointFeature.derive(first, second) if path.feature_type == "POINT"
                   else DerivedEdgeFeature.derive(first, second, any_groups=True))
        if derived is None:
            return None
        owner = shared_ancestor(cut_timber.render_timber_with_cuts_csg_local(), first.owner, second.owner)
        return FeatureHandle(timber=cut_timber.timber,
                             hit=OwnedFeatureHit(feature=derived, owner=owner or first.owner))
    assert isinstance(path, SingleFeaturePath)
    hit = find_declared_feature(cut_timber, path.ref)
    return None if hit is None else FeatureHandle(timber=cut_timber.timber, hit=hit)
