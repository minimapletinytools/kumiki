#!/usr/bin/env python3
"""
Persistent stdio runner for the Kigumi VS Code extension.

Protocol:
- stdin: newline-delimited JSON requests
- stdout: newline-delimited JSON responses/events only
- stderr: logs, warnings, tracebacks
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import inspect
import json
import math
import os
import select
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import (TYPE_CHECKING, Any, Callable, Dict, Final, List, Mapping, NamedTuple, Optional, Sequence,
                    Tuple, TypedDict, Union, cast)

# Stations along a line, low then high.
Interval = Tuple[float, float]
# A pointer's ray in timber-local space: origin, direction.
LocalRay = Tuple['Float3', 'Float3']

# --- wire forms ---------------------------------------------------------------
#
# What crosses to the viewer and into the drawings file. Plain dicts at runtime;
# these only tell ty which keys there are. total=False because most are built up
# a key at a time, and a file written by an older version may lack any of them.

Vec3 = List[float]


class GeometryWire(TypedDict, total=False):
    """A located Point, Line or Plane in world space. See _geometry_payload."""
    kind: str  # "point" | "line" | "plane"
    at: Vec3
    direction: Vec3
    normal: Vec3


class FeatureRefWire(TypedDict):
    csgPath: List[str]
    feature: Optional[str]


class AnchorWire(TypedDict, total=False):
    """A FeaturePath (see serialize_feature_path), plus where it resolved to."""
    timber: str
    csgPath: List[str]
    feature: Optional[str]
    type: Optional[str]
    kind: str  # a derived feature's: "edge" | "point"
    a: FeatureRefWire
    b: FeatureRefWire
    at: Optional[Vec3]
    geometry: Optional[GeometryWire]


class PlaneWire(TypedDict):
    at: Vec3
    normal: Vec3


class MeasureKindWire(TypedDict):
    operation: str
    space: str
    direction: str


class PlacementWire(TypedDict):
    offset: float


AngleWire = TypedDict("AngleWire", {"vertex": Vec3, "from": Vec3, "to": Vec3, "normal": Vec3})


class SettledEndWire(TypedDict, total=False):
    form: str  # "point" | "line" | "plane" | "area" | "none"
    normal: Vec3
    direction: Vec3


class SettledValueWire(TypedDict):
    unit: str  # "length" | "angle"
    value: float


class SettledWire(TypedDict):
    """What a measurement comes to. See _settled_measurement."""
    kind: Optional[MeasureKindWire]
    available: List[str]
    space: Optional[str]
    value: Optional[SettledValueWire]
    reason: Optional[str]
    a: Optional[SettledEndWire]
    b: Optional[SettledEndWire]


class MeasureWire(TypedDict, total=False):
    a: AnchorWire
    b: AnchorWire
    measureId: Optional[str]
    # A name ("perpendicular_distance") in files from before kinds were structured.
    kind: Union[MeasureKindWire, str, None]
    placement: Optional[PlacementWire]
    plane: Optional[PlaneWire]
    origin: str  # ORIGIN_*
    suppressed: bool  # MEASURE_SUPPRESSED
    unresolved: List[str]
    angle: Optional[AngleWire]
    settled: SettledWire


class MeasurementRequest(MeasureWire, total=False):
    """What the viewer sends to add, change, restore or delete a measurement."""
    drawingId: str
    viewportId: str
    changes: MeasureWire


class RayWire(TypedDict):
    origin: Vec3
    direction: Vec3


class TolerancesWire(TypedDict, total=False):
    """World units, from what a pixel is worth where the pointer is."""
    edge: float
    point: float


class PickRequest(TypedDict, total=False):
    """A click or hover on a member: find_csg_at_point, hover_feature_at_point."""
    slot: str
    memberKey: str
    point: Vec3
    currentPath: List[str]
    ctrlClick: bool
    tolerances: Optional[TolerancesWire]
    ray: Optional[RayWire]
    candidateIndex: Optional[int]
    # The end already held while measuring, and the camera to judge the pair by.
    heldGeometry: Optional[GeometryWire]
    heldAt: Optional[Vec3]
    heldReference: Optional[AnchorWire]
    look: Optional[Vec3]
    right: Optional[Vec3]
    up: Optional[Vec3]
    space: Optional[str]  # "3d" | "projected"
    drawnMembers: Optional[List[str]]  # in a drawing, the members it draws: what can hide something


class PathPickRequest(TypedDict, total=False):
    """A pick from the tree: find_csg_by_path."""
    slot: str
    memberKey: str
    path: List[str]
    featureLabel: Optional[str]

class MeshWire(TypedDict):
    vertices: List[float]
    indices: List[int]


class SegmentWire(TypedDict):
    start: 'Float3'
    end: 'Float3'


class AnchorPointsWire(TypedDict):
    a: Vec3
    b: Vec3


class PickPlacementWire(TypedDict):
    """Where a measurement to the pick would sit. See _pick_placement."""
    anchors: Optional[AnchorPointsWire]
    angle: Optional[AngleWire]
    settled: Optional[SettledWire]


class VerdictWire(TypedDict, total=False):
    """What a measurement to the pick would be. See _pick_verdict."""
    kinds: List[MeasureKindWire]
    plane: Optional[PlaneWire]
    anchors: Optional[AnchorPointsWire]
    angle: Optional[AngleWire]
    settled: Optional[SettledWire]
    reason: Optional[str]


class CandidateWire(TypedDict):
    label: str
    type: str
    real: bool
    derived: bool
    group: str
    priority: int
    path: List[str]
    hidden: bool


class PickStatsWire(TypedDict, total=False):
    meshWalkMs: float  # not timed for a pick from the tree
    trianglesMatched: int
    totalTriangles: int


class NodeDescriptionWire(TypedDict, total=False):
    """The picked node, and the feature on it if one was. See _describe_pick."""
    nodeKind: str
    nodeDisplayName: Optional[str]
    nodeLabel: Optional[str]
    jointName: Optional[str]
    featureLabel: Optional[str]
    featureType: Optional[str]
    facesToward: Optional[str]
    outwardNormal: Optional['Float3']


class DerivationParentWire(TypedDict):
    path: List[str]
    name: str


class DerivationWire(TypedDict):
    """How a derived feature was formed: the node that owns it, and its two parents."""
    ownerPath: Optional[List[str]]
    parents: List[DerivationParentWire]


class PickResultWire(NodeDescriptionWire, total=False):
    """The answer to a click, a hover or a pick from the tree."""
    memberKey: str
    path: List[str]
    reference: Optional[AnchorWire]
    candidateCount: int
    candidates: List[CandidateWire]
    candidateIndex: Optional[int]
    geometry: Optional[GeometryWire]
    at: Optional[Vec3]
    verdict: Optional[VerdictWire]
    highlightMesh: MeshWire
    parentHighlightMesh: MeshWire
    highlightEdgeSegments: List[SegmentWire]
    derivation: Optional[DerivationWire]
    stats: PickStatsWire

class CameraWire(TypedDict, total=False):
    right: Vec3
    up: Vec3
    look: Vec3
    target: Vec3
    extent: float


class OrbitWire(TypedDict, total=False):
    mode: str  # "free" | "axis"
    axis: Vec3


class PageWire(TypedDict):
    width: float
    height: float


class ViewportWire(TypedDict, total=False):
    id: str
    name: Optional[str]
    rect: List[float]
    locked: bool
    projection: str  # "orthographic" | "perspective"
    orbit: OrbitWire
    camera: CameraWire
    members: Optional[List[str]]
    ghostOthers: bool
    measurements: List[MeasureWire]


class DrawingWire(TypedDict, total=False):
    id: str
    name: str
    members: List[str]
    page: Optional[PageWire]
    cameraControls: List[str]
    viewports: List[ViewportWire]
    origin: str  # ORIGIN_*
    overriddenBy: str
    overridesPythonDrawing: str  # OVERRIDES_KEY
    dangling: bool
    dirty: bool
    unplaceableMeasurements: Dict[str, List[MeasureWire]]


# --- frame and geometry --------------------------------------------------------

# Kiwari.to_payload(), plus the id, frames, canSave and stale the runner adds.
KiwariSectionWire = Dict[str, Any]

# What serialize_sympy turns a number into: a float, or a string for an expression.
Scalar = Union[str, int, float, bool, None]


class TagWire(TypedDict):
    kind: str
    name: str


class TimberSummaryWire(TypedDict):
    name: str
    length: Scalar
    width: Scalar
    height: Scalar
    bottom_position: Any  # serialize_vector
    length_direction: Any
    width_direction: Any
    height_direction: Any
    cuts_count: int


class FrameSummaryWire(TypedDict, total=False):
    name: Optional[str]
    timber_count: int
    accessories_count: int
    timbers: List[TimberSummaryWire]
    accessories: List[Dict[str, str]]
    kiwari: Optional[List[KiwariSectionWire]]


class CylinderAxisWire(TypedDict):
    axisStart: Vec3
    axisEnd: Vec3
    radius: float


class PlaneOutlineWire(TypedDict):
    """A perfect reference plane's outline, cropped to the cut timber, in world space, for drawing it edge-on."""
    normal: Vec3
    positions: List[float]  # segment pairs, flat


class MemberMeshWire(TypedDict, total=False):
    """One member's mesh and what the viewer shows about it. See _base_member_payload."""
    name: str
    memberName: str
    memberType: str  # "timber" | "accessory"
    memberKey: str
    timberKey: str
    kumikiEphemeralId: int
    tags: List[TagWire]
    vertices: List[float]
    indices: List[int]
    prism_length: float
    prism_width: float
    prism_height: float
    perfect_width: float
    perfect_height: float
    nominal_width: float
    nominal_height: float
    csg_nodes: int
    csg_features: int
    timberClass: str
    isPerfectTimber: bool
    cut_length: Optional[float]
    meshSource: str
    hasActualGeometryDifferentFromPerfect: bool
    perfectTimberWithinVertices: List[float]
    perfectTimberWithinIndices: List[int]
    centerplanes: List[PlaneOutlineWire]
    perfectFaces: List[PlaneOutlineWire]
    perfectBoxNoJointsVertices: List[float]
    perfectBoxNoJointsIndices: List[int]
    roughBoxNoJointsVertices: List[float]
    roughBoxNoJointsIndices: List[int]
    cylinderAxis: CylinderAxisWire


class TriangulatedMesh(TypedDict):
    vertices: List[float]
    indices: List[int]
    bounds: Any  # numpy (2, 3): low corner, high corner


class MeshCacheEntry(TypedDict, total=False):
    """Not a wire form: what a slot keeps per member between builds."""
    mesh: MemberMeshWire
    local_csg: Optional['CutCSG']
    cut_timber: 'CutTimber'


class RemeshMetricWire(TypedDict, total=False):
    timberKey: str
    memberType: str
    remesh_s: float
    csg_depth: int
    triangle_count: int


class FootprintWire(TypedDict):
    key: str
    corners: List[Vec3]


class FrameGeometryWire(TypedDict, total=False):
    kind: str
    meshes: List[MemberMeshWire]
    footprints: List[FootprintWire]
    changedKeys: List[str]
    removedKeys: List[str]
    remeshMetrics: List[RemeshMetricWire]
    counts: Dict[str, int]
    profiling: Dict[str, float]


class CuttingSummaryWire(TypedDict):
    cutIndex: int
    label: Optional[str]
    hasCSG: bool
    hasEndCut: bool
    displayName: str


class HighlightWire(TypedDict, total=False):
    """What to light for a feature reference. See _feature_highlight."""
    highlightMesh: MeshWire
    featureType: str
    at: Optional[Vec3]
    highlightEdgeSegments: List[SegmentWire]


class ReferenceLineWire(TypedDict):
    name: str
    primary: bool
    edgePositions: List[float]


# --- trees: layers, assembly, CSG ---------------------------------------------------

class LayerTimberWire(TypedDict):
    kumikiEphemeralId: int
    memberKey: str
    name: str
    tags: List[TagWire]
    cuts: List[CuttingSummaryWire]
    referenceFeatures: List[ReferenceLineWire]


class LayerAccessoryWire(TypedDict):
    kumikiEphemeralId: int
    memberKey: str
    name: str
    type: str
    jointKumikiEphemeralId: Optional[int]


class JointMemberWire(TypedDict):
    timberKumikiEphemeralId: int
    cutIndices: List[int]


class LayerJointWire(TypedDict):
    kumikiEphemeralId: int
    name: str
    jointType: Optional[str]
    members: List[JointMemberWire]
    accessoryKumikiEphemeralIds: List[int]


class FramePartWire(TypedDict):
    """One @frame of several drawn together."""
    name: str
    timberKumikiEphemeralIds: List[int]
    jointKumikiEphemeralIds: List[int]


class LayersWire(TypedDict):
    frameName: Optional[str]
    timbers: List[LayerTimberWire]
    accessories: List[LayerAccessoryWire]
    joints: List[LayerJointWire]
    frames: Optional[List[FramePartWire]]
    assembly: Optional[Dict[str, bool]]


class RotationWire(TypedDict):
    axisPosition: Vec3
    axisDirection: Vec3
    angle: float


class MovementWire(TypedDict, total=False):
    kumikiEphemeralId: int
    memberKey: Optional[str]
    direction: Vec3
    distance: float
    dragged: bool
    rotation: RotationWire


class AssemblyStepWire(TypedDict):
    order: int
    suborder: int
    substep: int
    movements: List[MovementWire]


class AssemblyFailureWire(TypedDict):
    order: Optional[int]
    suborder: int
    message: str
    diagnostics: List[str]


class AssemblyWire(TypedDict):
    steps: List[AssemblyStepWire]
    warnings: List[str]
    failure: Optional[AssemblyFailureWire]


class FeatureWire(TypedDict):
    name: str
    type: str
    group: str
    real: bool


class CSGNodeWire(TypedDict):
    kind: str
    displayName: str
    label: Optional[str]
    path: List[str]
    role: Optional[str]
    parity: str
    jointName: Optional[str]
    jointId: Optional[str]
    cutIndex: Optional[int]
    features: List[FeatureWire]
    children: List['CSGNodeWire']


class CSGTreeWire(TypedDict, total=False):
    tree: CSGNodeWire
    memberKey: str


# --- slots, patterns, tools and responses ----------------------------------------------



class FrameCountsWire(TypedDict):
    name: Optional[str]
    timber_count: int
    accessories_count: int


class SlotLoadedWire(TypedDict, total=False):
    slot: str
    examplePath: str
    patternName: str
    frame: FrameCountsWire
    kiwari: Optional[List[KiwariSectionWire]]
    profiling: Dict[str, float]


class PatternEntryWire(TypedDict):
    path: str
    name: str
    tags: List[str]
    groups: List[str]
    source_file: Optional[str]


class PatternSourceWire(TypedDict):
    source: str  # "shipped" | "local"
    folder: str
    patterns: List[PatternEntryWire]


class PatternListWire(TypedDict):
    sources: List[PatternSourceWire]
    scan_s: float


class ToolsWire(TypedDict):
    tools: List[Dict[str, str]]
    rejectedEntries: List[Dict[str, str]]


class ToolRunWire(TypedDict):
    name: str
    output: str


class ReadyEventWire(ToolsWire):
    type: str
    examplePath: str
    commands: List[str]
    frame: FrameCountsWire
    kiwari: Optional[List[KiwariSectionWire]]


class ErrorWire(TypedDict):
    message: str
    type: str
    traceback: str


class ResponseWire(TypedDict, total=False):
    """Every answer to a request: `result` when ok, `error` when not."""
    id: Any
    ok: bool
    command: str
    result: Any
    error: ErrorWire
    kiwari: Optional[List[KiwariSectionWire]]  # a failed reload's, marked stale

# --- member entries -------------------------------------------------------------
#
# Not wire forms: what _assign_member_keys pairs each member's key with.

class TimberEntry(TypedDict):
    memberKey: str
    kumikiEphemeralId: int
    timber: 'PerfectTimberWithin'
    cutTimber: 'CutTimber'
    displayName: str


class AccessoryEntry(TypedDict):
    memberKey: str
    kumikiEphemeralId: int
    accessory: 'Accessory'
    displayName: str
    type: str

if TYPE_CHECKING:
    # Annotations only. kumiki must NOT be imported at module scope for
    # anything used at runtime: _purge_project_modules drops modules under the
    # project root that are not in a venv, which in a dev checkout includes
    # kumiki itself. A module-level class reference would then leave isinstance
    # comparing against a stale class object after a reload. Under
    # TYPE_CHECKING there is no runtime import at all, so annotations can be
    # concrete while every isinstance check still imports inside its function.
    from kumiki.csg.cutcsg import CSGFeature, CSGParity, CutCSG, FeatureTestTolerances, OwnedFeatureHit
    from kumiki.drawings.drawing import (AngleRays, MeasureSpan, MeasurementKind, MeasurementPlane, MeasurementSpace,
                                         VectorLike, Viewport, ViewAxes, ViewportId)
    from kumiki.csg.feature_paths import FeatureHandle
    from kumiki.drawings.cameras import CameraFrame, OrientedBox
    from kumiki.drawings.measuring import EndForm, Settled
    from kumiki.drawings.layout import PlacedViewport
    from kumiki.geometry import Line, Plane, Point
    from kumiki.identity import FeaturePath
    from kumiki.kiwari import Kiwari
    from kumiki.ticket import Ticket
    from kumiki.timber import Accessory, CutTimber, Cutting, Frame, Joint, PerfectTimberWithin
    from kumiki.viewer.rule_at_home import Float3, Rows3

    Located = Union[Point, Line, Plane]
    # A picked feature, the node that owns it, and what it lies on.
    LocatedPick = Tuple[CSGFeature, CutCSG, Optional[Located]]


def _find_project_root_from_argv() -> "Tuple[Path | None, bool]":
    """Resolve project root and mode.

    Priority:
    1) argv[2] explicit project root from extension (if provided)
    2) walk up from argv[1] target file path

    Returns (root_path, is_local_dev) or (None, False).
    """
    explicit_root: Path | None = None
    if len(sys.argv) >= 3 and sys.argv[2]:
        candidate_root = Path(sys.argv[2]).resolve()
        if candidate_root.exists():
            explicit_root = candidate_root

    if explicit_root is not None:
        if (explicit_root / "kumiki").is_dir() and (explicit_root / "pyproject.toml").is_file():
            return explicit_root, True
        return explicit_root, False

    if len(sys.argv) < 2:
        return None, False

    candidate = Path(sys.argv[1]).resolve().parent
    while True:
        # Local-dev should only match an actual kumiki repo root.
        if (candidate / "kumiki").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate, True
        if (candidate / ".kigumi" / "kumiki.yaml").is_file():
            return candidate, False
        if (candidate / ".kigumi.yaml").is_file():
            return candidate, False
        parent = candidate.parent
        if parent == candidate:
            return None, False
        candidate = parent


_project_root, _is_local_dev = _find_project_root_from_argv()
if _project_root is not None:
    _project_root_str = str(_project_root)
    if _is_local_dev and _project_root_str not in sys.path:
        sys.path.insert(0, _project_root_str)

    # If we're not running from the venv, re-exec with the venv python so all
    # dependencies (sympy etc.) are available.
    def _find_venv_python(root: Path) -> "Path | None":
        for rel in (".venv/bin/python3", ".venv/bin/python", "venv/bin/python3", "venv/bin/python"):
            p = root / rel
            if p.exists():
                return p
        return None

    # Only when run as the runner: imported (by a test), argv is someone else's,
    # and exec would replace their process.
    _venv_python = _find_venv_python(_project_root)
    if (__name__ == "__main__" and _venv_python is not None
            and Path(sys.executable).resolve() != _venv_python.resolve()):
        os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)
        # os.execv replaces the current process; code below never runs if it succeeds


# Enable milestone emission so pattern scripts can report progress to the viewer.
os.environ["KIGUMI_VIEWER_MILESTONES"] = "1"

TARGET_MODULE_NAME = "_kigumi_viewer_target"


@dataclass(frozen=True)
class KiwariGroup:
    """One set of parameters, and the frames built from it.

    Frames share one when their kiwari were resolved from the same declared kiwari.
    """
    frames: Tuple[str, ...]
    kiwari: Any

    @property
    def id(self) -> str:
        """What the viewer calls it: its frames, which stay the same from one build to the next."""
        return ",".join(self.frames)


@dataclass
class SlotState:
    """State for a single named viewer slot (e.g. 'main' or a pattern)."""
    file_path: Path
    module: Any
    frame: Any
    mesh_cache: Dict[str, MeshCacheEntry] = field(default_factory=dict)
    patternbook: Optional[Any] = None
    single_pattern_name: Optional[str] = None
    # What this slot was last built from, bound: one group per kiwari its frames
    # returned, or the Pattern's for a pattern. Kept on the slot rather than only
    # on the frames so a build that fails leaves the panel something to dial
    # back from.
    kiwari_groups: Tuple[KiwariGroup, ...] = ()
    # Each @frame's name and its own frame, when a file shows several as one.
    frame_parts: Tuple[Tuple[str, Any], ...] = ()
    # The file's @tool functions, and any @frame / @tool rejected for its signature.
    tools: Tuple[Any, ...] = ()
    rejected_entries: Tuple[Any, ...] = ()
    # Drawings made in this session and not yet saved. They live here rather
    # than in the viewer so python stays the one place a drawing comes from,
    # and they are lost on reload, which is what "unsaved" should mean.
    pending_drawings: List[DrawingWire] = field(default_factory=list)
    # Which import of the project's modules (kumiki, in a dev checkout) this was built
    # with. See _project_generation.
    generation: int = 0


@dataclass
class RunnerState:
    """Top-level runner state containing one or more named slots."""
    slots: Dict[str, SlotState] = field(default_factory=dict)
    active_slot: str = "main"

    # --- backwards-compat shims so existing code that reads state.frame etc. still works ---
    @property
    def _active(self) -> SlotState:
        return self.slots[self.active_slot]

    @property
    def file_path(self) -> Path:
        return self._active.file_path

    @property
    def module(self) -> Any:
        return self._active.module

    @property
    def frame(self) -> Any:
        return self._active.frame

    @property
    def mesh_cache(self) -> Dict[str, MeshCacheEntry]:
        return self._active.mesh_cache

    def get_slot(self, slot: str) -> SlotState:
        if slot not in self.slots:
            raise KeyError(f"No slot named '{slot}'. Active slots: {list(self.slots.keys())}")
        return self.slots[slot]


def log_stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# stdout carries the newline-delimited JSON protocol and is written from both
# the main request/response loop and the background assembly-solve thread
# (see the `get_assembly` handler below). A write of more than PIPE_BUF bytes
# is not atomic, so unsynchronized concurrent prints can interleave their
# bytes on the pipe and corrupt the line-based protocol -- serialize all
# stdout writes through this lock.
_stdout_lock = threading.Lock()


def emit_message(payload: Mapping[str, Any]) -> None:
    with _stdout_lock:
        print(json.dumps(payload), flush=True)


def serialize_sympy(obj: Any) -> Scalar:
    if hasattr(obj, "evalf"):
        return str(obj)
    if hasattr(obj, "__float__"):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    return obj if isinstance(obj, (str, int, float, bool)) or obj is None else str(obj)


def serialize_vector(vec: Any) -> Any:
    if vec is None:
        return None
    try:
        return [serialize_sympy(vec[i, 0]) for i in range(vec.shape[0])]
    except Exception:
        return str(vec)


def _vector3_to_floats(vec: Any) -> list:
    """Exact float triple from a 3x1 sympy Matrix, for numeric (non-display) use."""
    return [float(vec[i, 0]) for i in range(3)]


def get_timber_display_name(timber: 'PerfectTimberWithin') -> str:
    if hasattr(timber, "ticket") and hasattr(timber.ticket, "path"):
        return timber.ticket.path
    name = getattr(timber, "name", None)
    return str(name) if name is not None else type(timber).__name__


def _compute_csg_depth(csg: 'CutCSG') -> int:
    from kumiki.csg.cutcsg import SolidUnion, Difference

    if isinstance(csg, SolidUnion):
        if not csg.children:
            return 1
        return 1 + max(_compute_csg_depth(child) for child in csg.children)

    if isinstance(csg, Difference):
        depths: List[int] = [_compute_csg_depth(csg.base)]
        depths.extend(_compute_csg_depth(child) for child in csg.subtract)
        return 1 + max(depths)

    return 1


def _count_csg_nodes_and_features(csg: 'CutCSG') -> Tuple[int, int]:
    """Return (node_count, named_feature_count) for the CSG tree."""
    from kumiki.csg.cutcsg import SolidUnion, Difference

    nodes = 1
    features = 0

    features += len(_declared_feature_names(csg))

    if isinstance(csg, SolidUnion):
        for child in csg.children:
            cn, cf = _count_csg_nodes_and_features(child)
            nodes += cn
            features += cf
    elif isinstance(csg, Difference):
        cn, cf = _count_csg_nodes_and_features(csg.base)
        nodes += cn
        features += cf
        for sub in csg.subtract:
            cn, cf = _count_csg_nodes_and_features(sub)
            nodes += cn
            features += cf

    return (nodes, features)


def serialize_cut_timber(cut_timber: 'CutTimber') -> TimberSummaryWire:
    timber = cut_timber.timber
    return {
        "name": get_timber_display_name(timber),
        "length": serialize_sympy(timber.length),
        "width": serialize_sympy(timber.size[0]),
        "height": serialize_sympy(timber.size[1]),
        "bottom_position": serialize_vector(timber.get_bottom_position_global()),
        "length_direction": serialize_vector(timber.get_length_direction_global()),
        "width_direction": serialize_vector(timber.get_width_direction_global()),
        "height_direction": serialize_vector(timber.get_height_direction_global()),
        "cuts_count": len(cut_timber.cuts) if hasattr(cut_timber, "cuts") else 0,
    }


def prism_to_mesh(prism: Any) -> MeshWire:
    """Convert a RectangularPrism to a flat vertex list + index list triangle mesh.

    Vertex layout (8 corners, indices 0-7):
        0: -hw, -hh, z0    1: +hw, -hh, z0    2: +hw, +hh, z0    3: -hw, +hh, z0
        4: -hw, -hh, z1    5: +hw, -hh, z1    6: +hw, +hh, z1    7: -hw, +hh, z1
    where z0 = start_distance (bottom) and z1 = end_distance (top) in local Z.
    """
    hw = float(prism.size[0]) / 2.0
    hh = float(prism.size[1]) / 2.0
    z0 = float(prism.start_distance) if prism.start_distance is not None else 0.0
    z1 = float(prism.end_distance) if prism.end_distance is not None else 0.0

    M = prism.transform.orientation.matrix
    P = prism.transform.position
    # Convert SymPy values to Python floats once
    m = [[float(M[r, c]) for c in range(3)] for r in range(3)]
    p = [float(P[0]), float(P[1]), float(P[2])]

    def g(x: float, y: float, z: float) -> list:
        return [
            p[0] + m[0][0] * x + m[0][1] * y + m[0][2] * z,
            p[1] + m[1][0] * x + m[1][1] * y + m[1][2] * z,
            p[2] + m[2][0] * x + m[2][1] * y + m[2][2] * z,
        ]

    verts = [
        g(-hw, -hh, z0),  # 0
        g( hw, -hh, z0),  # 1
        g( hw,  hh, z0),  # 2
        g(-hw,  hh, z0),  # 3
        g(-hw, -hh, z1),  # 4
        g( hw, -hh, z1),  # 5
        g( hw,  hh, z1),  # 6
        g(-hw,  hh, z1),  # 7
    ]

    # 12 triangles with outward-facing CCW normals (verified via cross-product)
    # Face naming matches kumiki.timber.TimberFace: RIGHT=+X, FRONT=+Y, LEFT=-X, BACK=-Y
    # (see RectangularPrismFeature.test_point_unbounded in kumiki/csg/cutcsg.py).
    indices = [
        0, 2, 1,   0, 3, 2,  # bottom (-Z face)
        4, 5, 6,   4, 6, 7,  # top    (+Z face)
        0, 1, 5,   0, 5, 4,  # back   (-Y face)
        3, 7, 6,   3, 6, 2,  # front  (+Y face)
        3, 0, 4,   3, 4, 7,  # left   (-X face)
        1, 2, 6,   1, 6, 5,  # right  (+X face)
    ]

    return {
        "vertices": [coord for v in verts for coord in v],  # flat [x0,y0,z0, x1,y1,z1, ...]
        "indices": indices,
    }


def _triangulate_local_csg(cut_timber: 'CutTimber', local_csg: 'CutCSG') -> TriangulatedMesh:
    """Triangulate a local CSG in the timber's frame, returning flat vertex/index lists."""
    from kumiki.csg.cutcsg import adopt_csg
    from kumiki.rule import Transform
    from kumiki.csg.triangles import triangulate_cutcsg

    global_csg = adopt_csg(cut_timber.timber.transform, Transform.identity(), local_csg)
    triangle_mesh = triangulate_cutcsg(global_csg).mesh

    if triangle_mesh.vertices.size == 0 or triangle_mesh.faces.size == 0:
        raise RuntimeError("triangulate_cutcsg produced empty mesh")

    bounds = triangle_mesh.bounds
    if bounds is None:
        raise RuntimeError("triangulate_cutcsg produced mesh without bounds")

    return {
        "vertices": triangle_mesh.vertices.reshape(-1).tolist(),
        "indices": triangle_mesh.faces.reshape(-1).tolist(),
        "bounds": bounds,
    }


def _perfect_reference_outlines(
    timber: 'PerfectTimberWithin', root: 'CutCSG', centerplanes: bool,
) -> List[PlaneOutlineWire]:
    """What a drawing draws dotted, edge-on (picking.perfect_reference_outlines), as the wire has it."""
    from kumiki.viewer.picking import perfect_reference_outlines

    return [{"normal": outline.normal, "positions": outline.positions}
            for outline in perfect_reference_outlines(timber, root, centerplanes)]


def _base_member_payload(
    *,
    name: str,
    member_type: str,
    member_key: str,
    kumiki_id: int,
    tags: List[TagWire],
    vertices: List[float],
    indices: List[int],
    prism_length: Any,
    prism_width: Any,
    prism_height: Any,
    perfect_width: Any,
    perfect_height: Any,
    nominal_width: Any,
    nominal_height: Any,
) -> MemberMeshWire:
    """Common member-mesh payload shared by every geometry serializer.

    Callers add type-specific extras (csg counts, timber class, fallback
    markers, perfect-within meshes) to the returned dict.
    """
    return {
        "name": name,
        "memberName": name,
        "memberType": member_type,
        "memberKey": member_key,
        "timberKey": member_key,
        "kumikiEphemeralId": kumiki_id,
        "tags": tags,
        "vertices": vertices,
        "indices": indices,
        "prism_length": round(float(prism_length), 6),
        "prism_width": round(float(prism_width), 6),
        "prism_height": round(float(prism_height), 6),
        "perfect_width": round(float(perfect_width), 6),
        "perfect_height": round(float(perfect_height), 6),
        "nominal_width": round(float(nominal_width), 6),
        "nominal_height": round(float(nominal_height), 6),
    }


def _cut_length(cut_timber: 'CutTimber') -> Optional[float]:
    """How long the timber is once its end cuts are made.

    A timber with an end joint is not cut to length first -- the joint decides
    where its end lands, so `timber.length` is the stock it was cut from rather
    than the piece that comes out. The bounding prism is already cropped to the
    end cuts, so its extent along the length axis is the finished piece.
    """
    try:
        prism = cut_timber.get_perfect_timber_within_bounding_box_prism()
        if prism.start_distance is None or prism.end_distance is None:
            return None
        return round(float(prism.end_distance - prism.start_distance), 6)
    except Exception as exc:
        log_stderr(f"Warning: could not measure cut length: {exc}")
        return None


def _cut_timber_to_triangle_mesh_payload(
    cut_timber: 'CutTimber',
    local_csg: 'CutCSG',
    timber_key: str,
) -> MemberMeshWire:
    actual = _triangulate_local_csg(cut_timber, local_csg)
    vertices = actual["vertices"]
    indices = actual["indices"]
    dims = actual["bounds"][1] - actual["bounds"][0]

    timber = cut_timber.timber
    timber_tags = _serialize_timber_tags(getattr(timber, "ticket", None))
    perfect_size = timber.get_perfect_size()
    nominal_size = timber.get_rough_size()
    csg_nodes, csg_features = _count_csg_nodes_and_features(local_csg)
    timber_kumiki_id = int(timber.ticket.kumiki_id)
    timber_class = type(timber).__name__
    is_perfect = bool(timber.is_perfect_timber())
    # is_perfect_timber() only checks nominal half-sizes vs perfect size; it
    # does not detect actual non-rectangular geometry (e.g. RoundTimber has
    # is_perfect_timber()==True when diameter==size, but its actual CSG is a
    # cylinder, not a rectangular prism). Use class identity to determine
    # whether the actual geometry differs from the perfect timber within.
    non_rectangular_classes = ('RoundTimber', 'MeshTimber', 'RegularPolygonTimber')
    has_non_rectangular_actual = timber_class in non_rectangular_classes

    # Top-level vertices/indices remain the actual-geometry mesh for
    # backwards compatibility with viewers that pre-date the dual mesh.
    payload = _base_member_payload(
        name=get_timber_display_name(timber),
        member_type="timber",
        member_key=timber_key,
        kumiki_id=timber_kumiki_id,
        tags=timber_tags,
        vertices=vertices,
        indices=indices,
        prism_length=getattr(timber, "length", dims[2]),
        prism_width=getattr(timber, "size", [dims[0], dims[1]])[0],
        prism_height=getattr(timber, "size", [dims[0], dims[1]])[1],
        perfect_width=perfect_size[0],
        perfect_height=perfect_size[1],
        nominal_width=nominal_size[0],
        nominal_height=nominal_size[1],
    )
    payload.update(
        csg_nodes=csg_nodes,
        csg_features=csg_features,
        timberClass=timber_class,
        isPerfectTimber=is_perfect,
        cut_length=_cut_length(cut_timber),
    )

    # For non-rectangular-actual timbers, also triangulate the perfect-AABB CSG
    # so the viewer can swap meshes locally without round-tripping to Python.
    if has_non_rectangular_actual:
        try:
            perfect_csg = cut_timber.render_perfect_timber_within_with_cuts_csg_local()
            perfect = _triangulate_local_csg(cut_timber, perfect_csg)
            payload["perfectTimberWithinVertices"] = perfect["vertices"]
            payload["perfectTimberWithinIndices"] = perfect["indices"]
            payload["hasActualGeometryDifferentFromPerfect"] = True
        except Exception as exc:  # noqa: BLE001 — best-effort optional payload
            log_stderr(
                f"Warning: failed to build perfect-AABB mesh for "
                f"{get_timber_display_name(timber)}: {exc}"
            )
            payload["hasActualGeometryDifferentFromPerfect"] = False
    else:
        payload["hasActualGeometryDifferentFromPerfect"] = False
    payload["centerplanes"] = _perfect_reference_outlines(timber, local_csg, centerplanes=True)
    payload["perfectFaces"] = _perfect_reference_outlines(timber, local_csg, centerplanes=False)

    # No-joints box geometry: plain rectangular boxes with no CSG cuts applied at
    # all (no joint cuts, no mortise holes), cropped in length only by this
    # timber's aggregated end-cut trims. Built unconditionally (not gated behind
    # has_non_rectangular_actual) since a joint cut changes what a no-joints box
    # looks like for every timber shape, not just non-rectangular ones.
    try:
        perfect_box_mesh = prism_to_mesh(cut_timber.get_perfect_timber_within_bounding_box_prism())
        payload["perfectBoxNoJointsVertices"] = perfect_box_mesh["vertices"]
        payload["perfectBoxNoJointsIndices"] = perfect_box_mesh["indices"]
    except Exception as exc:  # noqa: BLE001 — best-effort optional payload
        log_stderr(
            f"Warning: failed to build perfect-box-no-joints mesh for "
            f"{get_timber_display_name(timber)}: {exc}"
        )

    try:
        rough_box_mesh = prism_to_mesh(cut_timber.get_rough_bounding_box_prism())
        payload["roughBoxNoJointsVertices"] = rough_box_mesh["vertices"]
        payload["roughBoxNoJointsIndices"] = rough_box_mesh["indices"]
    except Exception as exc:  # noqa: BLE001 — best-effort optional payload
        log_stderr(
            f"Warning: failed to build rough-box-no-joints mesh for "
            f"{get_timber_display_name(timber)}: {exc}"
        )

    return payload


def _accessory_to_triangle_mesh_payload(
    accessory: 'Accessory',
    local_csg: 'CutCSG',
    accessory_key: str,
    accessory_name: str,
) -> MemberMeshWire:
    import math

    from kumiki.csg.cutcsg import Cylinder, adopt_csg
    from kumiki.rule import Transform
    from kumiki.csg.triangles import triangulate_cutcsg

    # Accessory itself declares no transform; the kinds placed in the world do.
    placed = getattr(accessory, "transform", None)
    if placed is not None:
        global_csg = adopt_csg(placed, Transform.identity(), local_csg)
    else:
        # Accessories that already carry global-space CSG (e.g. CSGAccessory)
        # do not need an additional transform adoption.
        global_csg = local_csg
    triangle_mesh = triangulate_cutcsg(global_csg).mesh

    vertices = triangle_mesh.vertices.reshape(-1).tolist()
    indices = triangle_mesh.faces.reshape(-1).tolist()

    bounds = triangle_mesh.bounds
    dims = bounds[1] - bounds[0]

    accessory_kumiki_id = int(accessory.ticket.kumiki_id) if getattr(accessory, "ticket", None) is not None else 0
    payload = _base_member_payload(
        name=accessory_name,
        member_type="accessory",
        member_key=accessory_key,
        kumiki_id=accessory_kumiki_id,
        # Only timbers carry tags; an accessory has no ticket field for them.
        tags=[],
        vertices=vertices,
        indices=indices,
        prism_length=dims[2],
        prism_width=dims[0],
        prism_height=dims[1],
        perfect_width=dims[0],
        perfect_height=dims[1],
        nominal_width=dims[0],
        nominal_height=dims[1],
    )

    # Round accessories (pegs, dowels, ...) mesh as a faceted polygon
    # approximation, so EdgesGeometry's fixed angle threshold never catches
    # the curved barrel -- only the flat end caps get outlined. Ship the
    # exact cylinder primitive so the viewer can draw the two true,
    # camera-facing silhouette lines each frame instead (see
    # updateCylinderSilhouettes() in viewer-app.js).
    if (
        isinstance(global_csg, Cylinder)
        and global_csg.start_distance is not None
        and global_csg.end_distance is not None
    ):
        axis = _vector3_to_floats(global_csg.axis_direction)
        axis_len = math.sqrt(sum(c * c for c in axis)) or 1.0
        axis = [c / axis_len for c in axis]
        position = _vector3_to_floats(global_csg.position)
        start = float(global_csg.start_distance)
        end = float(global_csg.end_distance)
        payload["cylinderAxis"] = {
            "axisStart": [position[i] + axis[i] * start for i in range(3)],
            "axisEnd": [position[i] + axis[i] * end for i in range(3)],
            "radius": float(global_csg.radius),
        }

    return payload


def _cut_timber_to_bbox_mesh_payload(
    cut_timber: 'CutTimber',
    timber_key: str,
) -> MemberMeshWire:
    """Fallback mesh payload based on a cut timber's oriented bounding prism.

    This path avoids trimesh boolean triangulation and keeps rendering usable
    when optional backend dependencies are unavailable.

    haven't tried this, not sure how well it works, I guess the bbox might not be oriented correctly in this version...
    """
    timber = cut_timber.timber
    timber_tags = _serialize_timber_tags(getattr(timber, "ticket", None))
    perfect_size = timber.get_perfect_size()
    nominal_size = timber.get_rough_size()
    prism = cut_timber.get_perfect_timber_within_bounding_box_prism()
    mesh = prism_to_mesh(prism)

    csg_nodes, csg_features = _count_csg_nodes_and_features(cut_timber.render_timber_with_cuts_csg_local())
    timber_kumiki_id = int(timber.ticket.kumiki_id)
    timber_class = type(timber).__name__
    is_perfect = bool(timber.is_perfect_timber())
    payload = _base_member_payload(
        name=get_timber_display_name(timber),
        member_type="timber",
        member_key=timber_key,
        kumiki_id=timber_kumiki_id,
        tags=timber_tags,
        vertices=mesh["vertices"],
        indices=mesh["indices"],
        prism_length=getattr(timber, "length", 0.0),
        prism_width=getattr(timber, "size", [0.0, 0.0])[0],
        prism_height=getattr(timber, "size", [0.0, 0.0])[1],
        perfect_width=perfect_size[0],
        perfect_height=perfect_size[1],
        nominal_width=nominal_size[0],
        nominal_height=nominal_size[1],
    )
    payload.update(
        csg_nodes=csg_nodes,
        csg_features=csg_features,
        meshSource="bounding-prism-fallback",
        timberClass=timber_class,
        isPerfectTimber=is_perfect,
        hasActualGeometryDifferentFromPerfect=False,
        cut_length=_cut_length(cut_timber),
    )
    return payload


def build_real_geometry(state: RunnerState, slot_state: Optional['SlotState'] = None) -> FrameGeometryWire:
    """Build triangle mesh geometry for every cut timber."""
    ss = slot_state if slot_state is not None else state._active
    frame = ss.frame
    meshes: List[MemberMeshWire] = []
    changed_keys: List[str] = []
    remesh_metrics: List[RemeshMetricWire] = []
    seen_keys = set()
    key_counts: Dict[str, int] = {}

    for cut_timber in frame.cut_timbers:
        try:
            timber = cut_timber.timber
            key_base = get_timber_display_name(timber)

            occurrence = key_counts.get(key_base, 0)
            key_counts[key_base] = occurrence + 1
            timber_key = f"{key_base}#{occurrence}"

            local_csg = cut_timber.render_timber_with_cuts_csg_local()

            remesh_t0 = time.monotonic()
            csg_depth = _compute_csg_depth(local_csg)
            mesh_payload = _cut_timber_to_triangle_mesh_payload(
                cut_timber,
                local_csg,
                timber_key,
            )
            remesh_s = time.monotonic() - remesh_t0
            triangle_count = len(mesh_payload.get("indices", [])) // 3
            ss.mesh_cache[timber_key] = {
                "mesh": mesh_payload,
                "local_csg": local_csg,
                "cut_timber": cut_timber,
            }
            changed_keys.append(timber_key)
            remesh_metrics.append({
                "timberKey": timber_key,
                "remesh_s": remesh_s,
                "csg_depth": csg_depth,
                "triangle_count": triangle_count,
            })

            meshes.append(mesh_payload)
            seen_keys.add(timber_key)
        except Exception as exc:
            triangulation_empty_or_invalid = (
                "triangulate_cutcsg produced empty mesh" in str(exc)
                or "triangulate_cutcsg produced mesh without bounds" in str(exc)
                or "'NoneType' object is not subscriptable" in str(exc)
            )

            if triangulation_empty_or_invalid:
                try:
                    mesh_payload = _cut_timber_to_bbox_mesh_payload(cut_timber, timber_key)
                    triangle_count = len(mesh_payload.get("indices", [])) // 3
                    ss.mesh_cache[timber_key] = {
                        "mesh": mesh_payload,
                        "local_csg": None,
                        "cut_timber": cut_timber,
                    }
                    changed_keys.append(timber_key)
                    remesh_metrics.append({
                        "timberKey": timber_key,
                        "remesh_s": 0.0,
                        "csg_depth": 1,
                        "triangle_count": triangle_count,
                    })

                    meshes.append(mesh_payload)
                    seen_keys.add(timber_key)
                    log_stderr(
                        "Warning: triangulation produced empty/invalid mesh; "
                        f"rendered fallback bounding prism for {get_timber_display_name(cut_timber.timber)}"
                    )
                    continue
                except Exception as fallback_exc:
                    log_stderr(
                        f"Warning: fallback geometry failed for {get_timber_display_name(cut_timber.timber)}: {fallback_exc}"
                    )

            log_stderr(f"Warning: skipping geometry for {get_timber_display_name(cut_timber.timber)}: {exc}")

    accessories = list(frame.accessories) if hasattr(frame, "accessories") and frame.accessories else []
    for accessory in accessories:
        try:
            accessory_type = type(accessory).__name__
            key_base = f"accessory:{accessory_type}"

            occurrence = key_counts.get(key_base, 0)
            key_counts[key_base] = occurrence + 1
            accessory_key = f"{key_base}#{occurrence}"
            accessory_name = f"{accessory_type} {occurrence + 1}"

            local_csg = accessory.get_csg_local()

            remesh_t0 = time.monotonic()
            csg_depth = _compute_csg_depth(local_csg)
            mesh_payload = _accessory_to_triangle_mesh_payload(
                accessory,
                local_csg,
                accessory_key,
                accessory_name,
            )
            remesh_s = time.monotonic() - remesh_t0
            triangle_count = len(mesh_payload.get("indices", [])) // 3
            ss.mesh_cache[accessory_key] = {
                "mesh": mesh_payload,
            }
            changed_keys.append(accessory_key)
            remesh_metrics.append({
                "timberKey": accessory_key,
                "memberType": "accessory",
                "remesh_s": remesh_s,
                "csg_depth": csg_depth,
                "triangle_count": triangle_count,
            })

            meshes.append(mesh_payload)
            seen_keys.add(accessory_key)
        except Exception as exc:
            log_stderr(f"Warning: skipping geometry for accessory {type(accessory).__name__}: {exc}")

    removed_keys: List[str] = []
    for cached_key in list(ss.mesh_cache.keys()):
        if cached_key not in seen_keys:
            removed_keys.append(cached_key)
            del ss.mesh_cache[cached_key]

    # Footprints are flat polygons in the XY (z=0) ground plane. We send their corners (as
    # [x, y, 0] points) and let the viewer build a light fill + darkened edge.
    footprints_payload: List[FootprintWire] = []
    frame_footprints = list(getattr(frame, "footprints", None) or [])
    for index, footprint in enumerate(frame_footprints):
        try:
            corners = []
            for corner in footprint.corners:
                corners.append([float(corner[0]), float(corner[1]), 0.0])
            footprints_payload.append({
                "key": f"footprint#{index}",
                "corners": corners,
            })
        except Exception as exc:
            log_stderr(f"Warning: skipping footprint {index}: {exc}")

    return {
        "kind": "triangle-geometry",
        "meshes": meshes,
        "footprints": footprints_payload,
        "changedKeys": changed_keys,
        "removedKeys": removed_keys,
        "remeshMetrics": remesh_metrics,
        "counts": {
            "totalTimbers": len(meshes),
            "changedTimbers": len(changed_keys),
            "removedTimbers": len(removed_keys),
            "totalAccessories": len(accessories),
            "totalMembers": len(meshes),
        },
    }


def serialize_frame(frame: 'Frame') -> FrameSummaryWire:
    accessories = list(frame.accessories) if hasattr(frame, "accessories") and frame.accessories else []
    timbers = [serialize_cut_timber(cut_timber) for cut_timber in frame.cut_timbers]
    return {
        "name": frame.name if hasattr(frame, "name") else None,
        "timber_count": len(frame.cut_timbers),
        "accessories_count": len(accessories),
        "timbers": timbers,
        "accessories": [
            {
                "type": type(accessory).__name__,
            }
            for accessory in accessories
        ],
    }


def _assign_member_keys(frame: 'Frame') -> Tuple[List[TimberEntry], List[AccessoryEntry]]:
    """Compute the same memberKey scheme used by build_real_geometry.

    Returns (timber_entries, accessory_entries) with stable ordering.
    Each timber entry: {memberKey, kumikiEphemeralId, timber, cutTimber, displayName}.
    Each accessory entry: {memberKey, kumikiEphemeralId, accessory, displayName, type}.
    """
    timber_entries: List[TimberEntry] = []
    accessory_entries: List[AccessoryEntry] = []
    key_counts: Dict[str, int] = {}

    for cut_timber in frame.cut_timbers:
        timber = cut_timber.timber
        display = get_timber_display_name(timber)
        occurrence = key_counts.get(display, 0)
        key_counts[display] = occurrence + 1
        member_key = f"{display}#{occurrence}"
        timber_entries.append({
            "memberKey": member_key,
            "kumikiEphemeralId": int(timber.ticket.kumiki_id),
            "timber": timber,
            "cutTimber": cut_timber,
            "displayName": display,
        })

    accessories = list(frame.accessories) if hasattr(frame, "accessories") and frame.accessories else []
    for accessory in accessories:
        accessory_type = type(accessory).__name__
        key_base = f"accessory:{accessory_type}"
        occurrence = key_counts.get(key_base, 0)
        key_counts[key_base] = occurrence + 1
        member_key = f"{key_base}#{occurrence}"
        ticket = getattr(accessory, "ticket", None)
        kumiki_id = int(ticket.kumiki_id) if ticket is not None else 0
        ticket_name = getattr(ticket, "name", None) if ticket is not None else None
        display = ticket_name if ticket_name and ticket_name != "[no-name]" else f"{accessory_type} {occurrence + 1}"
        accessory_entries.append({
            "memberKey": member_key,
            "kumikiEphemeralId": kumiki_id,
            "accessory": accessory,
            "displayName": display,
            "type": accessory_type,
        })

    return timber_entries, accessory_entries


def _serialize_cutting_summary(cut_timber: 'CutTimber') -> List[CuttingSummaryWire]:
    from kumiki.viewer.picking import label_name
    cuts_meta: List[CuttingSummaryWire] = []
    cuts = list(getattr(cut_timber, "cuts", []) or [])
    for idx, cut in enumerate(cuts):
        label = label_name(cut)
        has_csg = getattr(cut, "negative_csg", None) is not None
        has_top = getattr(cut, "maybe_top_end_cut_distance_from_bottom", None) is not None
        has_bot = getattr(cut, "maybe_bottom_end_cut_distance_from_bottom", None) is not None
        if label and isinstance(label, str):
            display = label
        elif has_csg:
            display = f"cut {idx + 1}"
        elif has_top or has_bot:
            display = f"end-cut {idx + 1}"
        else:
            display = f"cut {idx + 1}"
        cuts_meta.append({
            "cutIndex": idx,
            "label": label,
            "hasCSG": has_csg,
            "hasEndCut": has_top or has_bot,
            "displayName": display,
        })
    return cuts_meta


def _timber_tag_kinds() -> List[Tuple[type, str]]:
    """The kumiki tag classes paired with their wire names, most specific first.

    Imported per call rather than at module scope: a reload purges and
    re-imports kumiki, which would leave a module-level class object matching
    nothing an isinstance check is ever handed.
    """
    from kumiki.ticket import GenericTag, MemberTag, SliceTag

    return [(SliceTag, "slice"), (MemberTag, "member"), (GenericTag, "generic")]


def _serialize_timber_tags(ticket: Optional['Ticket']) -> List[TagWire]:
    """Typed tags off a timber ticket, as {"kind", "name"} sorted by both.

    Only TimberTicket carries tags. A tag class with no wire name is skipped
    with a warning rather than raised on: this runs inside the per-timber
    geometry build, where an exception costs the whole timber's mesh. The
    kumiki-side test that every tag class is listed here is the loud half.
    """
    raw_tags = getattr(ticket, "tags", ())
    if not isinstance(raw_tags, (list, tuple)):
        return []

    kinds = _timber_tag_kinds()
    tags: List[TagWire] = []
    seen: set[Tuple[str, str]] = set()
    for tag in raw_tags:
        if isinstance(tag, str):
            kind, name = "generic", tag
        else:
            kind = next((wire for cls, wire in kinds if isinstance(tag, cls)), "")
            if not kind:
                log_stderr(f"Warning: skipping tag of unknown kind {type(tag).__name__}")
                continue
            name = getattr(tag, "name", "")
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or (kind, name) in seen:
            continue
        seen.add((kind, name))
        tags.append({"kind": kind, "name": name})
    tags.sort(key=lambda tag: (tag["kind"], tag["name"]))
    return tags


# --- drawings ---------------------------------------------------------------
#
# TESTING SCAFFOLDING. This builds one hard-coded drawing so the viewer's
# multi-viewport path has something to render before real drawing sets exist.
# Nothing in kumiki produces or stores it, no UI creates it, and it is expected
# to be deleted once drawings are authored for real.


# Camera frames, in kumiki world axes (Z up, +Y north, +X east). `look` is the
# direction the camera faces; the viewer derives the position back along it, so
# a frame is purely an orientation. right x up == -look, matching a camera that
# looks down its own -Z.
_DEBUG_DRAWING_VIEWS: List[Tuple[str, List[float], List[float], List[float]]] = [
    # id        right          up             look
    ("front", [1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]),
    ("top", [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]),
    ("right", [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [-1.0, 0.0, 0.0]),
]

# A3 landscape, in metres. Customizable per drawing in the real thing; this one
# is scaffolding, so it just picks a common sheet.
_DEBUG_DRAWING_PAGE: PageWire = {"width": 0.420, "height": 0.297}

def _placed_by_role(
    viewports: Sequence['Viewport'], ids: Mapping[str, 'ViewportId'], page: PageWire,
) -> Dict[str, 'PlacedViewport']:
    """Resolve a drawing's viewports against a page, keyed by what each is for.

    By role rather than by id, because the code below knows which view it is
    pointing and not where the tree put it -- which is the whole point of ids
    being positional. `ids` is the role-to-id map kumiki publishes beside each
    default layout, so moving a view within one changes that map and nothing
    here.
    """
    from kumiki.drawings.drawing import Page
    from kumiki.drawings.layout import resolve_viewports

    placed = {str(view.id): view
              for view in resolve_viewports(viewports, Page(page["width"], page["height"]))}
    return {role: placed[str(viewport_id)] for role, viewport_id in ids.items()}


def _viewport_spec(
    placed: 'PlacedViewport', *, locked: bool, projection: str, camera: CameraWire,
    orbit: Optional[OrbitWire] = None,
) -> ViewportWire:
    """The wire form of one placed viewport.

    The id is the tree's -- a position, "0.1.2" -- and the name is a label that
    nothing looks anything up by. See kumiki/drawings/drawing.py.
    """
    spec: ViewportWire = {"id": str(placed.id), "name": placed.label, "rect": list(placed.rect),
                          "locked": locked, "projection": projection, "camera": camera}
    if orbit is not None:
        spec["orbit"] = orbit
    return spec


def _viewport_aspect(rect: List[float], page: PageWire) -> float:
    """A viewport's aspect: its share of the sheet, times the sheet's own."""
    height = rect[3] * page["height"]
    return (rect[2] * page["width"]) / height if height > 0 else 1.0


def _dot(a: List[float], b: List[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def build_default_drawing_for_debugging(frame: 'Frame') -> DrawingWire:
    """A four-viewport scene over the whole frame: three elevations and a preview.

    Testing scaffolding -- see the note at the top of this section. The three
    orthographic viewports are locked, so the viewer holds their angle and only
    lets pan/zoom deltas ride on top; the perspective one is left free and is
    the same kind of viewport the default 3D scene uses.
    """
    from kumiki.drawings.cameras import orient_by_search, view_extent, world_bounds, world_box
    from kumiki.drawings.drawing import ELEVATION_IDS, elevation_viewports

    centre, half_size = world_bounds(frame.cut_timbers)
    placed = _placed_by_role(elevation_viewports(), ELEVATION_IDS, _DEBUG_DRAWING_PAGE)
    viewports: List[ViewportWire] = []
    for view_id, right, up, look in _DEBUG_DRAWING_VIEWS:
        rect = list(placed[view_id].rect)
        viewport = _viewport_spec(
            placed[view_id],
            locked=True,
            projection="orthographic",
            camera={
                "right": right,
                "up": up,
                "look": look,
                "target": centre,
                "extent": view_extent(half_size, right, up, _viewport_aspect(rect, _DEBUG_DRAWING_PAGE)),
            },
        )
        # Every timber, which is also what a scene defaults to; spelled out
        # because a real drawing is the interesting case and would not.
        viewport.update(members=None, ghostOthers=True, measurements=[])
        viewports.append(viewport)

    viewports.append(_preview_viewport(
        placed["preview"], world_box(centre, half_size), _DEBUG_DRAWING_PAGE,
        {"mode": "free"}, orient_by_search,
    ))

    return {
        "id": "debug-default-drawing",
        # The sheet these sit on. Rects above are fractions of it, so the four
        # views tile an A3 page rather than the window.
        "page": PageWire(**_DEBUG_DRAWING_PAGE),
        # A drawing shows no camera gizmos.
        "cameraControls": [],
        "viewports": viewports,
    }


# A3 landscape, in metres. Fixed for now; the page is meant to be the drawing's
# to choose, and this is where that choice will arrive from.
_SELECTION_DRAWING_PAGE: PageWire = {"width": 0.420, "height": 0.297}

SELECTION_DRAWING_ID = "selection-drawing"

#: The one reserved drawing that holds the 3D view's measurements.
#:
#: A drawing like any other, so the file merge, overrides, identity, saving and
#: the panel all apply to it without a second implementation. Reserved so that
#: nothing in python declares one. Its single viewport carries no camera: the 3D
#: view's belongs to the viewer and changes constantly, so there is nothing to
#: declare, and every measurement on it carries its own plane instead.
THREE_D_MEASUREMENTS_ID = "three-d-measurements"
THREE_D_MEASUREMENTS_VIEWPORT = "main"

# One timber gets its four long faces rolled out down the left of the sheet,
# with a live preview beside them -- the shop drawing for a single piece. Which
# face each view looks at, in the timber's own frame, going around it.
_LONG_FACE_VIEWS: List[Tuple[str, str, int]] = [
    # id       axis      sign
    ("front", "height", 1),
    ("right", "width", 1),
    ("back", "height", -1),
    ("left", "width", -1),
]



def _normalize(vec: List[float]) -> List[float]:
    length = math.sqrt(sum(component * component for component in vec))
    return [component / length for component in vec] if length > 0 else [0.0, 0.0, 1.0]


def _preview_viewport(
    placed: 'PlacedViewport',
    box: 'OrientedBox',
    page: PageWire,
    orbit: OrbitWire,
    orient: Callable[['OrientedBox', float], 'CameraFrame'],
) -> ViewportWire:
    """The live 3D view beside the elevations, pointed at what is being drawn.

    Left to itself the viewer builds a camera at the origin looking at nothing
    in particular, which for a piece standing away from the origin means an
    empty preview. `orient` is the strategy that picks the angle and `orbit`
    says how far it may be turned afterwards.
    """
    from kumiki.drawings.cameras import preview_extent

    rect = list(placed.rect)
    aspect = _viewport_aspect(rect, page)
    frame = orient(box, aspect)
    centre = box.centre
    return _viewport_spec(
        placed,
        locked=False,
        projection="perspective",
        orbit=orbit,
        camera={
            **frame.as_dict(),
            "target": centre,
            "extent": preview_extent(box, frame, aspect),
        },
    )


def _long_face_viewports(entry: TimberEntry, page: PageWire,
                         placed_by_role: Dict[str, 'PlacedViewport']) -> List[ViewportWire]:
    """The four long sides of one timber, stacked, each square-on to its face."""
    timber = entry["timber"]
    along = _vector3_to_floats(timber.get_length_direction_global())
    axes = {
        "width": _vector3_to_floats(timber.get_width_direction_global()),
        "height": _vector3_to_floats(timber.get_height_direction_global()),
    }
    from kumiki.drawings.cameras import camera_looking_at_face, view_extent, world_bounds

    centre, half_size = world_bounds([entry["cutTimber"]])

    viewports: List[ViewportWire] = []
    for view_id, axis_name, sign in _LONG_FACE_VIEWS:
        normal = [component * sign for component in axes[axis_name]]
        frame = camera_looking_at_face(normal, along)
        placed = placed_by_role[view_id]
        rect = list(placed.rect)
        viewports.append(_viewport_spec(
            placed,
            locked=True,
            projection="orthographic",
            camera={
                **frame.as_dict(),
                "target": centre,
                "extent": view_extent(half_size, frame.right, frame.up, _viewport_aspect(rect, page)),
            },
        ))
    return viewports


def _world_elevation_viewports(
    entries: List[TimberEntry], page: PageWire, placed_by_role: Dict[str, 'PlacedViewport'],
) -> List[ViewportWire]:
    """Front, top and right elevations in world axes, for a group of members."""
    from kumiki.drawings.cameras import view_extent, world_bounds

    centre, half_size = world_bounds([entry["cutTimber"] for entry in entries])
    viewports: List[ViewportWire] = []
    for view_id, right, up, look in _DEBUG_DRAWING_VIEWS:
        placed = placed_by_role[view_id]
        rect = list(placed.rect)
        viewports.append(_viewport_spec(
            placed,
            locked=True,
            projection="orthographic",
            camera={
                "right": right,
                "up": up,
                "look": look,
                "target": centre,
                "extent": view_extent(half_size, right, up, _viewport_aspect(rect, page)),
            },
        ))
    return viewports


def _unique_drawing_id(base: str, taken: set) -> str:
    """A drawing id nothing else is using. Drawing the same piece twice is fine."""
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def _selection_drawing_name(entries: List[TimberEntry], total: int) -> str:
    """What to call a drawing nobody has named.

    One piece is called after the piece, which is what anyone would call it.
    Several are counted, since listing them would not fit and would not help.
    """
    if len(entries) == 1:
        return entries[0]["displayName"]
    if not entries:
        return f"whole frame ({total})"
    return f"{len(entries)} members"


def create_drawing_from_selection(frame: 'Frame', member_keys: List[str]) -> DrawingWire:
    """A drawing of the selected members, on a sheet.

    One timber is drawn the way a piece is drawn for the shop: its four long
    faces rolled out down the sheet with a live preview beside them, each view
    square-on to a face and with the length running across the page. Several
    members have no single piece whose faces the drawing could be about, so they
    get world elevations instead.

    The drawing names its members. The scene still holds every timber -- the
    rest are ghosted, present for context and not part of what is drawn.
    """
    from kumiki.drawings.cameras import orient_by_search, orient_from_box, timber_box, world_bounds, world_box

    page = PageWire(**_SELECTION_DRAWING_PAGE)
    timber_entries, _ = _assign_member_keys(frame)
    wanted = list(member_keys or [])
    by_key = {entry["memberKey"]: entry for entry in timber_entries}
    entries = [by_key[key] for key in wanted if key in by_key]

    drawn = entries or timber_entries
    centre, half_size = world_bounds([entry["cutTimber"] for entry in drawn])

    if len(entries) == 1:
        from kumiki.drawings.drawing import SHOP_DRAWING_IDS, shop_drawing_viewports
        viewports = shop_drawing_viewports()
        placed = _placed_by_role(viewports, SHOP_DRAWING_IDS, page)
        viewports = _long_face_viewports(entries[0], page, placed)
        # One piece: oriented from its own box rather than the world box it
        # happens to occupy, and turned about its own length, so it can be
        # looked at from every side without ever being tumbled out of the
        # attitude it is drawn in.
        preview_box = timber_box(entries[0]["cutTimber"])
        orient = orient_from_box
        orbit = OrbitWire(mode="axis", axis=list(preview_box.axes[0]))
    else:
        # No selection is treated as the whole frame, so asking for a drawing
        # before selecting anything gives you something rather than nothing.
        from kumiki.drawings.drawing import ELEVATION_IDS, elevation_viewports
        viewports = elevation_viewports()
        placed = _placed_by_role(viewports, ELEVATION_IDS, page)
        viewports = _world_elevation_viewports(entries or timber_entries, page, placed)
        # Several pieces have no length of their own to speak of, so the angle
        # is searched for -- and kept upright, since which way is up is part of
        # what a preview of an assembly is telling you.
        preview_box = world_box(centre, half_size)
        orient = orient_by_search
        orbit = OrbitWire(mode="free")

    members = [entry["memberKey"] for entry in entries]
    for viewport in viewports:
        viewport["members"] = members or None
        viewport["ghostOthers"] = True
        viewport["measurements"] = []
    viewports.append(_preview_viewport(placed["preview"], preview_box, page, orbit, orient))

    return {
        "id": SELECTION_DRAWING_ID,
        "name": _selection_drawing_name(entries, len(timber_entries)),
        "members": members,
        "page": page,
        # A drawing shows no camera gizmos.
        "cameraControls": [],
        "viewports": viewports,
    }


# --- where drawings come from ------------------------------------------------
#
# Two sources. The frame asks for drawings in code (Frame.drawings), and a
# drawings file may override those and add its own. Which of the two a drawing
# came from is carried on it, because it is the first thing you want to know
# when one looks wrong: whether to edit the python or the file.

ORIGIN_CODE = "code"
ORIGIN_OVERRIDDEN = "overridden"
ORIGIN_FILE = "file"
# A code measurement the file has deleted. Still listed -- greyed, to be put back -- but not drawn.
ORIGIN_DELETED = "deleted"


# --- measurements -----------------------------------------------------------
#
# Two tiers: from the file, and not. A file measurement overrides the one
# beneath it with the same identity, which is the whole rule. It still produces
# the three states worth marking -- untouched code, code the file has overridden,
# and one the file introduced.

MEASURE_SUPPRESSED: Final = "suppressed"

# Warned about once per parse rather than per duplicate: a hand-edited file with
# a repeated entry would otherwise fill the log with the same sentence.
_duplicate_warning_given = False


def _feature_path_identity(anchor: Optional[AnchorWire]) -> Tuple[str, Tuple[str, ...], str, str]:
    """A comparable form of a feature reference as it travels on the wire.

    A tuple rather than a joined string, since a ticket path may itself contain
    a separator and two different references must never collapse into one.
    """
    # Imported per call: a reload purges kumiki's modules, so a reference held
    # from before would be to a class that no longer exists.
    from kumiki.identity import ResolvedTimberPath

    # Through the path types, so a wire form and the object it came from give
    # the same answer -- including a timber written by hand without an
    # occurrence, and an edge's two parents whichever way round they were
    # written.
    path = deserialize_feature_path(anchor)
    if path is None:
        return ("", (), "", "")
    return path.identity()


def _anchor_sort_key(anchor: Optional[AnchorWire]) -> Tuple[str, ...]:
    """Where one anchor falls in the order a pair is written in.

    On the path, not on its identity: identity nests differently per shape and
    will not order against itself. A missing anchor sorts before any real one.
    """
    path = deserialize_feature_path(anchor)
    return ("",) if path is None else path.sort_key


def _measure_pair_identity(measure: MeasureWire) -> Tuple[Any, Any]:
    """Just the two features of a measurement, without what is measured between."""
    first, second = sorted((measure.get("a"), measure.get("b")), key=_anchor_sort_key)
    return (_feature_path_identity(first), _feature_path_identity(second))


def _measure_identity(measure: MeasureWire) -> Tuple[Any, Any, Any, str]:
    """What makes a measurement itself, within the viewport it is drawn in.

    The anchors unordered, since measuring A to B is measuring B to A. Then the
    kind, because two kinds between one pair are two dimensions and both should
    show. Then an id, for the same pair measured twice the same way. Scoped to
    the viewport because that is where a measurement lives: the same anchors in
    the plan view are a different dimension with a different number, not this
    one seen from elsewhere.

    The same tuple Measure.identity builds, because the two are compared
    against each other -- a file measurement overrides a code one by matching
    it. A kind is normalized through MeasurementKind first, so one written
    under an older name matches the same kind written under the new one.
    """
    from kumiki.drawings.drawing import Measure, MeasurementKind

    first, second = _measure_pair_identity(measure)
    kind = measure.get("kind")
    return (
        first, second,
        Measure.kind_identity(MeasurementKind.from_wire(kind) if kind else None),
        str(measure.get("measureId") or ""),
    )


def serialize_feature_path(path: 'FeaturePath') -> AnchorWire:
    """A feature reference as the viewer and the file hold it. See kumiki.csg.feature_paths."""
    from kumiki.csg.feature_paths import serialize_feature_path as serialize
    return cast(AnchorWire, serialize(path))


def deserialize_feature_path(source: Any) -> Optional['FeaturePath']:
    """The reference a wire form names, or None. See kumiki.csg.feature_paths."""
    from kumiki.csg.feature_paths import deserialize_feature_path as deserialize
    return deserialize(source)


# --- the plane a measurement is taken on -------------------------------------
#
# A measurement's own, not the viewport's. See .claude/plans/measurement-spec.md: a
# drawing viewport is locked so either would do, but the 3D view's camera
# orbits, and a measurement evaluated against it would read a different number
# from one moment to the next.

def _derivation_wire(
    local_csg: 'CutCSG', feature_hits: List['OwnedFeatureHit'], feature: Optional['CSGFeature'],
) -> Optional[DerivationWire]:
    """For a derived feature (picking.derivation): the path to the node owning it, and each parent's."""
    from kumiki.viewer.picking import derivation

    found = derivation(local_csg, feature_hits, feature)
    if found is None:
        return None
    return {"ownerPath": found.owner_path,
            "parents": [{"path": path, "name": name} for path, name in found.parents]}


def _sight_blocker(
    ss: 'SlotState', own: 'CutTimber', own_root: 'CutCSG', payload: PickRequest, direction: 'Float3',
) -> Callable[['Float3'], bool]:
    """`blocked(place)` (picking.sight_blocker): whether a drawn member's material hides *place*, in
    *own*'s local space, from the camera. The members that can be in the way are the request's
    `drawnMembers` (every member when it is None), *own* among them."""
    from kumiki.viewer.picking import sight_blocker

    drawn = payload.get("drawnMembers")
    occluders = [(own_root, own.timber.transform)] + [
        (cast('CutCSG', entry["local_csg"]), entry["cut_timber"].timber.transform)
        for key, entry in ss.mesh_cache.items()
        if entry.get("cut_timber") is not None and entry.get("cut_timber") is not own
        and entry.get("local_csg") is not None and (drawn is None or key in drawn)]
    return sight_blocker(own.timber.transform, occluders, direction)


def _pick_verdict(
    state: RunnerState, located_pick: Optional['LocatedPick'], timber: 'PerfectTimberWithin',
    payload: PickRequest, slot_state: Optional[SlotState],
) -> Optional[VerdictWire]:
    """What a measurement to this pick would be, as one object.

    None when no measurement is being made -- an ordinary hover, which is a
    different thing from a pair that admits nothing, and both are read.

    Otherwise:

      kinds    what the pair admits, best first. Empty means the click refuses,
               and the hover paints it red. A kind that would come to nothing
               is not admitted.
      plane    the plane it would be taken on.
      anchors  where it would attach, at both ends, through the same rules that
               place a written measurement -- so what is drawn while deciding is
               where it lands once decided.
      reason   why there is nothing, when there is nothing.

    Asked once here rather than three times in the viewer. A colour, a preview
    and a refusal derived separately will eventually disagree, and the
    disagreement is invisible until someone clicks.
    """
    from kumiki.drawings.drawing import ViewAxes
    from kumiki.drawings.measuring import pick_verdict, world_geometry

    held_geometry, look = payload.get("heldGeometry"), payload.get("look")
    if not held_geometry or not look:
        return None
    if located_pick is None:
        return {"kinds": [], "plane": None, "anchors": None,
                "reason": "nothing-under-pointer"}
    geometry = world_geometry(_handle_of(located_pick[0], located_pick[1], timber))
    # The plane only for something measurable: a cylinder's barrel is good to select, and nothing
    # to measure to.
    plane = _plane_for_pick(located_pick, timber, payload) if geometry is not None else None
    verdict = pick_verdict(_geometry_from_wire(held_geometry), geometry, plane, look, _pick_space(payload),
                           ViewAxes.from_wire(payload))
    plane_wire = cast(PlaneWire, plane.as_wire()) if plane is not None else None
    if not verdict.kinds:
        refused: VerdictWire = {"kinds": [], "plane": plane_wire, "anchors": None, "reason": verdict.reason}
        if verdict.reason == "degenerate":
            refused["angle"] = None
        return refused
    # Where it would sit, by the rules that place it once written, so the preview IS the
    # measurement rather than a likeness of one.
    placement = _pick_placement(state, located_pick, timber, payload, slot_state)
    return {
        "kinds": [cast(MeasureKindWire, kind.as_wire()) for kind in verdict.kinds],
        "plane": plane_wire,
        **placement,
        "reason": None,
    }


def _pick_space(payload: PickRequest) -> 'MeasurementSpace':
    """Which space a pick is judged in: the sheet's, or the model's.

    The viewer says, because it is the one that knows which view the pointer is
    in. A drawing's viewport has a declared camera and projects onto its sheet;
    the 3D view projects nothing, its camera being the reader's.
    """
    from kumiki.drawings.drawing import MeasurementSpace

    named = (payload or {}).get("space")
    return (MeasurementSpace.THREE_D
            if named == MeasurementSpace.THREE_D.value
            else MeasurementSpace.PROJECTED)


def _pick_placement(
    state: RunnerState, located_pick: Optional['LocatedPick'], timber: 'PerfectTimberWithin', payload: PickRequest,
    slot_state: Optional[SlotState],
) -> PickPlacementWire:
    """Where a measurement to this pick would sit: its anchors, or its corner.

    Both from the same pair of spans and the same rules that place a written
    measurement, so what is drawn while deciding is where it lands once decided.
    A distance gets anchors and an angle gets a vertex and two rays; neither
    gets the other, and a pair that admits nothing gets nothing.

    The held end is resolved from its REFERENCE rather than sent along as
    geometry, so this goes through exactly the code a written measurement goes
    through -- the alternative is a second way of working out the same answer,
    and the two drifted: a half-made measurement was drawn at each feature's own
    middle while the finished one went to the middle of their overlap.
    """
    from kumiki.drawings.drawing import MeasurementSpace, ViewAxes
    from kumiki.drawings.feature_span import feature_span
    from kumiki.drawings.measuring import place_pair, world_geometry

    empty = PickPlacementWire(anchors=None, angle=None, settled=None)
    held = payload.get("heldReference")
    look = payload.get("look")
    if not held or not look or located_pick is None:
        return empty
    ss = slot_state if slot_state is not None else state._active
    frame = getattr(ss, "frame", None)
    if frame is None:
        return empty

    in_three_d = _pick_space(payload) is MeasurementSpace.THREE_D
    plane = _plane_for_pick(located_pick, timber, payload)
    normal = list(plane.normal) if plane is not None else look
    placed = _resolve_anchor_placed(frame, held, normal, in_three_d)
    if placed is None or placed[1] is None:
        return empty
    handle = _handle_of(located_pick[0], located_pick[1], timber)
    picked_span = feature_span(handle, _root_csg_of(ss, payload.get("memberKey")), normal, in_three_d)
    if picked_span is None:
        return empty
    # The same answer a written measurement travels with, so the preview shows the number the
    # finished one will carry rather than a second derivation of it.
    placement = place_pair(_geometry_from_wire(placed[0].get("geometry")), world_geometry(handle), placed[1],
                           picked_span, None, normal, ViewAxes.from_wire({**payload, "look": look}), in_three_d)
    if not placement.admitted:
        return empty
    settled = _settled_wire(placement.settled)
    if placement.anchors is not None:
        at_held, at_picked = placement.anchors
        return {"anchors": {"a": list(at_held), "b": list(at_picked)}, "angle": None, "settled": settled}
    return {"anchors": None, "angle": placement.rays.as_wire() if placement.rays is not None else None,
            "settled": settled}


def _root_csg_of(ss: SlotState, member_key: Optional[str]) -> Optional['CutCSG']:
    cached = (getattr(ss, "mesh_cache", None) or {}).get(member_key) or {}
    return cached.get("local_csg")


def _plane_for_pick(
    located_pick: Optional['LocatedPick'], timber: 'PerfectTimberWithin', payload: PickRequest,
) -> Optional['MeasurementPlane']:
    """The plane a measurement to this pick would be taken on (measuring.measurement_plane), or None.

    None unless something is held and the viewer said which way it is looking:
    a plane needs both ends and a camera, and a first pick has neither.
    """
    from kumiki.drawings.drawing import MeasurementSpace
    from kumiki.drawings.measuring import feature_anchor, measurement_plane, world_geometry

    held_geometry = payload.get("heldGeometry")
    look = payload.get("look")
    if located_pick is None or not held_geometry or not look:
        return None
    handle = _handle_of(located_pick[0], located_pick[1], timber)
    geometry = world_geometry(handle)
    if geometry is None:
        return None
    return measurement_plane(
        _geometry_from_wire(held_geometry), geometry, payload.get("heldAt"), feature_anchor(handle), look,
        in_view_plane=_pick_space(payload) is MeasurementSpace.PROJECTED)


def _serialize_code_measure(measure: Any, frame: 'Frame') -> Optional[MeasureWire]:
    anchors = measure.wire_anchors(frame)
    if anchors is None:
        log_stderr("Warning: a measurement's feature is not in this frame, so it is left out.")
        return None
    first, second, placement = anchors
    plane = getattr(measure, "plane", None)
    return {
        "a": serialize_feature_path(first),
        "b": serialize_feature_path(second),
        "measureId": str(measure.measure_id) if measure.measure_id else None,
        # Neither is part of identity: asking for a different kind, or moving
        # the line, is not measuring something else. They travel so that
        # overriding one in the file starts from what the code asked for.
        #
        # Structured rather than named: `angle` composes for a 3D angle and
        # is also what every measurement written before spaces called a
        # projected one, so a bare name cannot carry both.
        "kind": measure.kind.as_wire() if getattr(measure, "kind", None) else None,
        "placement": {"offset": placement.offset} if placement is not None else None,
        # Likewise not identity. Absent on the wire means "take the viewport's
        # plane", which is what an orthographic viewport's measurements may
        # always mean -- FromViewport.as_wire() is how the python side says it.
        "plane": plane.as_wire() if plane is not None else None,
        "origin": ORIGIN_CODE,
    }


def merge_measurements(
    code_measures: List[MeasureWire],
    file_measures: List[MeasureWire],
) -> List[MeasureWire]:
    """The measurements of one drawing, from both tiers.

    A file entry with the same identity as a code one replaces it and is marked
    as overriding; one with an identity nothing else has is the file's own. An
    entry marked suppressed deletes the code measurement instead of replacing
    it, which is how a measurement the code asks for and nobody wants goes
    away without the code being changed. It is kept, marked deleted, so it can
    be listed and put back.

    A repeated identity within a tier is a mistake rather than a case to
    resolve, so the later one wins. Refusing the file outright would cost
    someone their drawings over a stray duplicate, which is the same trade the
    file parser already makes.
    """
    global _duplicate_warning_given
    from_file: Dict[Tuple[Any, Any, Any, str], MeasureWire] = {}
    for measure in file_measures:
        identity = _measure_identity(measure)
        if identity in from_file and not _duplicate_warning_given:
            log_stderr(
                "Warning: two measurements share an identity; the later one wins. "
                "Give one of them a measureId to tell them apart."
            )
            _duplicate_warning_given = True
        from_file[identity] = measure

    from kumiki.drawings.drawing import MeasurementSource, does_override_identities

    merged: List[MeasureWire] = []
    used = set()
    for measure in code_measures:
        identity = _measure_identity(measure)
        # Through does_override rather than a bare lookup, so the rule about
        # what replaces what lives in one place. For these two tiers it is a
        # full match, which is what the dict already did -- but it is the rule
        # that says so, not this loop.
        override = None
        for candidate_identity, candidate in from_file.items():
            if does_override_identities(
                candidate_identity, _measure_pair_identity(candidate),
                MeasurementSource.FILE_OVERRIDE,
                identity, _measure_pair_identity(measure),
                MeasurementSource.PYTHON_CODED,
            ):
                override, identity = candidate, candidate_identity
                break
        if override is None:
            merged.append({**measure, "origin": ORIGIN_CODE})
            continue
        used.add(identity)
        if override.get(MEASURE_SUPPRESSED) is True:
            merged.append({**measure, MEASURE_SUPPRESSED: True, "origin": ORIGIN_DELETED})
            continue
        merged.append({**measure, **override, "origin": ORIGIN_OVERRIDDEN})

    for identity, measure in from_file.items():
        if identity in used or measure.get(MEASURE_SUPPRESSED) is True:
            continue
        merged.append({**measure, "origin": ORIGIN_FILE})

    return merged


def _file_measurements_by_viewport(entry: Optional[DrawingWire]) -> Dict[str, List[MeasureWire]]:
    """A file drawing's measurements, off the viewports they hang from."""
    by_viewport: Dict[str, List[MeasureWire]] = {}
    for viewport in (entry or {}).get("viewports") or []:
        if isinstance(viewport, dict) and isinstance(viewport.get("id"), str):
            by_viewport[viewport["id"]] = list(viewport.get("measurements") or [])
    return by_viewport


def _measurements_by_viewport(
    declared: Any,
    override: Optional[DrawingWire],
    frame: 'Frame',
) -> Dict[str, List[MeasureWire]]:
    """A drawing's measurements, merged tier over tier, under each viewport.

    Both tiers hang them off viewports, and the merge happens within one: the
    same anchors in another viewport are a different dimension, not this one
    again.
    """
    # Through measurements_by_viewport, so a measurement written ON a viewport
    # and one keyed by id both reach the merge the same way.
    code_by_viewport = declared.measurements_by_viewport() if declared is not None else {}
    file_by_viewport = _file_measurements_by_viewport(override)
    merged: Dict[str, List[MeasureWire]] = {}
    for viewport in list(code_by_viewport) + [v for v in file_by_viewport if v not in code_by_viewport]:
        merged[viewport] = merge_measurements(
            [wire for wire in (_serialize_code_measure(m, frame) for m in code_by_viewport.get(viewport, ()))
             if wire is not None],
            list(file_by_viewport.get(viewport) or []),
        )
    return merged


def _drawings_file_path(example_path: Path) -> Path:
    """Where a frame's drawings file lives.

    Under .kigumi rather than beside the source: writes there are already known
    not to wake the file watcher, since refresh stats land there on every
    refresh.
    """
    return example_path.parent / ".kigumi" / "drawings" / f"{example_path.stem}.json"


# What a file drawing names when it is overriding one the code declares. Kept
# separate from its own id so that an override is always recognisably an
# override: delete the python drawing and what is left is plainly a dangling
# entry, rather than something that quietly becomes a drawing in its own right.
OVERRIDES_KEY: Final = "overridesPythonDrawing"


def _read_drawings_file(path: Path) -> List[DrawingWire]:
    """The drawings file, in order, or nothing. A broken file is reported, not fatal.

    Losing a viewer because a hand-edited file has a comma out of place would be
    a poor trade for strictness, and the file is meant to be hand-edited.
    """
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log_stderr(f"Warning: could not read {path}: {exc}")
        return []
    if not isinstance(loaded, dict):
        return []
    drawings = loaded.get("drawings")
    if not isinstance(drawings, list):
        return []
    return [
        drawing for drawing in drawings
        if isinstance(drawing, dict) and isinstance(drawing.get("id"), str)
    ]


def _member_keys_for_timbers(frame: 'Frame', timbers: List[Any]) -> List[str]:
    """The member keys of the timbers a code drawing holds. Frame has checked they are its own."""
    keys: List[str] = []
    for timber in timbers or []:
        path = frame.resolved_timber_path_of(timber)
        if path is not None:
            keys.append(str(path))
    return keys


def _drawing_from_code(frame: 'Frame', declared: Any) -> DrawingWire:
    """Turn what the frame asked for into a scene the viewer can render."""
    member_keys = _member_keys_for_timbers(frame, list(declared.timbers))
    scene = create_drawing_from_selection(frame, member_keys)
    scene["id"] = str(declared.drawing_id)
    scene["name"] = declared.name
    scene["members"] = member_keys
    return scene


def add_measurement(
    frame: 'Frame',
    example_path: Optional[Path],
    pending: List[DrawingWire],
    drawing_id: str,
    viewport_id: str,
    measure: MeasureWire,
) -> DrawingWire:
    """Put a measurement on a viewport, and say which entry now holds it.

    The file is where a measurement made in the viewer lives, even when the
    drawing it is on came from code: an override contributes measurements to a
    drawing the code still lays out. So this finds or makes that override rather
    than touching the code drawing, which it could not change anyway.

    A pair already measured in this viewport is replaced rather than added
    beside. Two dimensions between the same two features, drawn on top of each
    other, is not something anyone means to ask for -- and the second click of a
    measurement is often a correction of the first.
    """
    holder, measures = _measurement_slot(
        frame, example_path, pending, drawing_id, viewport_id)
    pair = _measure_pair_identity(measure)
    measures[:] = [m for m in measures if _measure_pair_identity(m) != pair] + [measure]
    return holder


def _check_plane_matches_view(
    scenes: Sequence[DrawingWire], drawing_id: str, viewport_id: str, plane: Any,
) -> None:
    """Refuse to write a measurement whose plane an orthographic viewport cannot show.

    Ours to get right, not the reader's: a measurement is made in one view, on that view's plane
    (see _measurement_plane), so a mismatch here is a bug -- and written, it would only come back
    refused as "plane does not match this view". A file saying so is another matter; the viewer
    refuses that when it reads it.
    """
    normal = (plane or {}).get("normal") if isinstance(plane, Mapping) else None
    if not normal or len(normal) != 3:
        return
    drawing = next((one for one in scenes if one.get("id") == drawing_id), None)
    viewport = next((one for one in (drawing or {}).get("viewports", []) if one.get("id") == viewport_id), None)
    camera = (viewport or {}).get("camera") or {}
    look = camera.get("look")
    if (viewport or {}).get("projection") != "orthographic" or not look or len(look) != 3:
        return
    unit_normal, unit_look = _normalize([float(v) for v in normal]), _normalize([float(v) for v in look])
    if abs(abs(_dot(unit_normal, unit_look)) - 1.0) > 1e-6:
        raise ValueError(
            f"A measurement in viewport {viewport_id!r} of {drawing_id!r} has to lie on that view's plane "
            f"(normal {unit_look}), not on one with normal {unit_normal}")


def _requested_measure(payload: Dict[str, Any], *, whole: bool = False) -> MeasureWire:
    """The measurement a viewer request names: its ends and id, and with `whole` the rest."""
    request = cast(MeasurementRequest, payload)
    a, b = request.get("a"), request.get("b")
    if a is None or b is None:
        raise ValueError("A measurement request needs both payload.a and payload.b")
    if not whole:
        return MeasureWire(a=a, b=b, measureId=request.get("measureId"))
    return MeasureWire(a=a, b=b, kind=request.get("kind"), measureId=request.get("measureId"),
                       plane=request.get("plane"), placement=request.get("placement"))


def _viewer_measure_identity(measure: MeasureWire) -> Tuple[Any, str]:
    """Which measurement an edit from the viewer means.

    The two features, plus the id that lets one pair be measured twice. NOT the
    kind: changing what a dimension measures between the same two features is
    editing that dimension, not putting another one there.
    """
    return (_measure_pair_identity(measure), str(measure.get("measureId") or ""))


def _measurement_slot(
    frame: 'Frame',
    example_path: Optional[Path],
    pending: List[DrawingWire],
    drawing_id: str,
    viewport_id: str,
) -> Tuple[DrawingWire, List[MeasureWire]]:
    """The file entry that holds a viewport's measurements, and that list.

    The list is returned to be edited in place, and the holder is on `pending`
    by the time this returns, so every caller writes the same way and none of
    them has to remember the second half.
    """
    existing = collect_drawings(frame, example_path, pending)
    target = next((d for d in existing if d["id"] == drawing_id), None)
    if target is None and drawing_id == THREE_D_MEASUREMENTS_ID:
        # The reserved drawing is made when the first measurement needs it
        # rather than always being there: an empty one in every listing is a
        # drawing nobody asked for. It is not laid out on a sheet and is never
        # entered -- what it holds are measurements that belong to the model
        # rather than to any drawing of it, so its viewport declares no camera
        # and each measurement carries its own plane.
        target = DrawingWire(
            id=THREE_D_MEASUREMENTS_ID,
            name=THREE_D_MEASUREMENTS_ID,
            origin=ORIGIN_FILE,
            page=None,
            cameraControls=[],
            viewports=[ViewportWire(id=THREE_D_MEASUREMENTS_VIEWPORT, measurements=[])],
        )
        pending.append(target)
        existing = existing + [target]
    if target is None:
        raise ValueError(f"No drawing {drawing_id!r} to measure on")

    holder = _measurement_holder(existing, pending, target)
    viewport = next(
        (v for v in holder.setdefault("viewports", []) if v.get("id") == viewport_id), None)
    if viewport is None:
        viewport = ViewportWire(id=viewport_id, measurements=[])
        holder["viewports"].append(viewport)
    if holder not in pending:
        pending.append(holder)
    return holder, viewport.setdefault("measurements", [])


def update_measurement(
    frame: 'Frame',
    example_path: Optional[Path],
    pending: List[DrawingWire],
    drawing_id: str,
    viewport_id: str,
    measure: MeasureWire,
    changes: MeasureWire,
) -> DrawingWire:
    """Change a measurement without replacing it: its kind, its plane, where it sits.

    Not add_measurement with different fields. An add replaces whatever measured
    that pair, so a viewer that changed a kind by adding could not tell the undo
    stack whether a dimension had been edited or made -- and dragging one would
    push a create.

    A measurement the code declares has no entry here to change, so one is made
    carrying the anchors, its kind and the change. That is what an override is for:
    the code keeps asking for the measurement, and the file says what to do with it.
    The kind is what makes it an override -- one matches on kind too -- so without
    it, moving a code measurement that names its kind left the code's in place and
    drew the moved one beside it.
    """
    holder, measures = _measurement_slot(
        frame, example_path, pending, drawing_id, viewport_id)
    identity = _viewer_measure_identity(measure)
    for entry in measures:
        if _viewer_measure_identity(entry) == identity:
            entry.update(changes)
            return holder
    current = _merged_measurement(frame, example_path, pending, drawing_id, viewport_id, measure)
    kind = current.get("kind") if current is not None else None
    measures.append({**measure, "kind": kind, **changes} if kind is not None else {**measure, **changes})
    return holder


def _merged_measurement(
    frame: 'Frame', example_path: Optional[Path], pending: List[DrawingWire],
    drawing_id: str, viewport_id: str, measure: MeasureWire,
) -> Optional[MeasureWire]:
    """The measurement as the viewer sees it, tiers merged, or None if it is not there."""
    identity = _viewer_measure_identity(measure)
    return next((
        m
        for drawing in collect_drawings(frame, example_path, pending)
        if drawing["id"] == drawing_id
        for viewport in drawing.get("viewports") or []
        if viewport.get("id") == viewport_id
        for m in viewport.get("measurements") or []
        if _viewer_measure_identity(m) == identity
    ), None)


def delete_measurement(
    frame: 'Frame',
    example_path: Optional[Path],
    pending: List[DrawingWire],
    drawing_id: str,
    viewport_id: str,
    measure: MeasureWire,
) -> Optional[DrawingWire]:
    """Take a measurement off a viewport, according to where it comes from.

    - One the file owns is removed.
    - One the code asks for and the file has changed loses the change: the
      code's own comes back.
    - One the code asks for, untouched, is marked deleted in the file. The code
      still asks for it, so it is listed greyed and can be put back
      (restore_measurement).
    - One already deleted is left as it is.

    Returns the file entry that now holds it, or None if nothing changed.
    """
    current = _merged_measurement(frame, example_path, pending, drawing_id, viewport_id, measure)
    if current is None or current.get("origin") == ORIGIN_DELETED:
        return None
    holder, measures = _measurement_slot(
        frame, example_path, pending, drawing_id, viewport_id)
    identity = _viewer_measure_identity(measure)
    if current.get("origin") == ORIGIN_CODE:
        # The kind goes with it: an override matches the code measurement on it.
        measures.append({**measure, "kind": current.get("kind"), MEASURE_SUPPRESSED: True})
        return holder
    measures[:] = [m for m in measures if _viewer_measure_identity(m) != identity]
    return holder


def restore_measurement(
    frame: 'Frame',
    example_path: Optional[Path],
    pending: List[DrawingWire],
    drawing_id: str,
    viewport_id: str,
    measure: MeasureWire,
) -> Optional[DrawingWire]:
    """Put back a code measurement the file deleted. Returns None if it was not deleted."""
    current = _merged_measurement(frame, example_path, pending, drawing_id, viewport_id, measure)
    if current is None or current.get("origin") != ORIGIN_DELETED:
        return None
    holder, measures = _measurement_slot(
        frame, example_path, pending, drawing_id, viewport_id)
    identity = _viewer_measure_identity(measure)
    measures[:] = [m for m in measures
                   if not (_viewer_measure_identity(m) == identity and m.get(MEASURE_SUPPRESSED) is True)]
    return holder


def _measurement_holder(
    existing: List[DrawingWire],
    pending: List[DrawingWire],
    target: DrawingWire,
) -> DrawingWire:
    """The file entry a measurement on *target* belongs in, made if need be.

    A drawing of the file's own holds its own measurements. One from the code
    cannot, so it gets an override -- named after the drawing it overrides, so
    that deleting the code drawing leaves something plainly dangling rather than
    something that has quietly become a drawing in its own right.
    """
    if target.get("origin") == ORIGIN_FILE:
        held = next((d for d in pending if d["id"] == target["id"]), None)
        return held if held is not None else _savable_drawing(target)

    overriding = target.get("overriddenBy")
    if overriding:
        held = next((d for d in pending if d["id"] == overriding), None)
        if held is not None:
            return held
        found = next((d for d in existing if d["id"] == overriding), None)
        if found is not None:
            return _savable_drawing(found)

    return {
        "id": f"{target['id']}-measurements",
        "name": target.get("name", target["id"]),
        OVERRIDES_KEY: target["id"],
        "viewports": [],
    }


def collect_drawings(
    frame: 'Frame',
    example_path: Optional[Path],
    pending: Optional[List[DrawingWire]] = None,
) -> List[DrawingWire]:
    """Every drawing for a frame: from the code, from the file, and unsaved.

    The file mirrors the code -- drawings holding viewports holding measurements
    -- and a file drawing says outright which code drawing it overrides, if any.
    So an override contributes measurements to a drawing the code still lays out,
    a file drawing that overrides nothing is a drawing in its own right, and one
    naming a code drawing that has gone is plainly a dangling override rather
    than something that has quietly become its own.

    `dirty` says a drawing is not in the file yet. It is worked out here rather
    than left for the viewer to infer, so there is one answer to it.
    """
    saved = _read_drawings_file(_drawings_file_path(example_path)) if example_path else []
    # Unsaved entries stand in for saved ones of the same id, and are merged in
    # here rather than appended at the end. An override contributes measurements
    # to a drawing the code lays out, so a pending override has to go through
    # the same merge -- appended, it would replace the code drawing instead and
    # take the layout with it.
    pending_by_id = {entry["id"]: DrawingWire(**entry) for entry in (pending or []) if entry.get("id")}
    from_file = [pending_by_id.pop(entry["id"], entry) for entry in saved]
    from_file.extend(pending_by_id.values())
    unsaved = {entry["id"] for entry in (pending or []) if entry.get("id")}

    overrides = {
        entry[OVERRIDES_KEY]: entry for entry in from_file
        if isinstance(entry.get(OVERRIDES_KEY), str)
    }
    drawings: List[DrawingWire] = []
    overridden = set()

    for declared in list(getattr(frame, "drawings", None) or []):
        # The layout is always the code's. A file entry that wants a layout of
        # its own is a drawing of its own, which is what keeps adding one
        # dimension from taking a drawing's page and viewports with it.
        scene = _drawing_from_code(frame, declared)
        override = overrides.get(str(declared.drawing_id))
        if override is not None:
            overridden.add(id(override))
            scene["overriddenBy"] = override["id"]
        scene["origin"] = ORIGIN_CODE if override is None else ORIGIN_OVERRIDDEN
        _attach_measurements(scene, _measurements_by_viewport(declared, override, frame), scene["name"], frame)
        drawings.append(scene)

    for entry in from_file:
        if id(entry) in overridden:
            continue
        scene = DrawingWire(**entry)
        scene.setdefault("name", scene["id"])
        target = entry.get(OVERRIDES_KEY)
        if isinstance(target, str):
            # It says it overrides something the code no longer declares. Shown
            # rather than dropped, and shown as what it is, so it can be pointed
            # somewhere else or deleted on purpose.
            scene["dangling"] = True
            log_stderr(
                f"Warning: drawing {scene['id']!r} overrides {target!r}, "
                "which the frame no longer declares."
            )
        scene["origin"] = ORIGIN_FILE
        _attach_measurements(scene, _measurements_by_viewport(None, entry, frame), scene["name"], frame)
        drawings.append(scene)

    # Not in the file yet: either the drawing itself is unsaved, or the override
    # contributing its measurements is. The second matters as much as the first
    # -- a dimension added to a code drawing is unsaved work in a drawing that
    # otherwise is not.
    for drawing in drawings:
        drawing["dirty"] = (
            drawing["id"] in unsaved or drawing.get("overriddenBy") in unsaved
        )

    return drawings


def _resolve_measurement(
    frame: 'Frame', measure: MeasureWire, view: Optional['ViewAxes'] = None,
) -> MeasureWire:
    """A measurement with its anchors found, or marked as not findable.

    Resolved here rather than in the viewer because finding a feature means
    walking the CSG, which is python's. What the viewer gets is geometry in
    world space, which it can project into whichever viewport the measurement
    belongs to.

    The two ends are resolved TOGETHER. Where a dimension attaches is a property
    of the pair and of the plane it is drawn on, not of either feature alone: an
    anchor chosen per feature cannot know where the two face each other, and two
    parallel edges each taking their own midpoint gave a dimension that leaned.
    Only when the pair cannot be placed together does each fall back to a point
    of its own, which is what a feature that resolves to nothing else can offer.
    """
    from kumiki.drawings.drawing import MeasurementKind, MeasurementOperation, MeasurementSpace, ViewAxes
    from kumiki.drawings.measuring import place_pair

    resolved: MeasureWire = {**measure}
    broken = []
    found = {}
    spans = {}
    plane = (measure.get("plane") or {}).get("normal")
    view = ViewAxes.from_wire(view) if view is not None else None
    if plane is None and view is not None:
        # No plane written means the viewport's, which is the invariant an
        # orthographic viewport's measurements are entitled to rely on.
        plane = view.look

    # Which space this is taken in, needed before the ends are resolved: a face
    # is a PLANE in 3D and a line on a sheet, and that is what each end's
    # span comes back as. A 3D measurement says so in its own kind; one still
    # being inferred is projected, since that is what a sheet has.
    declared = MeasurementKind.from_wire(measure.get("kind"))
    in_three_d = declared is not None and declared.space is MeasurementSpace.THREE_D

    for key in ("a", "b"):
        placed = _resolve_anchor_placed(frame, measure.get(key), plane, in_three_d)
        if placed is None:
            broken.append(key)
            continue
        found[key], spans[key] = placed
        resolved[key] = {**(measure.get(key) or {}), **found[key]}

    if broken:
        # Shown greyed rather than dropped: a reference that stops resolving is
        # worth seeing, since the fix is usually a rename away.
        resolved["unresolved"] = broken
        return resolved

    # The resolved ends carry the wire form, since that is what goes to the
    # viewer. The rules take primitives, so they are turned back once here
    # rather than at each of the four places below that ask something of them.
    ends = {key: _geometry_from_wire((resolved.get(key) or {}).get("geometry"))
            for key in ("a", "b")}
    if spans.get("a") is not None and spans.get("b") is not None and plane is not None:
        # Placed for the measurement that will actually be drawn, judged in the space its ends came
        # back in (measuring.place_pair).
        placement = place_pair(ends["a"], ends["b"], spans["a"], spans["b"], declared, plane, view, in_three_d)
        kind = placement.kind
        if kind is not None and kind.operation is MeasurementOperation.DISTANCE and placement.anchors is not None:
            at_a, at_b = placement.anchors
            resolved["a"] = {**resolved["a"], "at": list(at_a)}
            resolved["b"] = {**resolved["b"], "at": list(at_b)}
        elif kind is not None and kind.operation is MeasurementOperation.ANGLE:
            # Where the corner IS and which two ways it opens, from both features together.
            rays = placement.rays
            resolved["angle"] = cast(AngleWire, rays.as_wire()) if rays is not None else None
        resolved["settled"] = _settled_wire(placement.settled)
    else:
        resolved["settled"] = _unplaceable_measurement(measure, spans, plane)
    return resolved


def _unplaceable_measurement(
    measure: MeasureWire, spans: Dict[str, Optional['MeasureSpan']], plane: Optional['VectorLike'],
) -> SettledWire:
    """A measurement that resolved but cannot be worked out, and why.

    Both ends were found -- an end that was not is `unresolved`, handled above
    and shown differently -- and something else is missing, so there is no
    number to send and the viewer is told not to draw it.

    Said here rather than left to the viewer because the viewer cannot work it
    out either, and its predecessor tried: with nothing sent, it fell back to
    judging the pair against whatever camera happened to be showing. For a
    measurement with no plane that is the drift MeasurementPlane exists to stop
    -- the same two points read as their separation from one angle and their
    diagonal from another -- so the honest answer is to refuse rather than to
    show a number that changes when the reader turns.

    Warned about because none of these should happen. A planeless measurement
    predates planes (nothing written since carries none), and the other two mean
    the timber's CSG would not render or a face would not crop -- all worth
    seeing in the log rather than silently not drawing.
    """
    from kumiki.drawings.measuring import unplaceable

    missing = [key for key in ("a", "b") if spans.get(key) is None]
    if plane is None:
        reason, why = "no-plane", (
            "it carries no plane and its viewport declares no camera, so there "
            "is no direction to judge it along")
    else:
        reason, why = "no-span", (
            f"end {' and '.join(missing)} has no extent -- the timber's CSG did "
            f"not render, or a face would not crop")
    log_stderr(
        f"Warning: not drawing the measurement between "
        f"{_measure_end_name(measure, 'a')} and {_measure_end_name(measure, 'b')}: "
        f"{why}.")
    settled = unplaceable(has_plane=plane is not None)
    assert settled.reason == reason
    return _settled_wire(settled)


def _measure_end_name(measure: MeasureWire, key: str) -> str:
    """One end of a measurement, named the way a person would look for it."""
    end = measure.get(key) or {}
    return str(end.get("feature") or end.get("timber") or "?")


def _viewport_axes(scene: DrawingWire, viewport_id: str) -> Optional['ViewAxes']:
    """A viewport's camera frame, as the measurement code wants it."""
    from kumiki.drawings.drawing import ViewAxes

    for viewport in scene.get("viewports") or []:
        if viewport.get("id") != viewport_id:
            continue
        camera = viewport.get("camera")
        if not camera:
            return None
        return ViewAxes.from_wire(camera)
    return None


def _attach_measurements(
    scene: DrawingWire,
    by_viewport: Dict[str, List[MeasureWire]],
    drawing_name: str,
    frame: 'Frame',
) -> None:
    """Put each viewport's measurements on the viewport they belong to.

    A measurement is drawn in a viewport and means nothing outside it, so it
    travels with the viewport rather than with the drawing.

    Measurements naming a viewport this layout does not produce cannot be drawn,
    so they are not shown and the mismatch is warned about. They are kept all the
    same: a viewport can come back when the code changes, and dropping them here
    would mean the next save deleted them from the file for good.

    The frame is not optional. Without it the anchors go out unresolved -- no
    position, no geometry -- which the viewer can only read as a broken
    reference, so every measurement on the drawing is refused and silently never
    drawn. That is what a drawing made from a selection did: it is a file
    drawing, and the file loop was the caller that left it out.
    """
    # Each viewport's own camera frame goes with its measurements: the sheet's
    # across and up are what a horizontal or vertical distance is measured
    # along, and its look is the plane of any measurement that did not write one.
    remaining = {
        viewport: [
            _resolve_measurement(frame, measure, _viewport_axes(scene, viewport))
            for measure in measures
        ]
        for viewport, measures in by_viewport.items()
    }
    for viewport in scene.get("viewports") or []:
        viewport["measurements"] = remaining.pop(viewport.get("id"), [])
    unplaceable = {
        viewport: measures for viewport, measures in remaining.items() if measures
    }
    for viewport in unplaceable:
        log_stderr(
            f"Warning: drawing {drawing_name!r} has measurements for viewport "
            f"{viewport!r}, which it does not have. They are kept but not shown."
        )
    scene["unplaceableMeasurements"] = unplaceable


def _savable_override(scene: DrawingWire) -> DrawingWire:
    """A code drawing the file overrides, as the file holds it: the override, not the drawing.

    The scene here is the merge -- the code's layout with the file's measurements -- so
    saving it as it is wrote a copy of the whole drawing that no longer said what it
    overrides. Read back, that was a second drawing of the same name, and the code one
    had lost every change.
    """
    saved = _savable_drawing({**scene, OVERRIDES_KEY: scene["id"]})
    return {
        "id": scene.get("overriddenBy") or f"{scene['id']}-measurements",
        "name": scene.get("name", scene["id"]),
        OVERRIDES_KEY: scene["id"],
        "viewports": saved["viewports"],
    }


def _savable_drawing(drawing: DrawingWire) -> DrawingWire:
    """One drawing as the file should hold it.

    Measurements the code produced are left out. Writing them would freeze what
    an algorithm generates into the file, and it would stop following the
    algorithm the moment the frame changed -- the same reason an untouched code
    drawing is not written out either.
    """
    saved = DrawingWire(**drawing)
    for transient in ("origin", "dirty", "unplaceableMeasurements", "overriddenBy", "dangling"):
        saved.pop(transient, None)

    def keepers(measures: Optional[List[MeasureWire]]) -> List[MeasureWire]:
        kept = []
        for measure in measures or []:
            if measure.get("origin") in (ORIGIN_OVERRIDDEN, ORIGIN_FILE, ORIGIN_DELETED):
                copy = MeasureWire(**measure)
                copy.pop("origin", None)
                kept.append(copy)
        return kept

    # Written back the way the file holds them: on the viewports. An override
    # keeps only the ids, since the layout is the code's; a drawing of its own
    # keeps whatever it had.
    is_override = isinstance(drawing.get(OVERRIDES_KEY), str)
    viewports: List[ViewportWire] = []
    for viewport in saved.get("viewports") or []:
        kept = keepers(viewport.get("measurements"))
        if is_override and not kept:
            continue
        if is_override:
            entry = ViewportWire()
            if "id" in viewport:
                entry["id"] = viewport["id"]
        else:
            entry = ViewportWire(**viewport)
        entry["measurements"] = kept
        viewports.append(entry)
    # Ones that could not be placed keep their viewport, so they come back if it
    # does rather than being deleted by the next save.
    for viewport, measures in (drawing.get("unplaceableMeasurements") or {}).items():
        kept = keepers(measures)
        if kept:
            viewports.append(ViewportWire(id=viewport, measurements=kept))
    saved["viewports"] = viewports
    return saved


def write_drawings_file(example_path: Path, drawings: List[DrawingWire]) -> str:
    """Save the drawings that are the file's to keep.

    Only the ones the file is responsible for: a drawing that came from code and
    was never touched has nothing to save, and writing it out would freeze a
    copy that stops following the code it was asked for by.
    """
    path = _drawings_file_path(example_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = [_savable_override(drawing) if drawing.get("origin") == ORIGIN_OVERRIDDEN
            else _savable_drawing(drawing)
            for drawing in drawings
            if drawing.get("origin") in (ORIGIN_OVERRIDDEN, ORIGIN_FILE)]
    path.write_text(json.dumps({"drawings": keep}, indent=2) + "\n", encoding="utf-8")
    return str(path)


# --- resolving a measurement's anchors --------------------------------------
#
# A FeaturePath says which feature; this finds it and works out where it is. The
# CSG tree is timber-local, so everything located in it is lifted through the
# timber's transform before it leaves here -- a measurement between two timbers
# compares nothing meaningful otherwise.


def _candidate_segments(node: 'CutCSG') -> Dict[int, str]:
    from kumiki.csg.feature_paths import candidate_segments
    return candidate_segments(node)


def _handle_of(feature: 'CSGFeature', node: 'CutCSG', timber: 'PerfectTimberWithin') -> 'FeatureHandle':
    from kumiki.csg.cutcsg import OwnedFeatureHit
    from kumiki.csg.feature_paths import FeatureHandle

    return FeatureHandle(timber=timber, hit=OwnedFeatureHit(feature=feature, owner=node))


def _anchor_floats(handle: 'FeatureHandle', root: Optional['CutCSG'] = None) -> Optional[List[float]]:
    """Where a dimension attaches to the feature (measuring.feature_anchor), as the wire has it."""
    from kumiki.drawings.measuring import feature_anchor

    at = feature_anchor(handle, root)
    return None if at is None else _vector3_to_floats(at)


def _world_geometry_payload(handle: 'FeatureHandle') -> Optional[GeometryWire]:
    """A feature's unbounded geometry, in world space, as the viewer wants it."""
    from kumiki.drawings.measuring import world_geometry

    return _geometry_payload(world_geometry(handle))


def _settled_wire(settled: 'Settled') -> SettledWire:
    """What a measurement comes to (measuring.Settled), as the viewer reads it."""
    def end(form: Optional['EndForm']) -> Optional[SettledEndWire]:
        if form is None:
            return None
        wire: SettledEndWire = {"form": form.form}
        if form.normal is not None:
            wire["normal"] = list(form.normal)
        if form.direction is not None:
            wire["direction"] = list(form.direction)
        return wire

    return {"kind": cast(MeasureKindWire, settled.kind.as_wire()) if settled.kind is not None else None,
            "available": list(settled.available), "space": settled.space,
            "value": (None if settled.unit is None or settled.value is None
                      else {"unit": settled.unit, "value": settled.value}),
            "reason": settled.reason, "a": end(settled.a), "b": end(settled.b)}


def _geometry_payload(geometry: Optional['Located']) -> Optional[GeometryWire]:
    """One of those, in the shape the viewer reads.

    The wire keeps the mapping form -- a "kind" and two lists -- because that is
    what crosses to JavaScript. Python stopped taking it: kumiki.drawings.drawing works
    in the primitives, and this is where the one becomes the other.
    """
    from kumiki.geometry import Line, Plane, Point

    if isinstance(geometry, Point):
        return {"kind": "point", "at": _vector3_to_floats(geometry.position)}
    if isinstance(geometry, Line):
        return {"kind": "line", "at": _vector3_to_floats(geometry.point),
                "direction": _vector3_to_floats(geometry.direction)}
    if isinstance(geometry, Plane):
        return {"kind": "plane", "at": _vector3_to_floats(geometry.point),
                "normal": _vector3_to_floats(geometry.normal)}
    return None


def _geometry_from_wire(value: Optional[GeometryWire]) -> Optional['Located']:
    """The other direction: what the viewer sent, as the primitive it describes.

    The held end of a half-made measurement comes back this way -- the viewer
    keeps the geometry it was given and hands it back with the next pick.
    """
    from kumiki.geometry import Line, Plane, Point
    from kumiki.rule import create_v3

    def vector(parts: Any) -> Any:
        return create_v3(*(float(part) for part in parts))

    if value is None:
        return None
    kind = value.get("kind")
    if kind == "point":
        return Point(position=vector(value["at"]))
    if kind == "line":
        return Line(point=vector(value["at"]),
                    direction=vector(value.get("direction") or (0, 0, 0)))
    if kind == "plane":
        return Plane(point=vector(value["at"]),
                     normal=vector(value.get("normal") or (0, 0, 0)))
    return None


def _resolve_anchor_placed(
    frame: 'Frame', anchor: Optional[AnchorWire], plane: Optional['VectorLike'],
    solid_space: bool = False,
) -> Optional[Tuple[AnchorWire, Optional['MeasureSpan']]]:
    """Where the feature an anchor names actually is, in world space.

    None when it cannot be found, so the caller shows the measurement as broken.
    """
    from kumiki.csg.feature_paths import resolve_feature_path

    path = deserialize_feature_path(anchor)
    if path is None:
        return None
    handle = resolve_feature_path(path, frame)
    if handle is None:
        return None
    cut_timber = frame.cut_timber_of(handle.timber)
    if cut_timber is None:
        return None
    root_csg = cut_timber.render_timber_with_cuts_csg_local()
    located = handle.feature.locate_simple_unbounded(handle.owner)
    return _anchor_payload(handle.feature, handle.owner, handle.timber, located, root_csg, plane, solid_space)


def _anchor_payload(
    feature: 'CSGFeature', node: 'CutCSG', timber: 'PerfectTimberWithin', located: Optional['Located'],
    root_csg: 'CutCSG', plane: Optional['VectorLike'], solid_space: bool = False,
) -> Tuple[AnchorWire, Optional['MeasureSpan']]:
    """What one end of a measurement is: where it is, what it lies on, its extent.

    The span is what the pairwise rules need and the anchor is what they fall
    back to. Both come from one lookup so they cannot end up describing
    different features.
    """
    from kumiki.drawings.feature_span import feature_span

    handle = _handle_of(feature, node, timber)
    return ({
        "at": _anchor_floats(handle, root_csg),
        "geometry": _world_geometry_payload(handle),
    }, feature_span(handle, root_csg, plane, solid_space))


def _reference_features_payload(timber: 'PerfectTimberWithin', root_csg: Optional['CutCSG'] = None) -> List[ReferenceLineWire]:
    """A timber's reference features, as world-space lines for the viewer to light.

    Of the perfect timber: a line runs the timber's length, and a face or center plane
    is its outline. With *root_csg* -- the cut timber, in its local space -- each line is
    cropped to it the way a selected edge is, so it stops where a cut took the wood.
    The first is the primary reference, which a drawing marks.
    """
    from kumiki.measuring import (locate_center_plane, locate_edge, locate_face,
                                  locate_long_face_centerline)

    references = getattr(getattr(timber, "ticket", None), "reference_features", ()) or ()
    if not references:
        return []
    vector = lambda v: [float(v[i]) for i in range(3)]  # noqa: E731
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))  # noqa: E731
    plus = lambda a, b, k=1.0: [x + k * y for x, y in zip(a, b)]  # noqa: E731
    origin = vector(timber.get_bottom_position_global())
    along = vector(timber.get_length_direction_global())
    length = float(timber.length)
    axes = [vector(timber.orientation.matrix[:, column]) for column in (0, 1)]
    sizes = [float(timber.size[0]), float(timber.size[1])]

    def run(point: List[float]) -> Tuple[List[float], List[float]]:
        """The line through *point* along the timber, from its bottom end to its top."""
        start = plus(point, along, dot(plus(origin, point, -1.0), along))
        return start, plus(start, along, length)

    found = []
    for index, feature in enumerate(references):
        name = feature.name
        if name.endswith("_FACE") or name.endswith("_CENTER_PLANE"):
            plane = (locate_face(timber, feature.long_face()) if name.endswith("_FACE")
                     else locate_center_plane(timber, feature.center_plane()))
            normal = vector(plane.normal)
            across = [normal[1] * along[2] - normal[2] * along[1],
                      normal[2] * along[0] - normal[0] * along[2],
                      normal[0] * along[1] - normal[1] * along[0]]
            half = 0.5 * sum(abs(dot(across, axis)) * size for axis, size in zip(axes, sizes))
            bottom, top = run(vector(plane.point))
            corners = [plus(bottom, across, -half), plus(bottom, across, half),
                       plus(top, across, half), plus(top, across, -half)]
            segments = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        else:
            line = (locate_long_face_centerline(timber, feature.long_face_centerline())
                    if name.endswith("_FACE_CENTERLINE")
                    else locate_edge(timber, feature.centerline() if name == "CENTERLINE" else feature.edge()))
            segments = [run(vector(line.point))]
        if root_csg is not None:
            # The axis runs through the wood; everything else lies on its surface.
            segments = _cropped_reference_segments(
                timber, root_csg, segments, through_material=name == "CENTERLINE")
        found.append({
            "name": name.lower(),
            "primary": index == 0,
            "edgePositions": [value for segment in segments for end in segment for value in end],
        })
    return found


def _cropped_reference_segments(
    timber: 'PerfectTimberWithin', root_csg: 'CutCSG', segments: List[Any], through_material: bool,
) -> List[Any]:
    """*segments* (world space) cut down to where the cut timber still has them.

    On its surface, or -- *through_material* -- inside it. Exact first, then at float
    noise, as a declared edge is (see cropped_edge_segments).
    """
    from kumiki.viewer.picking import DECLARED_EDGE_FLOAT_NOISE
    from kumiki.csg.cropcsg import (crop_line_to_boundary_segments_on_csg,
                                    crop_line_to_segments_on_csg)
    from kumiki.geometry import Line, unit_vector
    from kumiki.rule import create_v3

    crop = crop_line_to_segments_on_csg if through_material else crop_line_to_boundary_segments_on_csg
    near = timber.get_perfect_timber_within_csg_local().transform.position
    reach = float(timber.length) * 4
    kept = []
    for start, end in segments:
        a = timber.transform.global_to_local(create_v3(*start))
        b = timber.transform.global_to_local(create_v3(*end))
        span = float(((b - a).T * (b - a))[0, 0]) ** 0.5
        if span <= 0:
            continue
        line = Line(direction=unit_vector(b - a), point=a)
        station = lambda point: float(((point - a).T * line.direction)[0, 0])  # noqa: E731
        pieces = crop(line, root_csg, seed_reach=reach, near=near, tolerance=0.0)
        if not pieces:
            pieces = crop(line, root_csg, seed_reach=reach, near=near, tolerance=DECLARED_EDGE_FLOAT_NOISE)
        for piece in pieces or []:
            low, high = sorted((station(piece.start), station(piece.end)))
            low, high = max(low, 0.0), min(high, span)
            if high - low <= 1e-9:
                continue
            at = lambda distance: [float(v) for v in timber.transform.local_to_global(  # noqa: E731
                a + line.direction * distance)]
            kept.append((at(low), at(high)))
    return kept


def feature_highlights(slot_state: SlotState, references: Sequence[AnchorWire]) -> List[HighlightWire]:
    """What to light for each feature reference, in the shape a pick answer has.

    For features nobody is pointing at -- a measurement's ends. A reference that no
    longer finds its feature gets an empty highlight rather than an error.
    """
    return [_feature_highlight(slot_state, reference) for reference in references]


def _feature_highlight(slot_state: SlotState, reference: AnchorWire) -> HighlightWire:
    from kumiki.viewer.picking import build_inv_transform_float, edge_highlight_segments, extract_highlight_mesh
    from kumiki.csg.feature_paths import resolve_feature_path
    from kumiki.identity import SingleFeaturePath

    result: HighlightWire = {"highlightMesh": {"vertices": [], "indices": []}}
    path = deserialize_feature_path(reference)
    handle = resolve_feature_path(path, slot_state.frame) if path is not None else None
    if handle is None:
        return result
    cached = slot_state.mesh_cache.get(str((reference or {}).get("timber") or "")) or {}
    timber = handle.timber
    root = cached.get("local_csg") or slot_state.frame.cut_timber_of(timber).render_timber_with_cuts_csg_local()
    feature_type = handle.feature.feature_type().name
    result["featureType"] = feature_type
    if feature_type == "POINT":
        result["at"] = _anchor_floats(handle, root)
    elif feature_type == "EDGE":
        segments, _absent = edge_highlight_segments(handle.feature, handle.owner, timber, root)
        if segments:
            result["highlightEdgeSegments"] = segments
    elif cached.get("mesh") is not None and isinstance(path, SingleFeaturePath):
        rotation, position = build_inv_transform_float(timber.transform)
        vertices, indices, _matched, _total = extract_highlight_mesh(
            cached["mesh"]["vertices"], cached["mesh"]["indices"], handle.owner, rotation, position,
            5e-4, root_csg=root, selected_path=list(path.ref.csg_path), selected_ref=handle.owner,
            feature_label=handle.feature.name, feature_type=feature_type,
        )
        result["highlightMesh"] = {"vertices": vertices, "indices": indices}
    return result


def serialize_layers(frame: 'Frame', frame_parts: Sequence[Tuple[str, Any]] = ()) -> LayersWire:
    """Build the data payload consumed by the viewer's Layers panel.

    With several *frame_parts* -- a file's @frame functions shown as one -- it also says
    which timbers and joints are each frame's, so the panel can list them frame by frame.

    Stable identities use ``ticket.kumiki_id`` for tickets-bearing entities
    (timbers, joints, accessories). Cuts have no ticket and are referenced as
    ``"<timber_kumiki_id>/cut/<cut_index>"`` on the JS side.
    """
    timber_entries, accessory_entries = _assign_member_keys(frame)

    # Build a map of timber object to (timber_kumiki_id, frame's CutTimber)
    timber_to_kumiki_and_cut: Dict[int, tuple[int, Any]] = {}
    for entry in timber_entries:
        timber_id = id(entry["timber"])
        timber_to_kumiki_and_cut[timber_id] = (entry["kumikiEphemeralId"], entry["cutTimber"])

    timber_tags_by_kumiki_id: Dict[int, List[TagWire]] = {}
    for entry in timber_entries:
        timber_ticket = getattr(entry.get("timber"), "ticket", None)
        timber_tags_by_kumiki_id[entry["kumikiEphemeralId"]] = _serialize_timber_tags(timber_ticket)

    # Extract joint records from source_joints
    source_joints = list(getattr(frame, "source_joints", ()) or ())
    accessory_kumiki_ephemeral_to_joint: Dict[int, int] = {}

    joints_payload: List[LayerJointWire] = []
    for joint in source_joints:
        joint_ticket = getattr(joint, "ticket", None)
        if joint_ticket is None:
            continue
        
        joint_kumiki_id = int(getattr(joint_ticket, "kumiki_id", 0))
        joint_name = _joint_display_name(joint)
        joint_type = getattr(joint_ticket, "joint_type", None)
        
        # Extract members (timbers) from cuttings
        members_list: List[JointMemberWire] = []
        cuttings_dict = getattr(joint, "cuttings", {})
        for cutting in cuttings_dict.values():
            timber = getattr(cutting, "timber", None)
            if timber is None:
                continue
            timber_id = id(timber)
            if timber_id not in timber_to_kumiki_and_cut:
                continue
            timber_kumiki_id, frame_cut_timber = timber_to_kumiki_and_cut[timber_id]
            
            # Find which cuts from this timber (in the joint) appear in the frame's merged CutTimber
            # by comparing object identity
            joint_cuts = [cutting]
            frame_cuts = getattr(frame_cut_timber, "cuts", [])
            
            cut_indices = []
            for frame_cut_idx, frame_cut in enumerate(frame_cuts):
                # Check if this frame cut is one of the joint's cuts (by identity)
                for joint_cut in joint_cuts:
                    if frame_cut is joint_cut:
                        cut_indices.append(frame_cut_idx)
                        break
            
            if cut_indices:
                members_list.append({
                    "timberKumikiEphemeralId": timber_kumiki_id,
                    "cutIndices": cut_indices,
                })

        # Extract accessories
        accessory_kumiki_ids: List[int] = []
        joint_accessories = getattr(joint, "jointAccessories", {})
        for accessory in joint_accessories.values():
            accessory_ticket = getattr(accessory, "ticket", None)
            if accessory_ticket is not None:
                accessory_kumiki_id = int(getattr(accessory_ticket, "kumiki_id", 0))
                accessory_kumiki_ids.append(accessory_kumiki_id)
                accessory_kumiki_ephemeral_to_joint[accessory_kumiki_id] = joint_kumiki_id

        joints_payload.append({
            "kumikiEphemeralId": joint_kumiki_id,
            "name": joint_name,
            "jointType": joint_type,
            "members": members_list,
            "accessoryKumikiEphemeralIds": accessory_kumiki_ids,
        })

    timbers_payload: List[LayerTimberWire] = []
    for entry in timber_entries:
        cuts_meta = _serialize_cutting_summary(entry["cutTimber"])
        timbers_payload.append({
            "kumikiEphemeralId": entry["kumikiEphemeralId"],
            "memberKey": entry["memberKey"],
            "name": entry["displayName"],
            "tags": list(timber_tags_by_kumiki_id.get(entry["kumikiEphemeralId"], [])),
            "cuts": cuts_meta,
            "referenceFeatures": _reference_features_payload(
                entry["timber"], entry["cutTimber"].render_timber_with_cuts_csg_local()),
        })

    accessories_payload: List[LayerAccessoryWire] = []
    for entry in accessory_entries:
        accessories_payload.append({
            "kumikiEphemeralId": entry["kumikiEphemeralId"],
            "memberKey": entry["memberKey"],
            "name": entry["displayName"],
            "type": entry["type"],
            "jointKumikiEphemeralId": accessory_kumiki_ephemeral_to_joint.get(entry["kumikiEphemeralId"]),
        })

    # Solving the disassembly can take a while on big frames, so the layers
    # payload only announces whether a solve is COMING ({"pending": true});
    # the extension then issues a separate get_assembly request and forwards
    # the solved payload to the viewer, which shows a loading state meanwhile.
    return {
        "frameName": frame.name if hasattr(frame, "name") else None,
        "timbers": timbers_payload,
        "accessories": accessories_payload,
        "joints": joints_payload,
        "frames": _serialize_frame_parts(frame_parts, timber_to_kumiki_and_cut),
        "assembly": {"pending": True} if _frame_has_assembly_freedoms(frame) else None,
    }


def _serialize_frame_parts(
    frame_parts: Sequence[Tuple[str, Any]],
    timber_to_kumiki_and_cut: Dict[int, Any],
) -> Optional[List[FramePartWire]]:
    """Which timbers and joints are each frame's, or None when there is only the one frame."""
    if len(frame_parts) < 2:
        return None
    parts = []
    for name, part in frame_parts:
        timber_ids = [timber_to_kumiki_and_cut[id(cut.timber)][0] for cut in part.cut_timbers
                      if id(cut.timber) in timber_to_kumiki_and_cut]
        parts.append({
            "name": getattr(part, "name", None) or name,
            "timberKumikiEphemeralIds": timber_ids,
            "jointKumikiEphemeralIds": [int(getattr(joint.ticket, "kumiki_id", 0)) for joint in (part.source_joints or [])
                                        if getattr(joint, "ticket", None) is not None],
        })
    return parts


def _frame_has_assembly_freedoms(frame: 'Frame') -> bool:
    """Cheap gate mirroring solve_frame_assembly's: does any joint member
    declare an assembly freedom? (No solving involved.)"""
    source_joints = list(getattr(frame, "source_joints", ()) or ())
    for joint in source_joints:
        for cutting in joint.cuttings.values():
            if cutting.assembly_freedom is not None:
                return True
        for accessory in joint.jointAccessories.values():
            if accessory.assembly_freedom is not None:
                return True
    return False


def _assembly_float(value: Any) -> float:
    """Strict numeric conversion for assembly payloads (no string fallback)."""
    try:
        return float(value)
    except TypeError:
        return float(value.evalf())


def _build_assembly_payload(
    frame: 'Frame',
    timber_entries: List[TimberEntry],
    accessory_entries: List[AccessoryEntry],
    should_cancel: Optional[Any] = None,
) -> Optional[AssemblyWire]:
    """Solve the frame's assembly sequence for the viewer's preview timeline.

    Returns None when no member of any joint declares an assembly freedom
    (the viewer hides the timeline). Payload shape:

        {"steps": [{"order": int, "suborder": int, "substep": int,  # substep is 1-based
                    "movements": [{"kumikiEphemeralId": int, "memberKey": str,
                                   "direction": [x, y, z],  # unit
                                   "distance": float,       # base freed_after amount
                                   "dragged": bool,
                                   "rotation": {"axisPosition": [x, y, z],  # optional
                                                "axisDirection": [x, y, z],
                                                "angle": float}}]}],  # radians
         "warnings": [str],
         "failure": {"order": int | None, "suborder": int,
                     "message": str, "diagnostics": [str]} | None}

    ``distance`` is unscaled; the viewer multiplies by its configurable
    disassembly multiplier. On failure the solved steps are still included so
    the timeline stays scrubbable up to the failure point.
    """
    try:
        from kumiki.timber import solve_frame_assembly
    except ImportError:
        return None

    member_key_by_kumiki_id: Dict[int, str] = {}
    for entry in timber_entries:
        member_key_by_kumiki_id[entry["kumikiEphemeralId"]] = entry["memberKey"]
    for entry in accessory_entries:
        member_key_by_kumiki_id[entry["kumikiEphemeralId"]] = entry["memberKey"]

    try:
        solution = solve_frame_assembly(frame, should_cancel=should_cancel)
    except Exception as exc:  # noqa: BLE001 — assembly must never break the layers tree
        log_stderr(f"[assembly] solve failed: {exc}")
        return {
            "steps": [],
            "warnings": [],
            "failure": {"order": None, "suborder": 0, "message": str(exc), "diagnostics": []},
        }
    if solution is None:
        return None

    steps_payload: List[AssemblyStepWire] = []
    for step in solution.steps:
        movements_payload: List[MovementWire] = []
        for movement in step.movements:
            member_key = member_key_by_kumiki_id.get(movement.member_key)
            if member_key is None:
                # Member not rendered (e.g. filtered out of the frame); skip defensively.
                continue
            movement_payload: MovementWire = {
                "kumikiEphemeralId": int(movement.member_key),
                "memberKey": member_key,
                "direction": [_assembly_float(movement.direction[i, 0]) for i in range(3)],
                "distance": _assembly_float(movement.distance),
                "dragged": bool(movement.dragged),
            }
            if movement.rotation is not None:
                rotation = movement.rotation
                movement_payload["rotation"] = {
                    "axisPosition": [_assembly_float(rotation.axis_position[i, 0]) for i in range(3)],
                    "axisDirection": [_assembly_float(rotation.axis_direction[i, 0]) for i in range(3)],
                    "angle": _assembly_float(rotation.angle),
                }
            movements_payload.append(movement_payload)
        steps_payload.append({
            "order": int(step.ordering.order),
            "suborder": int(step.ordering.suborder),
            "substep": int(step.substep),
            "movements": movements_payload,
        })

    failure_payload: Optional[AssemblyFailureWire] = None
    if solution.failure is not None:
        failure_payload = {
            "order": int(solution.failure.ordering.order),
            "suborder": int(solution.failure.ordering.suborder),
            "message": solution.failure.message,
            "diagnostics": list(solution.failure.diagnostics),
        }

    return {
        "steps": steps_payload,
        "warnings": list(solution.warnings),
        "failure": failure_payload,
    }


def _serialize_feature(feature: 'CSGFeature') -> FeatureWire:
    """One declared feature, with the metadata the tree view wants to show."""
    return {
        "name": feature.name,
        "type": feature.feature_type().name,
        "group": feature.group.name,
        "real": feature.real,
    }


def _serialize_csg_node(
    csg: 'CutCSG',
    path: List[str],
    role: Optional[str],
    attribution: _CutAttribution,
    cut_timber: 'CutTimber',
    parity: 'CSGParity',
    path_label: Optional[str] = None,
    segments: Optional[Dict[int, str]] = None,
) -> CSGNodeWire:
    """One CSG node and everything beneath it.

    Nested rather than flattened, and every node rather than only labelled
    ones. This is a debugging surface: the shape of the tree, and the untagged
    intermediates in it, are exactly what you need when the shape is what has
    gone wrong. `path` still carries labels only, since that is what
    find_csg_by_path navigates by.
    """
    from kumiki.viewer.picking import label_name
    from kumiki.csg.cutcsg import (
        Difference, Intersection, SolidUnion, csg_children, csg_children_with_parity,
    )

    # role says which edge a child sits on; parity says what that edge means
    # for the finished solid, and the two differ -- two subtract edges cancel.
    # The rule itself lives in kumiki, stated once.
    child_parity = {
        id(child): child_par
        for child, child_par in csg_children_with_parity(csg, parity)
    }

    label = label_name(csg)
    # `label` stays the bare name people read; the path segment carries the
    # occurrence that tells same-named siblings apart.
    segment = path_label
    node_path = path + [segment] if segment else path

    node: CSGNodeWire = {
        # kind is the class name and stays machine-readable -- the viewer keys
        # structural decisions off it. displayName is the word people read.
        "kind": type(csg).__name__,
        "displayName": type(csg).display_name(),
        "label": label,
        "path": list(node_path),
        "role": role,
        "parity": parity.name,
        "jointName": attribution.joint_name,
        "jointId": attribution.joint_id,
        "cutIndex": attribution.cut_index,
        "features": [_serialize_feature(f) for f in csg.get_declared_features()],
        "children": [],
    }

    # A labelled node numbers its own children; an unlabelled one passes the
    # scope it was given straight through, since a path drills past it.
    below = _candidate_segments(csg) if segment else (segments or {})

    def child(node_csg: 'CutCSG', child_role: str, child_attribution: _CutAttribution) -> None:
        node["children"].append(_serialize_csg_node(
            node_csg, node_path, child_role, child_attribution, cut_timber,
            child_parity.get(id(node_csg), parity), below.get(id(node_csg)), below,
        ))

    if isinstance(csg, Difference):
        child(csg.base, "base", attribution)
        cuts = list(getattr(cut_timber, "cuts", []) or [])
        # Only the timber's own top-level Difference lines up with its cuts;
        # a nested one inside a joint's own geometry does not, so attribution
        # is inherited there rather than re-derived.
        aligned = len(csg.subtract) == len(cuts) and not path
        joints_by_cutting = _joint_by_cutting_id(cut_timber) if aligned else {}
        for index, sub_csg in enumerate(csg.subtract):
            sub_attribution = attribution
            if aligned:
                sub_attribution = _cut_attribution(joints_by_cutting, cuts[index], index)
            child(sub_csg, "subtract", sub_attribution)
    elif isinstance(csg, SolidUnion):
        for member in csg.children:
            child(member, "child", attribution)
    elif isinstance(csg, Intersection):
        child(csg.left, "left", attribution)
        child(csg.right, "right", attribution)

    return node


def serialize_cut_csg_tree(cut_timber: 'CutTimber') -> CSGTreeWire:
    """The whole rendered CSG of a timber, as a nested tree.

    Deliberately the rendered tree -- what picking actually runs against --
    rather than one cutting's negative CSG, which is a piece of the input and
    not the thing on screen.
    """
    from kumiki.csg.cutcsg import CSGParity

    local_csg = cut_timber.render_timber_with_cuts_csg_local()
    return {"tree": _serialize_csg_node(
        local_csg, [], None, NO_CUT_ATTRIBUTION, cut_timber, CSGParity.ADDITIVE,
        None, _candidate_segments(local_csg))}


def _module_file_path(module: ModuleType) -> Optional[Path]:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return None
    try:
        return Path(module_file).resolve()
    except Exception:
        return None


def _is_venv_path(path: Path) -> bool:
    path_parts = path.parts
    return ".venv" in path_parts or "venv" in path_parts


# When each project module was imported, by name, so a load purges them only when one has
# changed since; and when the last load was, for a module imported after it.
_project_module_loaded_at: Dict[str, float] = {}
_last_project_load_at = 0.0
# Bumped by every purge. A slot built before one holds objects of classes the purge replaced,
# and new code fails on them (a new Matrix does not know an old one), so it is rebuilt before
# its next use: see _resolve_slot.
_project_generation = 0


def _project_modules(project_root: Path, keep_paths: set[Path]) -> List[Tuple[str, Path]]:
    """The modules a purge would drop: under the project root, outside a venv, not kept."""
    found = []
    for module_name, module in list(sys.modules.items()):
        module_path = _module_file_path(module)
        if module_path is None or module_path in keep_paths or _is_venv_path(module_path):
            continue
        if project_root not in module_path.parents and module_path != project_root:
            continue
        found.append((module_name, module_path))
    return found


def _project_modules_changed(project_root: Path, keep_paths: set[Path]) -> bool:
    """Whether any project module's file was written after it was imported."""
    for module_name, module_path in _project_modules(project_root, keep_paths):
        try:
            written = module_path.stat().st_mtime
        except OSError:
            return True
        if written > _project_module_loaded_at.get(module_name, _last_project_load_at):
            return True
    return False


def _purge_project_modules(project_root: Path, keep_paths: set[Path], verbose: bool = False) -> None:
    """Aggressively purge all project modules from sys.modules to force clean reloads.
    
    This ensures that modified code is actually reflected when reloading, preventing
    stale cached implementations from being used due to import chain caching.
    """
    removable: list[str] = []
    removed_count = 0

    for module_name, module in list(sys.modules.items()):
        module_path = _module_file_path(module)
        if module_path is None:
            continue

        if module_path in keep_paths:
            continue

        if _is_venv_path(module_path):
            continue

        if project_root not in module_path.parents and module_path != project_root:
            continue

        removable.append(module_name)

    # Remove all project modules
    for module_name in removable:
        sys.modules.pop(module_name, None)
        _project_module_loaded_at.pop(module_name, None)
        removed_count += 1

    if verbose:
        if removed_count > 0:
            log_stderr(f"[reload] Purged {removed_count} project module(s): {', '.join(sorted(removable))}")
        else:
            log_stderr("[reload] No project modules to purge (first load or all already clean)")


def _looks_like_frame(value: Any) -> bool:
    return hasattr(value, "cut_timbers") and hasattr(value, "accessories")


def _module_patterns(module: ModuleType) -> List[Any]:
    """The module's @pattern functions as Patterns, in source order. Empty if it marks none."""
    decorators = _frame_decorators()
    if decorators is None or not hasattr(decorators, "module_patterns"):
        return []
    patterns, rejected = decorators.module_patterns(module)
    for entry in rejected:
        log_stderr(f"Warning: @{entry.kind} {entry.name} is not used: {entry.reason}")
    return patterns


def _is_valid_module_part(name: str) -> bool:
    return name.isidentifier() and not name.startswith("_")


def _module_name_for_path(file_path: Path) -> str:
    if _project_root is None:
        return TARGET_MODULE_NAME

    try:
        rel = file_path.resolve().relative_to(_project_root)
    except ValueError:
        return TARGET_MODULE_NAME

    if rel.suffix != ".py":
        return TARGET_MODULE_NAME

    parts = list(rel.with_suffix("").parts)
    if not parts:
        return TARGET_MODULE_NAME
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return TARGET_MODULE_NAME
    if not all(_is_valid_module_part(part) for part in parts):
        return TARGET_MODULE_NAME
    return ".".join(parts)


def load_module_from_path(file_path: Path, verbose: bool = False) -> ModuleType:
    """Load a Python module from file path with aggressive cache invalidation.
    
    This function ensures that:
    1. Python's import cache is invalidated
    2. All project modules are purged from sys.modules
    3. The target module and its dependencies are loaded fresh
    """
    global _last_project_load_at, _project_generation
    started = time.time()

    # Step 1: Invalidate Python's built-in import caches
    importlib.invalidate_caches()
    
    # Step 2: Aggressively purge project modules -- when one has changed. Purging when none has
    # gains nothing, and replaces the classes every other slot's frame was built from.
    keep_paths: set[Path] = set()
    if _project_root is not None:
        keep_paths = {Path(__file__).resolve(), file_path.resolve()}
        if _project_modules_changed(_project_root, keep_paths):
            _purge_project_modules(_project_root, keep_paths, verbose=verbose)
            _project_generation += 1
        elif verbose:
            log_stderr("[reload] No project module changed since it was imported; keeping them")
    else:
        if verbose:
            log_stderr("[reload] WARNING: _project_root is None — project module purge skipped!")
            log_stderr(f"[reload]   sys.argv = {sys.argv}")
            log_stderr("[reload]   Module changes to kumiki/ will NOT be picked up until runner restarts.")

    # Step 3: Ensure target module doesn't exist in sys.modules
    module_name = _module_name_for_path(file_path)
    if TARGET_MODULE_NAME in sys.modules:
        del sys.modules[TARGET_MODULE_NAME]
    if module_name in sys.modules:
        del sys.modules[module_name]

    # Step 4: Load the module fresh
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    if module_name != TARGET_MODULE_NAME:
        sys.modules[TARGET_MODULE_NAME] = module

    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
    if _project_root is not None:
        for name, _path in _project_modules(_project_root, keep_paths):
            _project_module_loaded_at.setdefault(name, started)
    _last_project_load_at = started
    
    if verbose:
        log_stderr(f"[reload] Loaded module: {module_name} from {file_path}")
    
    return module


def _frame_from_pattern_list(pattern_list: List[Any]) -> "tuple[Any, Any]":
    """Render pattern(s) from a List[Pattern] as a single frame.

    Single pattern: raises the first 'main'-tagged pattern at origin.
    Multiple patterns: delegates to librarian.build_pattern_grid_frame which renders
    all patterns at origin, computes a square-ish grid layout by translating timbers
    and accessories, and returns one merged Frame.
    """
    from kumiki.rule import create_v3, scalar

    if not pattern_list:
        raise ValueError("Pattern list is empty")

    if len(pattern_list) == 1:
        origin = create_v3(scalar(0), scalar(0), scalar(0))
        target = pattern_list[0]
        with contextlib.redirect_stdout(sys.stderr):
            result = target.raise_at(origin)
        return _coerce_viewable_frame(result, target.name), pattern_list

    from kumiki.librarian import build_pattern_grid_frame
    return build_pattern_grid_frame(pattern_list), pattern_list


def _accepts_an_argument(entry: Any) -> bool:
    """Whether *entry* takes a kiwari.

    One narrow question about arity, not a schema derived from a signature --
    what a parameter is and what it may be comes from the kiwari the builder
    declares, and nothing here reads annotations or defaults to find that out.
    """
    try:
        signature = inspect.signature(entry)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD, parameter.VAR_POSITIONAL)
        for parameter in signature.parameters.values()
    )


def _call_frame_entry(callable_entry: Any, kiwari: Optional['Kiwari'] = None) -> Any:
    """Build a frame, handing it *kiwari* if it is willing to take one."""
    with contextlib.redirect_stdout(sys.stderr):
        if _accepts_an_argument(callable_entry):
            return callable_entry(kiwari)
        if kiwari is not None:
            raise TypeError(
                f"{getattr(callable_entry, '__name__', 'this frame')} was given parameters to "
                "build with but takes no argument to receive them. Declare them with a kiwari: "
                "def build_frame(k: Kiwari | None = None) -> Frame"
            )
        return callable_entry()


# --- parameters saved beside the source -------------------------------------
#
# myframe.py -> myframe.parameters.json. Beside the source rather than under
# .kigumi/ (where drawings go) because a parameter choice is something you
# want to commit. The file watcher only watches the example file's own
# basename, so writing a sibling does not set off a reload.


def _parameters_file_path(example_path: Path) -> Path:
    return example_path.parent / f"{example_path.stem}.parameters.json"


def _can_save_parameters(slot_state: SlotState) -> bool:
    """Whether this slot may write its parameters beside its source.

    Not for a pattern: those live in library folders we have no business
    writing to, and a pattern's values belong to whoever raised it. Not for a
    file outside the workspace either, which is the same library case reached
    by a different road.
    """
    if slot_state.single_pattern_name is not None:
        return False
    workspace = _workspace_root()
    if workspace is None:
        return False
    try:
        slot_state.file_path.relative_to(workspace)
    except ValueError:
        return False
    return True


def _workspace_root() -> Optional[Path]:
    root = os.environ.get("KIGUMI_WORKSPACE_ROOT") or _project_root
    return Path(root).resolve() if root else None


def _read_parameters_file(
    example_path: Path,
) -> "tuple[List[tuple[Optional[List[str]], Dict[str, Any]]], Optional[Path]]":
    """The saved values for *example_path*, as (frames, values) per group, and where they came from.

    A file from before groups has one set of values naming no frames.
    """
    path = _parameters_file_path(example_path)
    if not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log_stderr(f"[parameters] Ignoring {path.name}: {exc}")
        return [], None
    if not isinstance(data, dict):
        return [], path
    if isinstance(data.get("groups"), list):
        saved = [
            ([str(name) for name in group.get("frames", [])], group["values"])
            for group in data["groups"]
            if isinstance(group, dict) and isinstance(group.get("values"), dict)
        ]
        return saved, path
    values = data.get("values")
    return ([(None, values)] if isinstance(values, dict) and values else []), path


def _write_parameters_file(slot_state: SlotState) -> str:
    """Save only what differs from what the code says.

    Writing every value out would mean changing a default in the source did
    nothing for anyone holding one of these files.
    """
    if not slot_state.kiwari_groups:
        raise ValueError("This frame takes no parameters, so there is nothing to save")
    if not _can_save_parameters(slot_state):
        raise ValueError(
            "Parameters can only be saved beside a frame in your own workspace, "
            "not for a library pattern"
        )
    groups = [
        {"frames": list(group.frames),
         "values": {key: group.kiwari.value_payload(key) for key in group.kiwari.changed_from_defaults()}}
        for group in slot_state.kiwari_groups
    ]
    groups = [group for group in groups if group["values"]]
    path = _parameters_file_path(slot_state.file_path)
    if not groups:
        # Nothing differs any more, so the file has nothing left to say.
        if path.exists():
            path.unlink()
        return str(path)
    payload = {
        "schema_version": 2,
        "groups": groups,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return str(path)


def _bind_kiwari_values(kiwari: Optional['Kiwari'], values: Optional[Mapping[str, Any]]) -> Optional['Kiwari']:
    """*kiwari* with *values* laid over it, or None if there is no kiwari yet."""
    if kiwari is None:
        return None
    if not values:
        return kiwari
    return kiwari.resolve(dict(values))


def _serialize_kiwari_for_slot(slot_state: SlotState, *, stale: bool = False) -> Optional[List[KiwariSectionWire]]:
    """What the panel is built from, one section per kiwari, or None when nothing takes parameters."""
    if slot_state is None or not slot_state.kiwari_groups:
        return None
    can_save = _can_save_parameters(slot_state)
    sections = []
    for group in slot_state.kiwari_groups:
        payload = group.kiwari.to_payload()
        payload["id"] = group.id
        payload["frames"] = list(group.frames)
        payload["canSave"] = can_save
        if stale:
            # Kept from the last build that worked, so the panel can say the values
            # on screen are not the ones the frame in front of you was built from.
            payload["stale"] = True
        sections.append(payload)
    return sections


def _coerce_viewable_frame(value: Any, name: Optional[str] = None) -> Any:
    if _looks_like_frame(value):
        return value

    from kumiki.csg.cutcsg import CutCSG
    from kumiki.rule import Transform
    from kumiki.timber import CSGAccessory, Frame

    frame_name = name or type(value).__name__

    if isinstance(value, CutCSG):
        return Frame(
            cut_timbers=[],
            accessories=[
                CSGAccessory(
                    transform=Transform.identity(),
                    positive_csg=value,
                )
            ],
            name=frame_name,
        )

    if isinstance(value, list) and all(isinstance(item, CutCSG) for item in value):
        return Frame(
            cut_timbers=[],
            accessories=[
                CSGAccessory(
                    transform=Transform.identity(),
                    positive_csg=item,
                )
                for item in value
            ],
            name=frame_name,
        )

    raise TypeError(
        f"{frame_name} returned {type(value).__name__}, expected frame-like object or CutCSG"
    )


def _frame_decorators() -> Optional[ModuleType]:
    """kumiki.frame_decorators, or None on a kumiki from before @frame (0.8.0), where no file can use it."""
    try:
        import kumiki.frame_decorators as frame_decorators
    except ImportError:
        return None
    return frame_decorators


def _build_frame_entry(function: Any, name: str, kiwari: Optional['Kiwari']) -> Any:
    """One @frame, built with the values for its own kiwari, or None on a first build."""
    with contextlib.redirect_stdout(sys.stderr):
        result = function(kiwari)
    return _coerce_viewable_frame(result, name)


def _origin_of(kiwari: 'Kiwari') -> Any:
    # A kumiki from before Kiwari.origin shares nothing between frames.
    return getattr(kiwari, "origin", kiwari)


def _group_kiwaris(built: List["tuple[str, Any]"]) -> Tuple[KiwariGroup, ...]:
    """The frames' kiwari, one group per declared kiwari, in the order they were first built."""
    groups: List["tuple[Any, List[str], Any]"] = []
    for name, kiwari in built:
        if kiwari is None:
            continue
        found = next((group for group in groups if group[0] is _origin_of(kiwari)), None)
        if found is None:
            groups.append((_origin_of(kiwari), [name], kiwari))
        else:
            found[1].append(name)
    return tuple(KiwariGroup(tuple(names), kiwari) for _, names, kiwari in groups)


def resolve_frame_from_module(
    module: ModuleType, incoming: Optional[Mapping[str, Any]] = None,
) -> "tuple[Any, Optional[Any], Tuple[KiwariGroup, ...], Tuple[tuple[str, Any], ...]]":
    """Resolve a frame from a loaded module, each of its frames built with *incoming*'s kiwari.

    In order: the file's `@pattern` functions (a pattern book), its `@frame` functions (each
    built with the values for its own kiwari and shown together), or the deprecated `build_frame` /
    `example`. *incoming* maps a frame's name to the kiwari to build it with.

    Returns (frame, patternbook_or_None, kiwari_groups, frame_parts): frame_parts is each
    @frame's name and its own frame, when there are several shown as one.
    """
    incoming = incoming or {}
    decorators = _frame_decorators()
    entries = decorators.module_entries(module) if decorators is not None else None
    pattern_list = _module_patterns(module)
    if pattern_list:
        if entries is not None and entries.frames:
            log_stderr("Warning: this file has @pattern functions, so it is a pattern book and its "
                       f"@frame functions are not shown: {', '.join(e.name for e in entries.frames)}")
        frame, patternbook = _frame_from_pattern_list(pattern_list)
        return frame, patternbook, (), ()

    for rejected in (entries.rejected if entries is not None else ()):
        log_stderr(f"Warning: @{rejected.kind} {rejected.name} is not used: {rejected.reason}")
    if decorators is not None and entries is not None and entries.frames:
        built = {entry.name: _build_frame_entry(entry.function, entry.name, incoming.get(entry.name))
                 for entry in entries.frames}
        groups = _group_kiwaris([(name, getattr(frame, "kiwari", None)) for name, frame in built.items()])
        # One set of values per kiwari. A frame handed nothing -- new since the last build --
        # is built again with what the rest of its group was handed.
        for group in groups:
            handed = next((incoming[name] for name in group.frames if incoming.get(name) is not None), None)
            for name in group.frames:
                if handed is not None and incoming.get(name) is None:
                    entry = next(entry for entry in entries.frames if entry.name == name)
                    built[name] = _build_frame_entry(entry.function, name, handed)
        groups = _group_kiwaris([(name, getattr(frame, "kiwari", None)) for name, frame in built.items()])
        frames = list(built.values())
        name = frames[0].name if len(frames) == 1 else " + ".join(
            frame.name or entry_name for entry_name, frame in built.items())
        parts = tuple(built.items()) if len(built) > 1 else ()
        return decorators.overlay_frames(frames, name), None, groups, parts

    for legacy in ("build_frame", "example"):
        if not hasattr(module, legacy):
            continue
        entry = getattr(module, legacy)
        if legacy == "build_frame" and not callable(entry):
            continue
        _warn_legacy_entry(legacy)
        if callable(entry):
            entry = _call_frame_entry(entry, incoming.get(legacy))
        if not _looks_like_frame(entry):
            try:
                entry = _coerce_viewable_frame(entry, legacy)
            except TypeError:
                if legacy == "example":
                    continue
                raise
        return entry, None, _group_kiwaris([(legacy, getattr(entry, "kiwari", None))]), ()

    raise AttributeError(
        "Module must have @pattern or @frame functions, "
        "or (deprecated) a 'build_frame()' function or 'example'"
    )


def _warn_legacy_entry(name: str) -> None:
    log_stderr(f"Warning: picking up the frame by the name '{name}' is deprecated and will be removed. "
               f"Mark it with @frame instead: @frame def {name}(k: Kiwari) -> Frame")


def _incoming_from_groups(
    groups: Sequence[KiwariGroup], values_by_group: Optional[Mapping[str, Any]],
) -> Dict[str, Optional['Kiwari']]:
    """Each frame's kiwari to build with: its group's last one, with the viewer's values laid over it."""
    incoming: Dict[str, Optional['Kiwari']] = {}
    for group in groups:
        values = (values_by_group or {}).get(group.id)
        bound = _bind_kiwari_values(group.kiwari, values if isinstance(values, Mapping) else None)
        for name in group.frames:
            incoming[name] = bound
    return incoming


def _incoming_from_saved(groups: Sequence[KiwariGroup], saved: List["tuple[Optional[List[str]], Dict[str, Any]]"]) -> Dict[str, Optional['Kiwari']]:
    """Each frame's kiwari with its group's saved values laid over it.

    A saved group is matched by the frames it names. A file from before groups names none, and
    is every group's -- each taking only the keys it declares, when there are several.
    """
    incoming: Dict[str, Optional['Kiwari']] = {}
    for group in groups:
        bound = group.kiwari
        for frames, values in saved:
            if frames is not None and not set(frames) & set(group.frames):
                continue
            if frames is None and len(groups) > 1:
                values = {key: value for key, value in values.items() if key in group.kiwari.declarations}
            bound = _bind_kiwari_values(group.kiwari, values)
            break
        for name in group.frames:
            incoming[name] = bound
    return incoming


def load_slot_state(
    file_path: str,
    previous_mesh_cache: Optional[Dict[str, MeshCacheEntry]] = None,
    kiwari_values: Optional[Mapping[str, Any]] = None,
    previous_groups: Sequence[KiwariGroup] = (),
) -> SlotState:
    """Load *file_path* into a slot.

    *kiwari_values* maps a group's id to the values the viewer wants for it, laid over what the
    last good build of that group declared. On a first load there is nothing to lay them over
    yet, and each frame's own declaration is all there is.
    """
    resolved_path = Path(file_path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"File not found: {resolved_path}")

    module = load_module_from_path(resolved_path, verbose=True)

    frame, patternbook, groups, parts = resolve_frame_from_module(
        module, _incoming_from_groups(previous_groups, kiwari_values))
    saved, saved_path = _read_parameters_file(resolved_path)
    if saved and groups and not kiwari_values:
        # A companion file is the author's saved starting point, so it only
        # applies when the viewer has not already said what it wants.
        frame, patternbook, groups, parts = resolve_frame_from_module(module, _incoming_from_saved(groups, saved))
    decorators = _frame_decorators()
    entries = decorators.module_entries(module) if decorators is not None else None
    return SlotState(
        file_path=resolved_path,
        module=module,
        frame=frame,
        mesh_cache=previous_mesh_cache if previous_mesh_cache is not None else {},
        patternbook=patternbook,
        kiwari_groups=groups,
        frame_parts=parts,
        tools=entries.tools if entries is not None else (),
        rejected_entries=entries.rejected if entries is not None else (),
        generation=_project_generation,
    )


def make_ready_event(state: RunnerState) -> ReadyEventWire:
    ss = state._active
    frame_summary = serialize_frame(ss.frame)
    tools = _serialize_tools(ss)
    return {
        "type": "ready",
        "examplePath": str(ss.file_path),
        "commands": [
            "ping", "reload_example", "get_frame", "get_geometry",
            "find_csg_at_point", "hover_feature_at_point", "find_csg_by_path",
            "get_layers_tree", "get_csg_tree",
            "get_default_drawing_for_debugging",
            "create_drawing_from_selection",
            "get_drawings", "save_drawings", "add_measurement",
            "update_measurement", "delete_measurement", "restore_measurement", "feature_highlights",
            "save_parameters",
            "load_slot", "unload_slot", "list_slots",
            "list_available_patterns", "raise_specific_pattern",
            "list_tools", "run_tool",
            "shutdown",
        ],
        "frame": {
            "name": frame_summary["name"],
            "timber_count": frame_summary["timber_count"],
            "accessories_count": frame_summary["accessories_count"],
        },
        "kiwari": _serialize_kiwari_for_slot(ss),
        "tools": tools["tools"],
        "rejectedEntries": tools["rejectedEntries"],
    }


def _serialize_tools(slot_state: SlotState) -> ToolsWire:
    """The slot's @tool functions, and the @frame / @tool functions rejected for their signature."""
    return {
        "tools": [{"name": entry.name} for entry in slot_state.tools],
        "rejectedEntries": [{"name": r.name, "kind": r.kind, "reason": r.reason} for r in slot_state.rejected_entries],
    }


def run_tool(slot_state: SlotState, name: str) -> ToolRunWire:
    """Run one of the slot's @tool functions on its frame; its text is the result."""
    entry = next((entry for entry in slot_state.tools if entry.name == name), None)
    if entry is None:
        available = [entry.name for entry in slot_state.tools]
        raise ValueError(f"No tool named {name!r}. Available: {available}")
    with contextlib.redirect_stdout(sys.stderr):
        output = entry.function(slot_state.frame)
    if not isinstance(output, str):
        raise TypeError(f"tool {name!r} returned {type(output).__name__}, expected str")
    return {"name": name, "output": output}


def make_success_response(request_id: Any, command: str, result: Any) -> ResponseWire:
    return {
        "id": request_id,
        "ok": True,
        "command": command,
        "result": result,
    }


def make_error_response(request_id: Any, command: str, exc: Exception) -> ResponseWire:
    return {
        "id": request_id,
        "ok": False,
        "command": command,
        "error": {
            "message": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        },
    }


# ===========================================================================
# Picking: the requests. What a point or ray lands on, and what to light for it,
# is kumiki.viewer.picking; this turns its answers into wire forms.
# ===========================================================================

def _local_ray_from_payload(
    payload: PickRequest, rot: 'Rows3', pos: 'Float3',
) -> Optional[LocalRay]:
    """The pointer's ray in timber-local space, or None if it did not send one.

    None is ordinary rather than a fault: a pick can be made without a ray (the
    tests do, and so does any caller that has only a point), and everything on
    a surface is found from the point alone.
    """
    from kumiki.viewer.picking import inv_transform_direction, inv_transform_point
    ray = payload.get("ray")
    if not isinstance(ray, dict):
        return None
    origin, direction = ray.get("origin"), ray.get("direction")
    if not (isinstance(origin, list) and isinstance(direction, list)):
        return None
    if len(origin) != 3 or len(direction) != 3:
        return None
    return (
        inv_transform_point(rot, pos, origin),
        inv_transform_direction(rot, direction),
    )


def _joint_by_cutting_id(cut_timber: 'CutTimber') -> Dict[int, 'Joint']:
    """{id(cutting): joint} for the joints that cut this timber.

    A Joint already owns its cuttings, so the reverse link is derived here.

    Reads CutTimber.joints rather than Frame.source_joints, which keeps this
    local to the timber being picked: no frame has to be threaded through, and
    a Frame assembled by some route other than from_joints does not silently
    lose the ability to name joints. Empty for a CutTimber built by hand,
    where attribution is unavailable rather than wrong.
    """
    lookup: Dict[int, 'Joint'] = {}
    for joint in getattr(cut_timber, "joints", None) or ():
        for cutting in (getattr(joint, "cuttings", None) or {}).values():
            lookup[id(cutting)] = joint
    return lookup


def _cutting_for_node(
    local_csg: 'CutCSG',
    cut_timber: 'CutTimber',
    target: 'CutCSG',
) -> Optional['Cutting']:
    """Which Cutting produced *target*, or None if it is the timber body.

    render_timber_with_cuts_csg_local() builds
    ``Difference(body, [cut.get_negative_csg_local() for cut in cuts])`` -- one
    subtract child per cutting, in order. That correspondence is created in a
    single function, so this reads it in a single function; everything else
    here is identity-based.
    """
    from kumiki.viewer.picking import subtree_contains
    from kumiki.csg.cutcsg import Difference

    if not isinstance(local_csg, Difference):
        return None
    cuts = list(getattr(cut_timber, "cuts", []) or [])
    if len(local_csg.subtract) != len(cuts):
        return None  # shape changed under us; decline rather than guess
    for subtree, cutting in zip(local_csg.subtract, cuts):
        if subtree_contains(subtree, target):
            return cutting
    return None


def _joint_display_name(joint: 'Joint') -> str:
    """How to show *joint* wherever a joint is named.

    The one implementation of that rule, in name-then-type-then-id order:
    the name its ticket was given, else the kind of joint it is, else its
    kumiki id. The id rather than a shared placeholder because several
    unnamed joints can touch one timber, and "which of these did I just
    click?" is the question the display exists to answer. It is runtime-only,
    which is fine here -- this string is shown, never stored.

    The layers payload and the CSG tree both call this. They used to derive
    it separately and disagree: a joint with a type but no name showed as its
    type in the joint list and as an id everywhere else.
    """
    from kumiki.ticket import UNNAMED_TICKET_PATH

    ticket = getattr(joint, "ticket", None)
    if ticket is None:
        return "<unnamed joint>"  # no ticket, so no id to distinguish it by
    name = ticket.get_name()
    if name and name != UNNAMED_TICKET_PATH:
        return name
    joint_type = getattr(ticket, "joint_type", None)
    if joint_type:
        return joint_type
    return f"<unnamed joint - {ticket.kumiki_id}>"


def _joint_for_cutting(cut_timber: 'CutTimber', cutting: 'Cutting') -> Optional['Joint']:
    """The joint that owns *cutting*, or None if none does."""
    return _joint_by_cutting_id(cut_timber).get(id(cutting))


def _joint_name_for_cutting(cut_timber: 'CutTimber', cutting: 'Cutting') -> Optional[str]:
    """Display name of the joint that owns *cutting*, or None if it owns none."""
    joint = _joint_for_cutting(cut_timber, cutting)
    return None if joint is None else _joint_display_name(joint)


class _CutAttribution(NamedTuple):
    """Which cutting -- and which joint -- a CSG node belongs to.

    Inherited by the whole subtree under a cutting's negative CSG, so the
    viewer can read attribution off any node instead of walking back up to the
    top tier to find it. All three fields are None for the timber body.

    joint_id is the joint ticket's kumiki_id as a string, matching the id the
    layers payload uses, so the joint list can join against it directly.
    """

    joint_name: Optional[str] = None
    joint_id: Optional[str] = None
    cut_index: Optional[int] = None


NO_CUT_ATTRIBUTION = _CutAttribution()


def _cut_attribution(
    joints_by_cutting: Dict[int, 'Joint'],
    cutting: 'Cutting',
    cut_index: int,
) -> _CutAttribution:
    """Attribution for one top-tier cutting, given a prebuilt joint lookup."""
    joint = joints_by_cutting.get(id(cutting))
    if joint is None:
        # The cut is real and indexable even when no joint claims it.
        return _CutAttribution(cut_index=cut_index)
    ticket = getattr(joint, "ticket", None)
    joint_id = None if ticket is None else str(ticket.kumiki_id)
    return _CutAttribution(_joint_display_name(joint), joint_id, cut_index)


def _joint_name_for_node(
    local_csg: 'CutCSG',
    cut_timber: 'CutTimber',
    target: 'CutCSG',
) -> Optional[str]:
    """Display name of the joint that produced *target*, if any."""
    cutting = _cutting_for_node(local_csg, cut_timber, target)
    if cutting is None:
        return None
    return _joint_name_for_cutting(cut_timber, cutting)


def _declared_feature_names(csg: 'CutCSG') -> List[str]:
    """Names of the features *csg* declares, in declaration order."""
    names: List[str] = []
    for declared in csg.get_declared_features():
        if declared.name not in names:
            names.append(declared.name)
    return names


def _describe_pick(
    target: 'CutCSG',
    local_csg: 'CutCSG',
    cut_timber: 'CutTimber',
    local_pt: 'Float3',
    eps: float,
    feature_label: Optional[str],
    feature_type: Optional[str] = None,
) -> NodeDescriptionWire:
    """Everything the selection display wants to say about one click.

    Kept separate from describe_leaf_csg, which runs per triangle during
    highlight extraction and must stay a cheap string lookup. This runs once.

    The three CSG-ish arguments are all about one timber and are easy to
    confuse, so, concretely:

    Args:
        target: the node the click resolved to. An ordinary click drills
            straight to a leaf primitive; a ctrl-click descends one level at a
            time, so under ctrl this is often a compound -- a SolidUnion or a
            Difference selected whole.
        local_csg: the ROOT of the tree `target` sits in, i.e.
            ``cut_timber.render_timber_with_cuts_csg_local()``. Needed because
            two of the four answers are about where `target` sits in the tree
            rather than about `target` itself: which joint produced it, and how
            many Difference.subtract edges lie above it (which decides whether
            its outward normal points the way the visible surface does).
        cut_timber: the timber that owns that tree. Supplies `cuts`, which line
            up with the root Difference's subtract children, and `joints`,
            which map a cutting back to the joint that made it.
        local_pt: the clicked point in TIMBER-LOCAL coordinates -- the same space as
            `local_csg` and `target`, not global. The caller converts.
        eps: surface tolerance for the hit, covering the gap between the
            analytic face and the triangulated mesh the ray struck.
        feature_label: the feature navigation actually resolved to, or None when
            the click selected `target` as a whole. Passed in rather than
            re-derived: asking `target` what lies under the point finds a face
            on a descendant even when no feature was selected, which made the
            display name a face while the highlight lit a whole union.
        feature_type: the type of that feature, when the caller already knows
            it. A derived edge has to be passed this way for the same reason
            its label does -- it belongs to two primitives, so `target` alone
            answers FACE for it. None means re-derive from `target`.

    Returns:
        nodeKind and nodeLabel, which always describe `target` itself;
        featureLabel, featureType and facesToward, which are None unless a
        feature was selected; and jointName, which is None for the timber's own
        body, since no joint produced that.
    """
    from kumiki.viewer.picking import outward_normal_and_face, to_v3, label_name
    from kumiki.csg.cutcsg import CSGFeatureType, FeatureTestTolerances

    described: NodeDescriptionWire = {
        "nodeKind": type(target).__name__,
        "nodeDisplayName": type(target).display_name(),
        "nodeLabel": label_name(target),
        "jointName": _joint_name_for_node(local_csg, cut_timber, target),
    }

    if feature_label is None:
        return {
            **described,
            "featureLabel": None,
            "featureType": None,
            "facesToward": None,
            "outwardNormal": None,
        }

    point = to_v3(local_pt)
    hit = target.find_first_feature(point, FeatureTestTolerances(face=eps))
    resolved_type = feature_type
    if resolved_type is None and hit is not None:
        resolved_type = hit.feature_type().name
    normal, faces_toward = outward_normal_and_face(target, local_csg, local_pt, eps)
    return {
        **described,
        # featureLabel is only a name when the primitive declared one. Without
        # that it is describe_leaf_csg's geometric guess, which the display
        # must not present as a name -- it is a direction, and one that has not
        # been sign-corrected, unlike the normal below.
        "featureLabel": feature_label,
        "featureType": resolved_type,
        "facesToward": faces_toward,
        "outwardNormal": normal,
    }


def _pick_reference(
    local_csg: 'CutCSG',
    member_key: str,
    node_path: List[str],
    feature_label: Optional[str],
    feature_type: Optional[str],
    edge: Optional['CSGFeature'] = None,
) -> Optional[AnchorWire]:
    """The reference a measurement would hold for what was just picked.

    None while a click is still drilling down through compounds and has not
    reached a feature, and None for a derived feature whose parents cannot both
    be placed in the tree -- neither is something to measure to yet.
    """
    from kumiki.viewer.picking import node_positions
    from kumiki.identity import (DerivedFeaturePath, FeatureRef, ResolvedTimberPath,
                                 SingleFeaturePath)

    if feature_label is None:
        return None
    timber = ResolvedTimberPath.parse(member_key)

    if edge is not None:
        positions = node_positions(local_csg)
        parents = []
        for hit in getattr(edge, "parents", (None, None)):
            if hit is None or id(hit.owner) not in positions:
                return None
            parents.append(FeatureRef(tuple(positions[id(hit.owner)][2]), hit.feature.name))
        return serialize_feature_path(DerivedFeaturePath(
            timber=timber, a=parents[0], b=parents[1],
            kind="POINT" if feature_type == "POINT" else "EDGE"))

    return serialize_feature_path(SingleFeaturePath(
        timber=timber,
        ref=FeatureRef(tuple(node_path), feature_label),
        feature_type=feature_type,
    ))


def _handle_hover_feature_at_point(
    state: RunnerState, payload: PickRequest, slot_state: Optional['SlotState'] = None,
) -> PickResultWire:
    """What the pointer is over: the answer a click would give, without clicking.

    Deliberately the same code, not a cheaper likeness of it. An outline drawn
    from the CSG was cheaper and was wrong in a way that showed: a face comes
    back convex, so a timber face with mortises through it outlined as a whole
    rectangle over the openings, and a face half cut away outlined at full size.
    Hover exists to say what a click would take, so it has to be what a click
    would take -- the same mesh, the same feature, the same drilling.

    The viewer draws it in another colour and under the selection. That is the
    entire difference.

    Affordable because of when it is asked rather than how much it costs: the
    pointer has to settle first, so this runs once per rest, not once per move.
    """
    return _handle_find_csg_at_point(state, payload, slot_state)


def _pick_tolerances(payload: PickRequest, eps: float) -> 'FeatureTestTolerances':
    """How close a click has to be, given what the viewer says a pixel is worth.

    A face is clicked directly, so its slack is the gap between the analytic
    surface and the triangulated mesh the ray hit -- a fixed distance, and eps
    is it. An edge or a vertex cannot be clicked exactly at all: selecting one
    means snapping, and how much slack that wants depends on how big the timber
    looks, not on how big it is. The viewer sends those two already converted
    from pixels to world units; without them the built-in defaults stand.

    Clamped at the bottom by eps, since no amount of zooming in makes a snap
    tighter than the mesh it is snapping on.
    """
    from kumiki.csg.cutcsg import FeatureTestTolerances

    sent = payload.get("tolerances")
    if not isinstance(sent, dict):
        return FeatureTestTolerances(face=eps)

    def scaled(name: str, fallback: Any) -> Any:
        value = sent.get(name)
        if not isinstance(value, (int, float)) or value <= 0:
            return fallback
        return max(float(value), eps)

    return FeatureTestTolerances(
        face=eps,
        edge=scaled("edge", FeatureTestTolerances().edge),
        point=scaled("point", FeatureTestTolerances().point),
    )


#: How an accessory -- a wedge, a peg -- is keyed in the mesh cache.
ACCESSORY_KEY_PREFIX = "accessory:"


def _candidates_wire(
    local_csg: 'CutCSG', feature_hits: List['OwnedFeatureHit'], visible_count: int,
) -> List[CandidateWire]:
    """The candidates under the pointer, for the viewer; those from *visible_count* on are hidden.

    Enough per candidate to answer "why that one" and "why not mine" from the viewer's own log,
    without turning the runner's pick log on: the ordering is (real, kind, declared, group,
    priority), and all of it is here.
    """
    from kumiki.viewer.picking import node_positions

    positions = node_positions(local_csg)
    return [
        {
            "label": hit.feature.name,
            "type": hit.feature.feature_type().name,
            "real": bool(hit.feature.real),
            "derived": bool(hit.feature.is_derived()),
            "group": hit.feature.group.name,
            "priority": int(hit.feature.priority),
            # Where it is declared, which tells apart two features named alike.
            "path": positions.get(id(hit.owner), (0, 0, []))[2],
            # Under the pointer but not seen there: offered greyed, never taken.
            "hidden": index >= visible_count,
        }
        for index, hit in enumerate(feature_hits)
    ]


def _nothing_at_point(member_key: str) -> PickResultWire:
    """A pick that found nothing, in the shape every pick answer takes.

    Every key the viewer reads, so nothing it displays is left holding what the
    last answer said.
    """
    return {
        "memberKey": member_key,
        "path": [],
        "reference": None,
        "candidateCount": 0,
        "candidates": [],
        "candidateIndex": None,
        "geometry": None,
        "at": None,
        "verdict": None,
        "featureLabel": None,
        "featureType": None,
        "facesToward": None,
        "outwardNormal": None,
        "nodeDisplayName": None,
        "nodeLabel": None,
        "jointName": None,
        "highlightMesh": {"vertices": [], "indices": []},
        "stats": {"meshWalkMs": 0.0, "trianglesMatched": 0, "totalTriangles": 0},
    }


def _handle_find_csg_at_point(state: RunnerState, payload: PickRequest, slot_state: Optional['SlotState'] = None) -> PickResultWire:
    """Process a find_csg_at_point request and return the result dict."""
    from kumiki.drawings.drawing import MeasurementSpace
    from kumiki.viewer.picking import (best_matching_candidate, build_inv_transform_float, choose,
                                       edge_highlight_segments, extract_highlight_mesh, find_candidates,
                                       inv_transform_point, navigate, non_real_plane_outline,
                                       resolve_csg_at_path)
    ss = slot_state if slot_state is not None else state._active
    member_key = payload.get("memberKey")
    point = payload.get("point")
    current_path = payload.get("currentPath") or []
    # A drawing's view picks features directly, every timber alike: there is no drilling down the
    # tree there, so Ctrl is a plain click.
    ctrl_click = bool(payload.get("ctrlClick", False)) and payload.get("space") != MeasurementSpace.PROJECTED.value
    eps = 5e-4  # generous epsilon for raycast-based click points
    # Edge and vertex slack scaled to what a pixel is worth where the click
    # landed, which the viewer works out and sends. See _pick_tolerances.
    tolerances = _pick_tolerances(payload, eps)

    if not isinstance(member_key, str) or member_key not in ss.mesh_cache:
        raise ValueError(f"Unknown memberKey: {member_key}")
    if not isinstance(point, list) or len(point) != 3:
        raise ValueError("point must be [x, y, z]")

    if member_key.startswith(ACCESSORY_KEY_PREFIX):
        # A wedge or a peg. It is drawn, so a ray hits it, and it is cached with
        # a mesh and nothing else -- no CSG, no declared features, nothing
        # inside one to pick. So: nothing here, rather than an error.
        #
        # It has to be an answer and not a raise because the HOVER asks about
        # whatever the pointer crosses. A raise there is reported once and then
        # suppressed, which left hover silently dead for the rest of the session
        # after the pointer passed over a single wedge. Reaching one got easier
        # when a click began drilling straight in while measuring, since it no
        # longer has to be selected first.
        return _nothing_at_point(member_key)

    cached = ss.mesh_cache[member_key]
    local_csg = cached.get("local_csg")
    cut_timber = cached.get("cut_timber")
    mesh = cached.get("mesh")

    if local_csg is None or cut_timber is None or mesh is None:
        # A TIMBER with nothing cached is a real fault -- they are cached with
        # their CSG or not at all -- so this still raises.
        raise ValueError(f"No CSG data cached for {member_key}")

    timber = cut_timber.timber
    timber_rot, timber_pos = build_inv_transform_float(timber.transform)

    # Convert global click point to timber-local
    local_pt = inv_transform_point(timber_rot, timber_pos, point)

    t0 = time.monotonic()

    # Three steps, kumiki's (picking.py): where navigating the tree lands, what is under the pointer,
    # and which of it is wanted -- named by the caller (Tab, the menu), else the one that finishes the
    # measurement in hand, else the first in a drawing, else what navigation found.
    in_drawing = _pick_space(payload) is MeasurementSpace.PROJECTED
    local_ray = _local_ray_from_payload(payload, timber_rot, timber_pos)
    navigated = navigate(local_csg, local_pt, eps, ctrl_click, current_path)
    blocked = (_sight_blocker(ss, cut_timber, local_csg, payload, local_ray[1])
               if in_drawing and local_ray is not None else None)
    found = find_candidates(local_csg, local_pt, eps, tolerances, local_ray, in_drawing, blocked)
    feature_hits, visible_count = found
    if in_drawing and local_ray is not None and not visible_count and not ctrl_click:
        # Only hidden features here: nothing to take, but the menu still lists them, greyed.
        return {**_nothing_at_point(member_key),
                "candidates": _candidates_wire(local_csg, feature_hits, visible_count)}
    held = _geometry_from_wire(payload.get("heldGeometry")) if payload.get("heldGeometry") else None
    look = payload.get("look")
    space = _pick_space(payload)
    pick = choose(local_csg, navigated, found, payload.get("candidateIndex"),
                  lambda hits: best_matching_candidate(hits, timber, held, look, space), in_drawing, ctrl_click)
    new_path, target_csg, feature_label = pick.path, pick.node, pick.label
    feature_type, edge = pick.kind, pick.edge

    parent_csg = None
    if new_path:
        parent_csg = resolve_csg_at_path(local_csg, new_path, local_pt, eps)

    # An edge is drawn as a line whether it was derived or declared: a timber's
    # own arris needs the line as much as a joint's does, and without this it
    # was picked and then nothing was drawn for it.
    highlight_edge = None
    edge_absent = False
    edge_feature = pick.edge_feature
    located_pick: Optional['LocatedPick'] = pick.located()
    if edge_feature is not None:
        highlight_edge, edge_absent = edge_highlight_segments(
            edge_feature, target_csg, timber, local_csg,
        )
    elif located_pick is not None:
        highlight_edge = non_real_plane_outline(located_pick[0], located_pick[1], timber, local_csg)

    # Extract highlight mesh for the selected target
    hl_verts, hl_idx, matched, total = extract_highlight_mesh(
        mesh["vertices"],
        mesh["indices"],
        target_csg,
        timber_rot,
        timber_pos,
        eps,
        root_csg=local_csg,
        selected_path=new_path,
        selected_ref=parent_csg if feature_label is not None else target_csg,
        feature_label=feature_label,
        edge_feature=edge if (highlight_edge is None and not edge_absent) else None,
        feature_type=feature_type,
    )

    # When a feature (face) is selected, also extract the parent labeled CSG mesh
    # so the viewer can render the parent dimmer and the feature brighter.
    parent_hl: Optional[MeshWire] = None
    if feature_label is not None and parent_csg is not None:
        p_verts, p_idx, _, _ = extract_highlight_mesh(
            mesh["vertices"],
            mesh["indices"],
            parent_csg,
            timber_rot,
            timber_pos,
            eps,
            root_csg=local_csg,
            selected_path=new_path,
            selected_ref=parent_csg,
        )
        if p_verts:
            parent_hl = MeshWire(vertices=p_verts, indices=p_idx)

    mesh_walk_ms = (time.monotonic() - t0) * 1000.0

    result: PickResultWire = {
        # Echoed back because the viewer can have several timbers selected at
        # once, so it cannot infer which one a result belongs to.
        "memberKey": member_key,
        "path": new_path,
        # What a measurement would hold if this pick became one. Built here
        # because only the runner can see the CSG a path has to be read against
        # -- an edge in particular is not a feature anyone declared, so it has
        # to name the two faces that form it.
        "reference": _pick_reference(
            local_csg, member_key, new_path, feature_label, feature_type, edge,
        ),
        # How many features are at this point, so the viewer knows how many
        # there are to step through, and what they are called, so it can offer
        # them by name rather than as "the next one".
        # Only those that can be taken: Tab steps through these.
        "candidateCount": visible_count,
        "candidates": _candidates_wire(local_csg, feature_hits, visible_count),
        # And WHICH of them this answer is, so the viewer can mark the one it is
        # showing -- the right-click menu lights the row the view is lighting,
        # rather than keeping a second opinion about which that is.
        #
        # Matched by name at the end rather than recorded on the way: the choice
        # can come from a named index, from the preference when none was named,
        # or from one of the fallbacks, and all of them have to be reported the
        # same way.
        "candidateIndex": next(
            (index for index, hit in enumerate(feature_hits) if hit is pick.hit), None),
        # Where the feature is, unbounded, in world space. What decides whether
        # a pair can be dimensioned is what each PROJECTS to, and the viewer
        # projects on every pointer move -- so it gets the plane or the line and
        # works that out itself between asking.
        "geometry": (_world_geometry_payload(_handle_of(located_pick[0], located_pick[1], timber))
                     if located_pick is not None else None),
        # And where a dimension would attach, cropped to the solid the cuts have
        # left, which is the same anchor the saved measurement resolves to. An
        # edge in particular anchors at the middle of its longest surviving
        # piece, not at the extent it was declared with.
        "at": (_anchor_floats(_handle_of(located_pick[0], located_pick[1], timber), local_csg)
               if located_pick is not None else None),
        # What a measurement to this pick would BE: one answer, asked once, and
        # read by the hover colour, the preview and the click alike. See
        # .claude/plans/measuring-states.md -- three readers deriving it separately is
        # what every measurement bug on this branch came down to.
        "verdict": _pick_verdict(state, located_pick, timber, payload, slot_state),
        # What was selected, and the feature within it if navigation resolved
        # one. feature_label is None while a click is still drilling down
        # through compounds, and the display has to say so rather than name a
        # face belonging to something further in.
        **_describe_pick(target_csg, local_csg, cut_timber, local_pt, eps, feature_label, feature_type),
        "derivation": _derivation_wire(
            local_csg, feature_hits, edge if edge is not None and edge.name == feature_label else None),
        "highlightMesh": {
            "vertices": hl_verts,
            "indices": hl_idx,
        },
        "stats": {
            "meshWalkMs": round(mesh_walk_ms, 2),
            "trianglesMatched": matched,
            "totalTriangles": total,
        },
    }
    if parent_hl is not None:
        result["parentHighlightMesh"] = parent_hl
    if highlight_edge is not None:
        # A list: a cut through the middle of an edge leaves a piece either side.
        result["highlightEdgeSegments"] = highlight_edge
    _log_pick(member_key, local_pt, tolerances, feature_hits, result)
    return result


def _log_pick(
    member_key: str, local_pt: 'Float3', tolerances: 'FeatureTestTolerances',
    feature_hits: List['OwnedFeatureHit'], result: PickResultWire,
) -> None:
    """One line per pick saying what was under the pointer, when asked for.

    Off unless KIGUMI_PICK_LOG is set, because hover asks this on every rest of
    the pointer and the output channel is shared with everything else.

    It reports every candidate rather than the chosen one, and marks the choice,
    because the question it exists to answer is usually "why did it pick THAT"
    or "why is the thing I want not in the list at all" -- and neither is
    answerable from the winner alone. The tolerances go out with it since what
    is in the list depends on them.
    """
    if not os.environ.get("KIGUMI_PICK_LOG"):
        return

    chosen = result.get("candidateIndex")
    where = ", ".join(f"{float(axis):.4f}" for axis in local_pt)
    log_stderr(
        f"[pick] {member_key} at ({where}) local"
        f"  face={float(tolerances.face) * 1000:.2f}mm"
        f" edge={float(tolerances.edge) * 1000:.2f}mm"
        f" point={float(tolerances.point) * 1000:.2f}mm"
    )
    if not feature_hits:
        log_stderr("[pick]   no features here")
    for index, hit in enumerate(feature_hits):
        feature = hit.feature
        log_stderr(
            f"[pick]   {'>' if index == chosen else ' '} [{index}]"
            f" {feature.feature_type().name:5}"
            f" {'derived ' if feature.is_derived() else 'declared'}"
            f" real={str(feature.real):5}"
            f" group={feature.group.name:14}"
            f" prio={feature.priority:<5}"
            f" {feature.name}"
        )
    log_stderr(
        f"[pick]   -> path={result.get('path')}"
        f" feature={result.get('featureLabel')!r}"
        f" type={result.get('featureType')!r}"
    )


def _handle_find_csg_by_path(state: RunnerState, payload: PathPickRequest, slot_state: Optional['SlotState'] = None) -> PickResultWire:
    """Resolve a CSG at a known path and return highlight mesh for the viewer."""
    from kumiki.viewer.picking import (build_inv_transform_float, extract_highlight_mesh, label_name,
                                       non_real_plane_outline, resolve_csg_at_path)
    ss = slot_state if slot_state is not None else state._active
    member_key = payload.get("memberKey")
    path = payload.get("path") or []
    feature_label = payload.get("featureLabel") or None
    eps = 5e-4

    if not isinstance(member_key, str) or member_key not in ss.mesh_cache:
        raise ValueError(f"Unknown memberKey: {member_key}")
    if not isinstance(path, list) or len(path) == 0:
        raise ValueError("path must be a non-empty list of tag strings")

    cached = ss.mesh_cache[member_key]
    local_csg = cached.get("local_csg")
    cut_timber = cached.get("cut_timber")
    mesh = cached.get("mesh")

    if local_csg is None or cut_timber is None or mesh is None:
        raise ValueError(f"No CSG data cached for {member_key}")

    timber = cut_timber.timber
    timber_rot, timber_pos = build_inv_transform_float(timber.transform)

    # Resolve the CSG node at the given path (no point hint needed)
    target_csg = resolve_csg_at_path(local_csg, path, None, eps)

    # If a feature name was requested, confirm the target actually declares it.
    # The mesh target stays the CSG either way -- extract_highlight_mesh does
    # the per-face narrowing itself, via feature_label.
    actual_feature_label = None
    if feature_label and feature_label in _declared_feature_names(target_csg):
        actual_feature_label = feature_label

    hl_verts, hl_idx, matched, total = extract_highlight_mesh(
        mesh["vertices"],
        mesh["indices"],
        target_csg,
        timber_rot,
        timber_pos,
        eps,
        root_csg=local_csg,
        selected_path=path,
        selected_ref=target_csg,
        feature_label=actual_feature_label,
    )

    parent_hl: Optional[MeshWire] = None
    if actual_feature_label:
        p_verts, p_idx, _, _ = extract_highlight_mesh(
            mesh["vertices"],
            mesh["indices"],
            target_csg,
            timber_rot,
            timber_pos,
            eps,
            root_csg=local_csg,
            selected_path=path,
            selected_ref=target_csg,
        )
        if p_verts:
            parent_hl = MeshWire(vertices=p_verts, indices=p_idx)

    result: PickResultWire = {
        "memberKey": member_key,
        "path": path,
        "featureLabel": actual_feature_label,
        # Same two fields _describe_pick reports, so the display reads the same
        # whether a node was picked in 3D or clicked in the tree.
        "nodeKind": type(target_csg).__name__,
        "nodeDisplayName": type(target_csg).display_name(),
        "nodeLabel": label_name(target_csg),
        "highlightMesh": {
            "vertices": hl_verts,
            "indices": hl_idx,
        },
        "stats": {
            "trianglesMatched": matched,
            "totalTriangles": total,
        },
    }
    if parent_hl is not None:
        result["parentHighlightMesh"] = parent_hl
    if actual_feature_label:
        named = next((f for f in target_csg.get_declared_features() if f.name == actual_feature_label), None)
        outline = None if named is None else non_real_plane_outline(named, target_csg, cut_timber.timber, local_csg)
        if outline:
            result["highlightEdgeSegments"] = outline
    return result


def _resolve_slot(state: RunnerState, payload: Dict[str, Any]) -> SlotState:
    """Return the SlotState targeted by the request payload (defaults to active_slot),
    rebuilt first if the project's modules were re-imported since it was built."""
    slot_name = payload.get("slot", state.active_slot)
    slot = state.get_slot(slot_name)
    if slot.generation != _project_generation:
        slot = _rebuild_stale_slot(slot)
        state.slots[slot_name] = slot
        # Picks read the mesh cache, which the rebuild emptied.
        build_real_geometry(state, slot)
    return slot


def _rebuild_stale_slot(slot: SlotState) -> SlotState:
    """*slot* built again with the current modules, keeping its parameter values.

    The values go over as plain data: the old Kiwari, and any vector in it, are instances of
    the replaced classes. The mesh cache is not kept either, for the same reason.
    """
    log_stderr(f"[reload] Rebuilding {slot.file_path.name}: the project's modules were re-imported since it was built")
    values = {
        group.id: {key: group.kiwari.value_payload(key) for key in group.kiwari.declarations}
        for group in slot.kiwari_groups if group.kiwari is not None
    }
    if slot.single_pattern_name:
        rebuilt, _ = _raise_specific_pattern(str(slot.file_path), slot.single_pattern_name, kiwari_values=values)
        return rebuilt
    rebuilt = load_slot_state(str(slot.file_path))
    if values and rebuilt.kiwari_groups:
        rebuilt = load_slot_state(str(slot.file_path), kiwari_values=values, previous_groups=rebuilt.kiwari_groups)
    return rebuilt


def _resolve_slot_name(state: RunnerState, payload: Dict[str, Any]) -> str:
    return payload.get("slot", state.active_slot)


# ---------------------------------------------------------------------------
# Pattern discovery
# ---------------------------------------------------------------------------

_patterns_cache: Optional[PatternListWire] = None


def _list_available_patterns(force_rescan: bool = False) -> PatternListWire:
    """Scan shipped and local pattern folders and return pattern metadata.

    Results are cached after the first scan. Pass *force_rescan=True* (or
    send ``"rescan": true`` in the command payload) to re-import everything.
    """
    global _patterns_cache
    if _patterns_cache is not None and not force_rescan:
        return _patterns_cache

    t0 = time.monotonic()
    from kumiki.librarian import scan_library_index

    sources: List[PatternSourceWire] = []

    # Shipped patterns — bundled inside the kumiki package as kumiki/patterns/
    # (pip-installed) or at the sibling patterns/ folder in a dev checkout.
    def _extract_patterns_from_index(index: Any) -> List[PatternEntryWire]:
        items: List[PatternEntryWire] = []
        for pb_record in index.get("patternbooks", []):
            source_file = pb_record.get("file_path")
            for p in (pb_record.get("patterns") or []):
                path = p.get("path", "")
                tags = list(p.get("tags") or [])
                name = path.split("/")[-1] if path else ""
                items.append({
                    "path": path,
                    "name": name,
                    "tags": tags,
                    "groups": [],
                    "source_file": source_file,
                })
        return items

    try:
        import kumiki
        kumiki_dir = Path(kumiki.__file__).resolve().parent
        shipped_patterns_dir = kumiki_dir / "patterns"
        if not shipped_patterns_dir.is_dir():
            shipped_patterns_dir = kumiki_dir.parent / "patterns"
        if shipped_patterns_dir.is_dir():
            with contextlib.redirect_stdout(sys.stderr):
                index = scan_library_index(str(shipped_patterns_dir))
            patterns_list = _extract_patterns_from_index(index)
            if patterns_list:
                sources.append({"source": "shipped", "folder": str(shipped_patterns_dir), "patterns": patterns_list})
    except Exception as exc:
        log_stderr(f"[patterns] Error scanning shipped patterns: {exc}")

    # Local project patterns
    if _project_root is not None:
        local_patterns_dir = _project_root / "patterns"
        if local_patterns_dir.is_dir():
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    index = scan_library_index(str(local_patterns_dir))
                patterns_list = _extract_patterns_from_index(index)
                if patterns_list:
                    sources.append({"source": "local", "folder": str(local_patterns_dir), "patterns": patterns_list})
            except Exception as exc:
                log_stderr(f"[patterns] Error scanning local patterns: {exc}")

    scan_s = time.monotonic() - t0
    total_patterns = sum(len(s["patterns"]) for s in sources)
    log_stderr(f"[patterns] Scanned {total_patterns} patterns in {scan_s:.2f}s")
    result = PatternListWire(sources=sources, scan_s=scan_s)
    _patterns_cache = result
    return result


def _find_pattern_in_list(pattern_list: List[Any], pattern_name: str) -> Optional[Any]:
    """Find a Pattern in a List[Pattern] by path or name."""
    for p in pattern_list:
        path = getattr(p, "path", "")
        if path == pattern_name or path.split("/")[-1] == pattern_name:
            return p
    return None


def _raise_specific_pattern(
    source_file: str,
    pattern_name: str,
    kiwari_values: Optional[Mapping[str, Any]] = None,
) -> Tuple[SlotState, SlotLoadedWire]:
    """Load a specific pattern from a source file and return (SlotState, result_dict)."""
    resolved = Path(source_file).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Pattern source file not found: {resolved}")

    t0 = time.monotonic()
    module = load_module_from_path(resolved, verbose=True)

    pattern_list = _module_patterns(module)
    if pattern_list:
        pattern = _find_pattern_in_list(pattern_list, pattern_name)
        if pattern is None:
            available = [getattr(p, "path", "") for p in pattern_list]
            raise ValueError(f"Pattern '{pattern_name}' not found. Available: {available}")

        from kumiki.rule import create_v3, scalar
        origin = create_v3(scalar(0), scalar(0), scalar(0))
        # A pattern declares its kiwari on the Pattern, so the schema is
        # readable without building -- raise_at binds the values onto it and
        # hands the result in only if this pattern takes one.
        values = (kiwari_values or {}).get(pattern.path)
        bound = _bind_kiwari_values(pattern.kiwari, values if isinstance(values, Mapping) else None)
        with contextlib.redirect_stdout(sys.stderr):
            pattern_result = pattern.raise_at(origin, bound)
        frame = _coerce_viewable_frame(pattern_result, f"Pattern '{pattern.name}'")

        reload_s = time.monotonic() - t0
        slot = SlotState(
            file_path=resolved,
            module=module,
            frame=frame,
            mesh_cache={},
            patternbook=pattern_list,
            single_pattern_name=pattern.path,
            kiwari_groups=(KiwariGroup((pattern.path,), bound),) if bound is not None else (),
            generation=_project_generation,
        )
        result: SlotLoadedWire = {
            "examplePath": str(resolved),
            "patternName": pattern.path,
            "frame": {
                "name": frame.name if hasattr(frame, "name") else pattern.name,
                "timber_count": len(frame.cut_timbers),
                "accessories_count": len(frame.accessories) if hasattr(frame, "accessories") else 0,
            },
            "kiwari": _serialize_kiwari_for_slot(slot),
            "profiling": {"reload_s": reload_s},
        }
        return slot, result

    raise ValueError(
        f"No patterns found in {source_file}. A pattern book marks each pattern with "
        "@pattern(\"group/name\") above the function that builds it."
    )


def _opt_mapping(payload: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    """Return payload[key] if it is a dict, else None."""
    value = payload.get(key)
    return value if isinstance(value, dict) else None


def _require_str(payload: Dict[str, Any], key: str, message: str) -> str:
    """Return payload[key] if it is a non-empty string, else raise ValueError(message)."""
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(message)
    return value


_active_assembly_cancels: Dict[str, threading.Event] = {}

def _cancel_active_assembly(slot_name: str) -> None:
    event = _active_assembly_cancels.pop(slot_name, None)
    if event is not None:
        event.set()


def handle_request(state: RunnerState, request: Dict[str, Any]) -> Tuple[RunnerState, ResponseWire, bool]:
    request_id = request.get("id")
    command = request.get("command")
    payload = request.get("payload") or {}

    if not isinstance(command, str):
        raise ValueError("Request must include a string 'command'")

    if command == "ping":
        return state, make_success_response(request_id, command, {"pong": True}), False

    if command == "reload_example":
        slot_name = _resolve_slot_name(state, payload)
        _cancel_active_assembly(slot_name)
        old_slot = state.slots.get(slot_name)
        next_path = payload.get("filePath", str(state.get_slot(slot_name).file_path))
        kiwari_values = _opt_mapping(payload, "kiwari")
        old_cache = old_slot.mesh_cache if old_slot else {}
        t0 = time.monotonic()

        # If this slot was loaded for a single pattern, re-raise just that pattern
        if old_slot and old_slot.single_pattern_name:
            next_slot, _ = _raise_specific_pattern(
                next_path,
                old_slot.single_pattern_name,
                kiwari_values=kiwari_values,
            )
            next_slot.mesh_cache = old_cache
        else:
            next_slot = load_slot_state(
                next_path,
                old_cache,
                kiwari_values=kiwari_values,
                previous_groups=old_slot.kiwari_groups if old_slot else (),
            )

        reload_s = time.monotonic() - t0
        state.slots[slot_name] = next_slot
        frame_name = next_slot.frame.name if hasattr(next_slot.frame, "name") else "?"
        log_stderr(f"[reload] [{slot_name}] Frame loaded: '{frame_name}', {len(next_slot.frame.cut_timbers)} timbers")
        result = {
            "examplePath": str(next_slot.file_path),
            "frame": {
                "name": next_slot.frame.name,
                "timber_count": len(next_slot.frame.cut_timbers),
                "accessories_count": len(next_slot.frame.accessories),
            },
            "kiwari": _serialize_kiwari_for_slot(next_slot),
            "profiling": {"reload_s": reload_s},
        }
        return state, make_success_response(request_id, command, result), False

    if command == "get_frame":
        ss = _resolve_slot(state, payload)
        frame_payload = serialize_frame(ss.frame)
        frame_payload["kiwari"] = _serialize_kiwari_for_slot(ss)
        return state, make_success_response(request_id, command, frame_payload), False

    if command == "get_drawings":
        ss = _resolve_slot(state, payload)
        return state, make_success_response(request_id, command, {
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
        }), False

    if command == "save_drawings":
        # Everything at once, and only what the file is responsible for.
        ss = _resolve_slot(state, payload)
        drawings = collect_drawings(ss.frame, ss.file_path, ss.pending_drawings)
        written = write_drawings_file(ss.file_path, drawings)
        # They are the file's now, so nothing is pending and the next read finds
        # them there. Keeping them would give the same drawing two answers.
        ss.pending_drawings = []
        return state, make_success_response(request_id, command, {
            "path": written,
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
        }), False

    if command == "add_measurement":
        ss = _resolve_slot(state, payload)
        _check_plane_matches_view(
            collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
            str(payload.get("drawingId") or ""), str(payload.get("viewportId") or ""), payload.get("plane"))
        add_measurement(
            ss.frame, ss.file_path, ss.pending_drawings,
            str(payload.get("drawingId") or ""),
            str(payload.get("viewportId") or ""),
            _requested_measure(payload, whole=True),
        )
        return state, make_success_response(request_id, command, {
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
        }), False

    if command == "update_measurement":
        ss = _resolve_slot(state, payload)
        update_measurement(
            ss.frame, ss.file_path, ss.pending_drawings,
            str(payload.get("drawingId") or ""),
            str(payload.get("viewportId") or ""),
            _requested_measure(payload),
            cast(MeasurementRequest, payload).get("changes") or MeasureWire(),
        )
        return state, make_success_response(request_id, command, {
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
        }), False

    if command == "feature_highlights":
        ss = _resolve_slot(state, payload)
        references = payload.get("references")
        if not isinstance(references, list):
            raise ValueError("feature_highlights requires payload.references, a list")
        return state, make_success_response(request_id, command, {
            "highlights": feature_highlights(ss, references),
        }), False

    if command == "restore_measurement":
        ss = _resolve_slot(state, payload)
        restore_measurement(
            ss.frame, ss.file_path, ss.pending_drawings,
            str(payload.get("drawingId") or ""),
            str(payload.get("viewportId") or ""),
            _requested_measure(payload),
        )
        return state, make_success_response(request_id, command, {
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
        }), False

    if command == "delete_measurement":
        ss = _resolve_slot(state, payload)
        delete_measurement(
            ss.frame, ss.file_path, ss.pending_drawings,
            str(payload.get("drawingId") or ""),
            str(payload.get("viewportId") or ""),
            _requested_measure(payload),
        )
        return state, make_success_response(request_id, command, {
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
        }), False

    if command == "create_drawing_from_selection":
        ss = _resolve_slot(state, payload)
        drawing = create_drawing_from_selection(ss.frame, payload.get("member_keys") or [])
        existing = collect_drawings(ss.frame, ss.file_path, ss.pending_drawings)
        drawing["id"] = _unique_drawing_id(drawing["name"], {d["id"] for d in existing})
        # The name follows the id, so drawing the same piece twice gives two
        # rows you can tell apart rather than two called the same thing.
        drawing["name"] = drawing["id"]
        drawing["origin"] = ORIGIN_FILE
        ss.pending_drawings.append(drawing)
        return state, make_success_response(request_id, command, {
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
            "enterId": drawing["id"],
        }), False

    if command == "get_default_drawing_for_debugging":
        # Testing scaffolding; see build_default_drawing_for_debugging. Kept out
        # of the frame payload so a drawing never re-serializes geometry.
        ss = _resolve_slot(state, payload)
        drawing = build_default_drawing_for_debugging(ss.frame)
        return state, make_success_response(request_id, command, {"scenes": [drawing]}), False

    if command == "get_layers_tree":
        ss = _resolve_slot(state, payload)
        return state, make_success_response(request_id, command, serialize_layers(ss.frame, ss.frame_parts)), False

    if command == "get_assembly":
        # Deferred from get_layers_tree so the frame renders before the
        # (potentially slow) disassembly solve runs.
        slot_name = _resolve_slot_name(state, payload)
        ss = _resolve_slot(state, payload)

        _cancel_active_assembly(slot_name)
        cancel_event = threading.Event()
        _active_assembly_cancels[slot_name] = cancel_event

        log_stderr(f"[assembly] [{slot_name}] Starting async background assembly solve for frame '{getattr(ss.frame, 'name', '?')}' ({len(ss.frame.cut_timbers)} timbers)...")
        t0 = time.monotonic()

        def _worker() -> None:
            try:
                timber_entries, accessory_entries = _assign_member_keys(ss.frame)
                payload_data = _build_assembly_payload(
                    ss.frame, timber_entries, accessory_entries, should_cancel=cancel_event.is_set
                )
                assembly_s = time.monotonic() - t0
                _active_assembly_cancels.pop(slot_name, None)
                if not cancel_event.is_set():
                    log_stderr(f"[assembly] [{slot_name}] Background assembly solve completed in {assembly_s:.3f}s")
                    emit_message({
                        "type": "assembly_result",
                        "slot": slot_name,
                        "result": {"assembly": payload_data},
                        "profiling": {"assembly_s": assembly_s},
                    })
                else:
                    log_stderr(f"[assembly] [{slot_name}] Background assembly solve canceled after {assembly_s:.3f}s")
            except Exception as exc:
                _active_assembly_cancels.pop(slot_name, None)
                if not cancel_event.is_set():
                    log_stderr(f"[assembly] [{slot_name}] Background assembly solve failed: {exc}")

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        return state, make_success_response(request_id, command, {"assembly": {"pending": True}}), False

    if command == "get_csg_tree":
        ss = _resolve_slot(state, payload)
        member_key = _require_str(payload, "memberKey", "get_csg_tree requires payload.memberKey")
        cached = ss.mesh_cache.get(member_key)
        cut_timber = cached.get("cut_timber") if cached else None
        if cut_timber is None:
            # Fall back to scanning frame for the matching memberKey by name+occurrence.
            timber_entries, _ = _assign_member_keys(ss.frame)
            match = next((e for e in timber_entries if e["memberKey"] == member_key), None)
            if match is None:
                raise ValueError(f"Unknown memberKey: {member_key}")
            cut_timber = match["cutTimber"]
        result = serialize_cut_csg_tree(cut_timber)
        result["memberKey"] = member_key
        return state, make_success_response(request_id, command, result), False

    if command == "get_geometry":
        ss = _resolve_slot(state, payload)
        t0 = time.monotonic()
        geometry = build_real_geometry(state, ss)
        geometry_s = time.monotonic() - t0
        geometry["profiling"] = {"geometry_s": geometry_s}
        return state, make_success_response(request_id, command, geometry), False

    if command == "hover_feature_at_point":
        ss = _resolve_slot(state, payload)
        result = _handle_hover_feature_at_point(state, cast(PickRequest, payload), ss)
        return state, make_success_response(request_id, command, result), False

    if command == "find_csg_at_point":
        ss = _resolve_slot(state, payload)
        result = _handle_find_csg_at_point(state, cast(PickRequest, payload), ss)
        return state, make_success_response(request_id, command, result), False

    if command == "find_csg_by_path":
        ss = _resolve_slot(state, payload)
        result = _handle_find_csg_by_path(state, cast(PathPickRequest, payload), ss)
        return state, make_success_response(request_id, command, result), False

    # --- Slot management ---

    if command == "load_slot":
        slot_name = _require_str(payload, "slot", "load_slot requires payload.slot")
        _cancel_active_assembly(slot_name)
        file_path = _require_str(payload, "filePath", "load_slot requires payload.filePath")
        t0 = time.monotonic()
        new_slot = load_slot_state(file_path, kiwari_values=_opt_mapping(payload, "kiwari"))
        reload_s = time.monotonic() - t0
        state.slots[slot_name] = new_slot
        log_stderr(f"[slot] Loaded slot '{slot_name}' from {file_path}")
        result = {
            "slot": slot_name,
            "examplePath": str(new_slot.file_path),
            "frame": {
                "name": new_slot.frame.name if hasattr(new_slot.frame, "name") else None,
                "timber_count": len(new_slot.frame.cut_timbers),
                "accessories_count": len(new_slot.frame.accessories) if hasattr(new_slot.frame, "accessories") else 0,
            },
            "kiwari": _serialize_kiwari_for_slot(new_slot),
            "profiling": {"reload_s": reload_s},
        }
        return state, make_success_response(request_id, command, result), False

    if command == "unload_slot":
        slot_name = _require_str(payload, "slot", "unload_slot requires payload.slot")
        _cancel_active_assembly(slot_name)
        if slot_name == state.active_slot:
            raise ValueError(f"Cannot unload the active slot '{slot_name}'")
        removed = slot_name in state.slots
        if removed:
            del state.slots[slot_name]
            log_stderr(f"[slot] Unloaded slot '{slot_name}'")
        return state, make_success_response(request_id, command, {"slot": slot_name, "removed": removed}), False

    if command == "list_slots":
        slot_info = {}
        for name, ss in state.slots.items():
            slot_info[name] = {
                "filePath": str(ss.file_path),
                "frameName": ss.frame.name if hasattr(ss.frame, "name") else None,
                "timberCount": len(ss.frame.cut_timbers),
            }
        return state, make_success_response(request_id, command, {
            "slots": slot_info,
            "activeSlot": state.active_slot,
        }), False

    # --- Tools ---

    if command == "list_tools":
        return state, make_success_response(request_id, command, _serialize_tools(_resolve_slot(state, payload))), False

    if command == "run_tool":
        name = _require_str(payload, "name", "run_tool requires payload.name")
        return state, make_success_response(request_id, command, run_tool(_resolve_slot(state, payload), name)), False

    # --- Pattern discovery ---

    if command == "list_available_patterns":
        force_rescan = bool(payload.get("rescan", False))
        result = _list_available_patterns(force_rescan=force_rescan)
        return state, make_success_response(request_id, command, result), False

    if command == "raise_specific_pattern":
        slot_name = _require_str(payload, "slot", "raise_specific_pattern requires payload.slot")
        source_file = _require_str(payload, "sourceFile", "raise_specific_pattern requires payload.sourceFile")
        pattern_name = _require_str(payload, "patternName", "raise_specific_pattern requires payload.patternName")
        new_slot, result = _raise_specific_pattern(
            source_file, pattern_name, kiwari_values=_opt_mapping(payload, "kiwari")
        )
        state.slots[slot_name] = new_slot
        result["slot"] = slot_name
        log_stderr(f"[slot] Raised pattern '{pattern_name}' in slot '{slot_name}'")
        return state, make_success_response(request_id, command, result), False

    if command == "save_parameters":
        ss = _resolve_slot(state, payload)
        written = _write_parameters_file(ss)
        log_stderr(f"[parameters] Saved to {written}")
        return state, make_success_response(request_id, command, {
            "path": written,
            "saved": {group.id: list(group.kiwari.changed_from_defaults()) for group in ss.kiwari_groups},
        }), False

    if command == "export_member":
        ss = _resolve_slot(state, payload)
        member_key = payload.get("memberKey")
        export_format = str(payload.get("format", "stl")).lower()
        output_dir_raw = payload.get("outputDir")

        if export_format not in {"stl", "step"}:
            raise ValueError("export_member requires payload.format to be 'stl' or 'step'")
        if not isinstance(member_key, str) or not member_key:
            raise ValueError("export_member requires payload.memberKey")
        if not isinstance(output_dir_raw, str) or not output_dir_raw:
            raise ValueError("export_member requires payload.outputDir")

        output_dir = Path(output_dir_raw).resolve()
        if _project_root is not None:
            allowed_root = (_project_root / "kigumi_exports").resolve()
            try:
                output_dir.relative_to(allowed_root)
            except ValueError as exc:
                raise ValueError("export_member outputDir must be inside project kigumi_exports/") from exc

        timber_entries, _accessory_entries = _assign_member_keys(ss.frame)
        entry = next((e for e in timber_entries if e["memberKey"] == member_key), None)
        if entry is None:
            raise ValueError(f"Unknown memberKey: {member_key}")

        from kumiki.blueprint import export_cut_timber_stl, export_cut_timber_step

        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = entry["timber"].ticket.path or entry["displayName"]
        dest = output_dir / f"{base_name}.{export_format}"
        if export_format == "stl":
            export_cut_timber_stl(entry["cutTimber"], dest, local=True)
        else:
            export_cut_timber_step(entry["cutTimber"], dest, local=True)

        return state, make_success_response(request_id, command, {
            "format": export_format,
            "memberKey": member_key,
            "outputDir": str(output_dir),
            "files": [str(dest)],
        }), False

    if command == "export_frame":
        ss = _resolve_slot(state, payload)
        export_format = str(payload.get("format", "stl")).lower()
        output_dir_raw = payload.get("outputDir")
        include_combined = bool(payload.get("includeCombined", True))
        include_individuals = bool(payload.get("includeIndividuals", True))
        include_accessories = bool(payload.get("includeAccessories", True))

        if export_format not in {"stl", "step", "3mf", "obj"}:
            raise ValueError("export_frame requires payload.format to be 'stl', 'step', '3mf', or 'obj'")
        if not isinstance(output_dir_raw, str) or not output_dir_raw:
            raise ValueError("export_frame requires payload.outputDir")

        output_dir = Path(output_dir_raw).resolve()
        if _project_root is not None:
            allowed_root = (_project_root / "kigumi_exports").resolve()
            try:
                output_dir.relative_to(allowed_root)
            except ValueError as exc:
                raise ValueError("export_frame outputDir must be inside project kigumi_exports/") from exc

        from kumiki.blueprint import (
            export_frame_stl,
            export_frame_3mf,
            export_frame_obj,
            export_frame_step,
        )

        # export_format is validated above, and the file extension equals the
        # format name for every supported format — so combined_name/glob are
        # derived from it directly (no per-format string can drift).
        exporters = {
            "stl": export_frame_stl,
            "3mf": export_frame_3mf,
            "obj": export_frame_obj,
            "step": export_frame_step,
        }
        written = exporters[export_format](
            ss.frame,
            output_dir,
            combined=include_combined,
            include_accessories=include_accessories,
        )
        combined_name = f"_combined.{export_format}"
        extension_glob = f"*.{export_format}"

        if not include_individuals:
            for candidate in output_dir.glob(extension_glob):
                if candidate.name == combined_name:
                    continue
                try:
                    candidate.unlink()
                except OSError as exc:
                    log_stderr(f"Warning: failed to remove individual export '{candidate}': {exc}")

            combined_path = output_dir / combined_name
            written = [combined_path] if combined_path.exists() else []

        return state, make_success_response(request_id, command, {
            "format": export_format,
            "outputDir": str(output_dir),
            "includeCombined": include_combined,
            "includeIndividuals": include_individuals,
            "includeAccessories": include_accessories,
            "files": [str(path) for path in written],
            "count": len(written),
        }), False

    if command == "shutdown":
        return state, make_success_response(request_id, command, {"shutting_down": True}), True

    raise ValueError(f"Unknown command: {command}")


def main() -> None:
    if len(sys.argv) < 2:
        emit_message({
            "type": "fatal_error",
            "error": "No example file path provided",
        })
        sys.exit(1)

    target_path = sys.argv[1]

    log_stderr(f"[startup] runner.py ready. executable={sys.executable}")
    log_stderr(f"[startup] _project_root={_project_root}")
    log_stderr(f"[startup] target={target_path}")

    try:
        initial_slot = load_slot_state(target_path)
        state = RunnerState(slots={"main": initial_slot}, active_slot="main")
    except Exception as exc:
        emit_message({
            "type": "fatal_error",
            "error": {
                "message": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            },
        })
        sys.exit(1)

    emit_message(make_ready_event(state))

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        request_id = None
        command = "unknown"
        try:
            request = json.loads(line)
            request_id = request.get("id")
            command = request.get("command", "unknown")
            state, response, should_exit = handle_request(state, request)
            emit_message(response)
            if should_exit:
                return
        except Exception as exc:
            # A build that failed leaves the slot it failed on untouched, so
            # the kiwari it last built from still stands. Sending it back means
            # a value someone just typed wrong is still there to be dialled
            # back, rather than the panel emptying along with the frame.
            response = make_error_response(request_id, command, exc)
            failed_slot = state.slots.get(_resolve_slot_name(state, request.get("payload") or {}))
            if failed_slot is not None and failed_slot.kiwari_groups:
                response["kiwari"] = _serialize_kiwari_for_slot(failed_slot, stale=True)
            emit_message(response)


if __name__ == "__main__":
    main()
