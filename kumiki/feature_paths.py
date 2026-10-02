"""Feature references: a FeatureHandle in Python, a FeaturePath on the wire.

Python code refers to features directly, by the objects themselves. A FeaturePath
names a feature by timber, CSG labels and feature name, and is only for crossing
to the viewer or the drawings file. `to_feature_path` and `resolve_feature_path`
convert between the two.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from .cutcsg import (CSGFeature, CutCSG, DerivedEdgeFeature, DerivedPointFeature, Difference,
                     OwnedFeatureHit, SolidUnion, csg_children, shared_ancestor)
from .identity import (DerivedFeaturePath, FeaturePath, FeatureRef, ResolvedJointPath,
                       ResolvedTimberPath, SingleFeaturePath)

if TYPE_CHECKING:
    from .timber import CutTimber, Frame, PerfectTimberWithin


def _same_hit(one: OwnedFeatureHit, other: OwnedFeatureHit) -> bool:
    """Same owner node, and the same feature on it: by name, or by parents for a derived one."""
    if one.owner is not other.owner or type(one.feature) is not type(other.feature):
        return False
    if isinstance(one.feature, (DerivedEdgeFeature, DerivedPointFeature)):
        assert isinstance(other.feature, (DerivedEdgeFeature, DerivedPointFeature))
        return _same_hit(one.feature.a, other.feature.a) and _same_hit(one.feature.b, other.feature.b)
    return one.feature.name == other.feature.name


@dataclass(frozen=True, eq=False)
class FeatureHandle:
    """A feature of one timber: the timber, and the feature with the node that owns it.

    A derived feature carries its two parents, so one type covers declared and derived features.
    Equal when it is the same timber and node, compared by identity, and the same feature.
    """
    timber: 'PerfectTimberWithin'
    hit: OwnedFeatureHit

    @property
    def feature(self) -> CSGFeature:
        return self.hit.feature

    @property
    def owner(self) -> CutCSG:
        return self.hit.owner

    def __eq__(self, other) -> bool:
        return (isinstance(other, FeatureHandle) and self.timber is other.timber
                and _same_hit(self.hit, other.hit))

    def __hash__(self) -> int:
        return hash((id(self.timber), id(self.hit.owner), self.hit.feature.name))


def label_name(labeled: Any) -> Optional[str]:
    """The name on a CSG node's or a Cutting's label, or None."""
    return getattr(getattr(labeled, "label", None), "name", None)


def _labelled_children(node: CutCSG) -> List[CutCSG]:
    """The nodes a path step under `node` can name, in document order.

    Unlabelled unions and differences are stepped through; a path names only labelled nodes.
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
    """Every node a path step naming `label` could mean, in document order."""
    return [child for child in _labelled_children(node) if label_name(child) == label]


def candidate_segments(node: CutCSG) -> Dict[int, str]:
    """The path segment for every node a step under `node` can name, keyed by id: `label`, then `label#n`."""
    seen: Dict[str, int] = {}
    segments: Dict[int, str] = {}
    for child in _labelled_children(node):
        label = label_name(child)
        assert label is not None
        occurrence = seen.get(label, 0)
        seen[label] = occurrence + 1
        segments[id(child)] = label if occurrence == 0 else f"{label}#{occurrence}"
    return segments


def find_csg_by_labels(csg: CutCSG, labels: Sequence[str]) -> Optional[CutCSG]:
    """Walk down from `csg` by labels. A labelled `csg` consumes the first step itself."""
    remaining = tuple(labels)
    label = label_name(csg)
    if label is not None:
        if not remaining:
            return csg
        if label != ResolvedJointPath.parse(remaining[0]).path:
            return None
        remaining = remaining[1:]

    node = csg
    for segment in remaining:
        wanted = ResolvedJointPath.parse(segment)
        candidates = labelled_candidates(node, wanted.path)
        if wanted.occurrence >= len(candidates):
            return None
        node = candidates[wanted.occurrence]
    return node


def node_positions(root: CutCSG) -> Dict[int, Tuple[int, int, List[str]]]:
    """Every node under `root`, keyed by id, as (depth, document order, label path)."""
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
    """The uncut body the cuts are taken out of."""
    rendered = cut_timber.render_timber_with_cuts_csg_local()
    return rendered.base if isinstance(rendered, Difference) else rendered


def roots_for_path(cut_timber: 'CutTimber', labels: Sequence[str]) -> Tuple[List[CutCSG], Tuple[str, ...]]:
    """Which trees a path could be in, and what is left of the path to walk.

    A first step naming one of the timber's cuts picks that cut by occurrence. Otherwise
    every cut and the timber's body are searched.
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
    """The declared feature a FeatureRef names on this timber, with its node."""
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
    """A handle to a declared feature, found by CSG labels and name. For authoring by hand."""
    hit = find_declared_feature(cut_timber, FeatureRef(csg_path=tuple(csg_path), feature=feature))
    return None if hit is None else FeatureHandle(timber=cut_timber.timber, hit=hit)


def serialize_feature_path(path: FeaturePath) -> Dict[str, Any]:
    """A FeaturePath as the viewer and the drawings file hold it."""
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
    """The FeaturePath a wire form names, or None if it names nothing usable."""
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
    """The wire reference for a handle, or None if its timber or node isn't in `frame`."""
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
        a, b = ref(feature.a), ref(feature.b)
        if a is None or b is None:
            return None
        return DerivedFeaturePath(timber=timber_path, a=a, b=b,
                                  kind="POINT" if isinstance(feature, DerivedPointFeature) else "EDGE")
    single = ref(handle.hit)
    if single is None:
        return None
    return SingleFeaturePath(timber=timber_path, ref=single, feature_type=feature.feature_type().name)


def resolve_feature_path(path: FeaturePath, frame: 'Frame') -> Optional[FeatureHandle]:
    """The feature a wire reference names in `frame`, or None if it no longer exists there.

    A derived feature is derived again from its two resolved parents.
    """
    cut_timber = frame.cut_timber_at(path.timber)
    if cut_timber is None:
        return None
    if isinstance(path, DerivedFeaturePath):
        first = find_declared_feature(cut_timber, path.a)
        second = find_declared_feature(cut_timber, path.b)
        if first is None or second is None:
            return None
        derive = DerivedPointFeature.derive if path.feature_type == "POINT" else DerivedEdgeFeature.derive
        derived = derive(first, second)
        if derived is None:
            return None
        owner = shared_ancestor(cut_timber.render_timber_with_cuts_csg_local(), first.owner, second.owner)
        return FeatureHandle(timber=cut_timber.timber,
                             hit=OwnedFeatureHit(feature=derived, owner=owner or first.owner))
    assert isinstance(path, SingleFeaturePath)
    hit = find_declared_feature(cut_timber, path.ref)
    return None if hit is None else FeatureHandle(timber=cut_timber.timber, hit=hit)
