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
LocalRay = Tuple[List[float], List[float]]

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
    start: Vec3
    end: Vec3


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
    outwardNormal: Optional[Vec3]


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
    from kumiki.drawings.drawing import (AngleRays, MeasureSpan, MeasurementKind, MeasurementSpace, VectorLike,
                                         Viewport, ViewAxes, ViewportId)
    from kumiki.drawings.layout import PlacedViewport
    from kumiki.geometry import Line, Plane, Point
    from kumiki.identity import FeaturePath
    from kumiki.kiwari import Kiwari
    from kumiki.ticket import Ticket
    from kumiki.timber import Accessory, CutTimber, Cutting, Frame, Joint, PerfectTimberWithin

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


def _build_perfect_timber_within_csg_local(cut_timber: 'CutTimber') -> 'CutCSG':
    """The perfect timber within with the same cuts applied, for previewing non-perfect timbers."""
    return cut_timber.render_perfect_timber_within_with_cuts_csg_local()


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
            perfect_csg = _build_perfect_timber_within_csg_local(cut_timber)
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
    from kumiki.picking import label_name
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

# Leaves a margin around the model rather than framing it edge to edge.
_DRAWING_EXTENT_PADDING = 1.15


def _cut_extent(cut_timber: 'CutTimber', stock_length: float) -> Tuple[float, float]:
    """Where the finished piece starts and ends along its own length.

    The same distinction the member list draws (see _cut_length): a timber with
    an end joint is not cut to length first, so its stock is not the piece that
    gets drawn. Framing a view on the stock leaves the piece sitting off centre
    by whatever the joint took off.
    """
    try:
        prism = cut_timber.get_perfect_timber_within_bounding_box_prism()
        start = float(prism.start_distance) if prism.start_distance is not None else 0.0
        end = float(prism.end_distance) if prism.end_distance is not None else stock_length
        return start, end
    except Exception as exc:
        log_stderr(f"Warning: could not measure cut extent: {exc}")
        return 0.0, stock_length


def _timber_world_corners(cut_timber: 'CutTimber') -> List[List[float]]:
    """The 8 corners of a timber's finished piece, in world space."""
    timber = cut_timber.timber
    origin = _vector3_to_floats(timber.get_bottom_position_global())
    along = _vector3_to_floats(timber.get_length_direction_global())
    across = _vector3_to_floats(timber.get_width_direction_global())
    up = _vector3_to_floats(timber.get_height_direction_global())
    length = float(timber.length)
    half_width = float(timber.size[0]) / 2.0
    half_height = float(timber.size[1]) / 2.0

    corners: List[List[float]] = []
    for distance in _cut_extent(cut_timber, length):
        for width_sign in (-half_width, half_width):
            for height_sign in (-half_height, half_height):
                corners.append([
                    origin[axis]
                    + along[axis] * distance
                    + across[axis] * width_sign
                    + up[axis] * height_sign
                    for axis in range(3)
                ])
    return corners


def _frame_world_bounds(frame: 'Frame') -> Tuple[List[float], List[float]]:
    """(centre, half_size) of everything in the frame; a unit box if it is empty."""
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for cut_timber in frame.cut_timbers:
        for corner in _timber_world_corners(cut_timber):
            for axis in range(3):
                lows[axis] = min(lows[axis], corner[axis])
                highs[axis] = max(highs[axis], corner[axis])

    if any(low == float("inf") for low in lows):
        return [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]

    centre = [(lows[axis] + highs[axis]) / 2.0 for axis in range(3)]
    half_size = [(highs[axis] - lows[axis]) / 2.0 for axis in range(3)]
    return centre, half_size


def _view_extent(
    half_size: List[float],
    right: List[float],
    up: List[float],
    aspect: float = 1.0,
) -> float:
    """Half-height that fits the model in a view with these screen axes.

    The viewer widens the frustum from the half-height by the viewport's aspect,
    so the width the model needs has to be divided by that aspect before the two
    are compared. Skipping that is only harmless while viewports are square; a
    long timber drawn across a wide strip needs far less height than its length.
    """
    def projected(axis: List[float]) -> float:
        return sum(abs(axis[i]) * half_size[i] for i in range(3))

    safe_aspect = aspect if aspect > 0 else 1.0
    needed = max(projected(up), projected(right) / safe_aspect)
    return max(0.001, needed * _DRAWING_EXTENT_PADDING)


def _viewport_aspect(rect: List[float], page: PageWire) -> float:
    """A viewport's aspect: its share of the sheet, times the sheet's own."""
    height = rect[3] * page["height"]
    return (rect[2] * page["width"]) / height if height > 0 else 1.0


def _dot(a: List[float], b: List[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: List[float], b: List[float]) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _camera_looking_at_face(normal: List[float], along: List[float]) -> CameraWire:
    """A camera frame square-on to a face, with the timber's length across screen.

    The camera sits outside the face along its outward normal and looks back at
    it. `up` is chosen so right x up == -look, the frame of a camera looking down
    its own -Z, which is what keeps the view from coming out mirrored.
    """
    return {
        "right": list(along),
        "up": _cross(normal, along),
        "look": [-component for component in normal],
    }


def build_default_drawing_for_debugging(frame: 'Frame') -> DrawingWire:
    """A four-viewport scene over the whole frame: three elevations and a preview.

    Testing scaffolding -- see the note at the top of this section. The three
    orthographic viewports are locked, so the viewer holds their angle and only
    lets pan/zoom deltas ride on top; the perspective one is left free and is
    the same kind of viewport the default 3D scene uses.
    """
    centre, half_size = _frame_world_bounds(frame)
    from kumiki.drawings.drawing import ELEVATION_IDS, elevation_viewports
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
                "extent": _view_extent(half_size, right, up, _viewport_aspect(rect, _DEBUG_DRAWING_PAGE)),
            },
        )
        # Every timber, which is also what a scene defaults to; spelled out
        # because a real drawing is the interesting case and would not.
        viewport.update(members=None, ghostOthers=True, measurements=[])
        viewports.append(viewport)

    viewports.append(_preview_viewport(
        placed["preview"], _world_box(centre, half_size), _DEBUG_DRAWING_PAGE,
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



def _members_world_bounds(entries: List[TimberEntry]) -> Tuple[List[float], List[float]]:
    """(centre, half_size) over the given timber entries."""
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for entry in entries:
        for corner in _timber_world_corners(entry["cutTimber"]):
            for axis in range(3):
                lows[axis] = min(lows[axis], corner[axis])
                highs[axis] = max(highs[axis], corner[axis])
    if any(low == float("inf") for low in lows):
        return [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]
    return (
        [(lows[axis] + highs[axis]) / 2.0 for axis in range(3)],
        [(highs[axis] - lows[axis]) / 2.0 for axis in range(3)],
    )


def _normalize(vec: List[float]) -> List[float]:
    length = math.sqrt(sum(component * component for component in vec))
    return [component / length for component in vec] if length > 0 else [0.0, 0.0, 1.0]


def _camera_frame_looking(look: List[float]) -> CameraWire:
    """An orthonormal frame looking along `look`, kept upright.

    `up` is world Z with the part along the view direction taken out, which is
    what stops a three-quarter view from arriving on its side. right x up ==
    -look, the frame of a camera looking down its own -Z.
    """
    forward = _normalize(look)
    world_up = [0.0, 0.0, 1.0]
    along = sum(world_up[i] * forward[i] for i in range(3))
    up = _normalize([world_up[i] - along * forward[i] for i in range(3)])
    return {"right": _normalize(_cross(forward, up)), "up": up, "look": forward}


# --- preview orientation strategies -----------------------------------------
#
# Where the preview looks from. Two strategies, because what makes a good angle
# depends on what is being drawn, and neither is obviously the last word --
# `orient_by_search` in particular is a guess-and-check and may not survive, so
# it is kept behind the same seam as the other and can be dropped without
# touching anything that calls it.
#
# Both take an OrientedBox and the viewport's aspect, and return a camera frame.


class OrientedBox(NamedTuple):
    """A box in the world: where it is, which way it lies, and how big it is.

    Not an axis-aligned bounding box. A single timber has its own axes and is
    usually not square to the world, and orienting a view around its true box
    rather than the world box it happens to occupy is the difference between
    seeing the piece and seeing the space it takes up.
    """

    centre: List[float]
    axes: Tuple[List[float], List[float], List[float]]
    half_sizes: Tuple[float, float, float]

    def reach(self, direction: List[float]) -> float:
        """How far the box extends along a direction, from its centre."""
        return sum(
            abs(sum(direction[i] * self.axes[axis][i] for i in range(3))) * self.half_sizes[axis]
            for axis in range(3)
        )

    def silhouette_area(self, look: List[float]) -> float:
        """How much of the box a viewer sees, looking along `look`.

        Exact for a box: each face pair contributes its area scaled by how
        squarely it faces the camera.
        """
        a, b, c = self.half_sizes
        faces = ((a, 4 * b * c), (b, 4 * a * c), (c, 4 * a * b))
        return sum(
            abs(sum(look[i] * self.axes[axis][i] for i in range(3))) * area
            for axis, (_, area) in enumerate(faces)
        )

    @property
    def longest_axis(self) -> int:
        return max(range(3), key=lambda axis: self.half_sizes[axis])


def _world_box(centre: List[float], half_size: List[float]) -> OrientedBox:
    """The world-aligned box a group of members occupies."""
    return OrientedBox(
        centre=centre,
        axes=([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]),
        half_sizes=(half_size[0], half_size[1], half_size[2]),
    )


def _timber_box(entry: TimberEntry) -> OrientedBox:
    """One timber's own box: its axes, its section, and its cut extent.

    The cut extent rather than the stock, for the same reason the elevations use
    it -- a timber with an end joint is not cut to length first, so its stock is
    not the piece anyone is looking at.
    """
    timber = entry["timber"]
    along = _vector3_to_floats(timber.get_length_direction_global())
    across = _vector3_to_floats(timber.get_width_direction_global())
    up = _vector3_to_floats(timber.get_height_direction_global())
    origin = _vector3_to_floats(timber.get_bottom_position_global())
    start, finish = _cut_extent(entry["cutTimber"], float(timber.length))
    middle = (start + finish) / 2.0
    return OrientedBox(
        centre=[origin[i] + along[i] * middle for i in range(3)],
        axes=(along, across, up),
        half_sizes=(
            (finish - start) / 2.0,
            float(timber.size[0]) / 2.0,
            float(timber.size[1]) / 2.0,
        ),
    )


def _preview_extent(box: OrientedBox, frame: CameraWire, aspect: float) -> float:
    """How much of the world the preview has to hold, at this angle."""
    needed = max(box.reach(frame["up"]), box.reach(frame["right"]) / aspect)
    return max(0.001, needed * _PREVIEW_EXTENT_PADDING)


# A perspective view wants more room around the piece than an elevation does.
_PREVIEW_EXTENT_PADDING = 1.6

# Where the search may look from. Every compass direction, and a few heights
# above the horizon -- never level with it or straight down, where an upright
# camera has no up left to speak of.
_PREVIEW_AZIMUTH_STEPS = 24
_PREVIEW_ELEVATIONS_DEG = (20.0, 35.0, 50.0)


def _preview_look_candidates() -> List[List[float]]:
    candidates: List[List[float]] = []
    for elevation_deg in _PREVIEW_ELEVATIONS_DEG:
        elevation = math.radians(elevation_deg)
        for step in range(_PREVIEW_AZIMUTH_STEPS):
            azimuth = 2 * math.pi * step / _PREVIEW_AZIMUTH_STEPS
            # Looking down from above, so the z part is negative.
            candidates.append([
                math.cos(azimuth) * math.cos(elevation),
                math.sin(azimuth) * math.cos(elevation),
                -math.sin(elevation),
            ])
    return candidates


def orient_by_search(box: OrientedBox, aspect: float, preserve_up: bool = True) -> CameraWire:
    """Try a few dozen angles and keep the one that shows the piece best.

    What is maximized is how long the box's longest axis appears once the view
    has been sized to fit it. The obvious measure -- how much of the viewport
    the silhouette fills -- is worse than useless, because it is always won by
    looking straight down the length of the piece: an end-on view fits
    beautifully and shows nothing. Length on screen goes to zero there instead.

    Two angles that show the piece equally long are separated by which shows
    more of it, so a square-on view loses to a three-quarter one.

    With `preserve_up` the candidates are upright, so world +Z stays up the
    screen. That is what several timbers want: a frame read at a tilt is harder
    to follow than one drawn slightly smaller, and which way is up is part of
    what the preview is telling you.

    There is very likely a closed form for this -- the best angle for a box in a
    viewport of a given aspect is not a hard problem, and someone has certainly
    solved it. Guessing and checking is fine here: it is a few dozen candidates
    against one box, it runs once when a drawing is asked for rather than per
    frame, and being able to change the scoring by reading it is worth more than
    being clever.
    """
    longest = box.half_sizes[box.longest_axis]
    axis = box.axes[box.longest_axis]
    best_frame = _camera_frame_looking([-1.0, 1.0, -0.75])
    best_length = -1.0
    best_area = -1.0
    for look in _preview_look_candidates():
        frames = [_camera_frame_looking(look)]
        if not preserve_up:
            # Also allow the piece's own length to be the screen's up, which
            # suits a long timber in a tall viewport and puts the world on its
            # side to get it.
            frames.append(_frame_from_look_and_up(look, axis))
        for frame in frames:
            extent = _preview_extent(box, frame, aspect)
            across = sum(frame["right"][i] * axis[i] for i in range(3)) * longest
            up_screen = sum(frame["up"][i] * axis[i] for i in range(3)) * longest
            on_screen = math.sqrt(across * across + up_screen * up_screen) / extent
            area = box.silhouette_area(_normalize(look))
            # Within a couple of percent counts as the same length, and then
            # the view that shows more of the piece wins.
            if on_screen > best_length * 1.02 or (on_screen > best_length * 0.98 and area > best_area):
                best_length = max(best_length, on_screen)
                best_area = area
                best_frame = frame
    return best_frame


# Where a single piece is looked at from, in its own frame: off to one side,
# above, and a little towards one end, so a long face, a short face and an end
# are all in view.
_PIECE_LOOK_IN_BOX = (0.38, 0.86, -0.55)


def orient_from_box(box: OrientedBox, aspect: float) -> CameraWire:
    """Look at a box from a fixed three-quarter angle in its own frame.

    For a single piece there is nothing to search for: the box is the timber, so
    the angle that shows it well is the same angle every time, expressed in the
    timber's own axes rather than the world's. A post and a brace lying at forty
    degrees get the same view of themselves.

    The piece is laid along whichever way the viewport is longer, since that is
    the direction there is room in.
    """
    length, across, up = box.axes
    look = _normalize([
        length[i] * _PIECE_LOOK_IN_BOX[0]
        + across[i] * _PIECE_LOOK_IN_BOX[1]
        + up[i] * _PIECE_LOOK_IN_BOX[2]
        for i in range(3)
    ])
    longest = box.axes[box.longest_axis]
    # A tall viewport wants the piece standing up in it, a wide one wants it
    # lying down -- so the long axis goes up the screen only in the first.
    up_hint = longest if aspect < 1 else up
    return _frame_from_look_and_up(look, up_hint)


def _frame_from_look_and_up(look: List[float], up_hint: List[float]) -> CameraWire:
    """An orthonormal frame looking along `look`, as close to `up_hint` as it can.

    Falls back to the upright frame when the hint is along the view direction,
    where it says nothing about which way is up.
    """
    forward = _normalize(look)
    along = sum(up_hint[i] * forward[i] for i in range(3))
    up = [up_hint[i] - along * forward[i] for i in range(3)]
    if sum(component * component for component in up) < 1e-9:
        return _camera_frame_looking(look)
    up = _normalize(up)
    return {"right": _normalize(_cross(forward, up)), "up": up, "look": forward}


def _preview_viewport(
    placed: 'PlacedViewport',
    box: OrientedBox,
    page: PageWire,
    orbit: OrbitWire,
    orient: Callable[[OrientedBox, float], CameraWire],
) -> ViewportWire:
    """The live 3D view beside the elevations, pointed at what is being drawn.

    Left to itself the viewer builds a camera at the origin looking at nothing
    in particular, which for a piece standing away from the origin means an
    empty preview. `orient` is the strategy that picks the angle and `orbit`
    says how far it may be turned afterwards.
    """
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
            **frame,
            "target": centre,
            "extent": _preview_extent(box, frame, aspect),
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
    centre, half_size = _members_world_bounds([entry])

    viewports: List[ViewportWire] = []
    for view_id, axis_name, sign in _LONG_FACE_VIEWS:
        normal = [component * sign for component in axes[axis_name]]
        frame = _camera_looking_at_face(normal, along)
        placed = placed_by_role[view_id]
        rect = list(placed.rect)
        viewports.append(_viewport_spec(
            placed,
            locked=True,
            projection="orthographic",
            camera={
                **frame,
                "target": centre,
                "extent": _view_extent(
                    half_size, frame["right"], frame["up"], _viewport_aspect(rect, page),
                ),
            },
        ))
    return viewports


def _world_elevation_viewports(
    entries: List[TimberEntry], page: PageWire, placed_by_role: Dict[str, 'PlacedViewport'],
) -> List[ViewportWire]:
    """Front, top and right elevations in world axes, for a group of members."""
    centre, half_size = _members_world_bounds(entries)
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
                "extent": _view_extent(half_size, right, up, _viewport_aspect(rect, page)),
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
    page = PageWire(**_SELECTION_DRAWING_PAGE)
    timber_entries, _ = _assign_member_keys(frame)
    wanted = list(member_keys or [])
    by_key = {entry["memberKey"]: entry for entry in timber_entries}
    entries = [by_key[key] for key in wanted if key in by_key]

    drawn = entries or timber_entries
    centre, half_size = _members_world_bounds(drawn)

    if len(entries) == 1:
        from kumiki.drawings.drawing import SHOP_DRAWING_IDS, shop_drawing_viewports
        viewports = shop_drawing_viewports()
        placed = _placed_by_role(viewports, SHOP_DRAWING_IDS, page)
        viewports = _long_face_viewports(entries[0], page, placed)
        # One piece: oriented from its own box rather than the world box it
        # happens to occupy, and turned about its own length, so it can be
        # looked at from every side without ever being tumbled out of the
        # attitude it is drawn in.
        preview_box = _timber_box(entries[0])
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
        preview_box = _world_box(centre, half_size)
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

def _plane_constraints(one: GeometryWire, other: GeometryWire) -> List[List[float]]:
    """Directions the plane's normal has to be square to, for these two features.

    Each rule in the spec's priority order turns into the same kind of thing:

      perpendicular to a measured FACE  ->  normal square to that face's normal
      parallel to a measured EDGE       ->  normal square to that edge's run
      contains both measured POINTS     ->  normal square to the line between

    the last only when both anchors are points, since one point constrains where
    the plane sits rather than which way it faces.
    """
    constraints = []
    for geometry in (one, other):
        kind = (geometry or {}).get("kind")
        if kind == "plane":
            constraints.append([float(part) for part in geometry.get("normal") or []])
        elif kind == "line":
            constraints.append([float(part) for part in geometry.get("direction") or []])
    if (one or {}).get("kind") == "point" and (other or {}).get("kind") == "point":
        here, there = one.get("at") or [], other.get("at") or []
        if len(here) == 3 and len(there) == 3:
            constraints.append([float(there[i]) - float(here[i]) for i in range(3)])
    return [c for c in constraints if len(c) == 3 and any(c)]


def _plane_normal(constraints: List[List[float]], look: List[float]) -> Optional[List[float]]:
    """A normal square to every constraint, and otherwise as close to `look` as it can be.

    Two anchors give at most two constraints, and two constraints can always be
    met: square to both is their cross product, and when they are parallel it is
    the one-constraint case again. So this does not fail for want of a solution
    -- it returns None only when there is no direction left to choose, which is
    the caller's cue to fall back to the camera's own plane.

    Closest to `look` means the dimension is drawn as nearly face-on as its
    constraints allow, which is the difference between reading it and seeing it
    edge-on as a line.
    """
    gaze = _normalize(look)
    distinct = []
    for constraint in constraints:
        unit = _normalize(constraint)
        if not any(abs(abs(_dot(unit, seen)) - 1.0) < 1e-9 for seen in distinct):
            distinct.append(unit)

    if not distinct:
        # Nothing to be square to: face the camera.
        return gaze
    if len(distinct) >= 2:
        normal = _cross(distinct[0], distinct[1])
        if not any(abs(part) > 1e-12 for part in normal):
            return None
        normal = _normalize(normal)
        # A plane has no front, so take whichever way round faces the camera.
        return normal if _dot(normal, gaze) >= 0 else [-part for part in normal]

    # One constraint: a whole family of planes contains it. Take the camera's
    # direction with the part along the constraint removed, which is the member
    # of that family nearest to facing the camera.
    only = distinct[0]
    along = _dot(gaze, only)
    flattened = [gaze[i] - only[i] * along for i in range(3)]
    if not any(abs(part) > 1e-9 for part in flattened):
        # Looking straight down the one thing the plane must contain, so every
        # member of the family is equally edge-on. Any of them will do.
        fallback = [1.0, 0.0, 0.0] if abs(only[0]) < 0.9 else [0.0, 1.0, 0.0]
        return _normalize(_cross(only, fallback))
    return _normalize(flattened)


def _measurement_plane(
    one: GeometryWire,
    other: GeometryWire,
    at_one: Optional[List[float]],
    at_other: Optional[List[float]],
    look: List[float],
) -> PlaneWire:
    """Where a measurement between these two features is taken and drawn.

    `look` is the camera's view direction at the moment it was made, which
    settles whatever the features leave free -- and settles all of it when they
    constrain nothing.

    Position: through a measured point if there is one, since the plane has to
    contain it; otherwise midway between the two anchors, which puts the
    dimension among what it measures rather than off beside it.
    """
    normal = _plane_normal(_plane_constraints(one, other), look)
    if normal is None:
        normal = _normalize(look)

    at = None
    for geometry in (one, other):
        if (geometry or {}).get("kind") == "point" and geometry.get("at"):
            at = [float(part) for part in geometry["at"]]
            break
    if at is None and at_one and at_other and len(at_one) == 3 and len(at_other) == 3:
        at = [(float(at_one[i]) + float(at_other[i])) / 2 for i in range(3)]

    return {"at": at or [0.0, 0.0, 0.0], "normal": normal}


def _picked_located(
    feature_hits: List['OwnedFeatureHit'], feature_label: Optional[str], edge: Optional['CSGFeature'],
    owner: 'CutCSG',
) -> Optional['LocatedPick']:
    """The picked feature, its owner, and what it lies on, or None.

    One lookup for the anchor and the geometry both, so the two cannot end up
    describing different features.
    """
    if feature_label is None:
        return None
    if edge is not None:
        return (edge, owner, edge.locate_simple_unbounded(owner))
    hit = next((h for h in feature_hits if h.feature.name == feature_label), None)
    if hit is None:
        return None
    return (hit.feature, hit.owner, hit.feature.locate_simple_unbounded(hit.owner))


def _derivation_wire(
    local_csg: 'CutCSG', feature_hits: List['OwnedFeatureHit'], feature: Optional['CSGFeature'],
) -> Optional[DerivationWire]:
    """For a derived feature: the path to the node owning it, and each parent's path and name."""
    from kumiki.picking import node_positions

    if feature is None or not feature.is_derived():
        return None
    positions = node_positions(local_csg)

    def path_of(owner) -> Optional[List[str]]:
        placed = positions.get(id(owner))
        return placed[2] if placed is not None else None

    owner = next((hit.owner for hit in feature_hits if hit.feature is feature), None)
    return {
        "ownerPath": path_of(owner) if owner is not None else None,
        "parents": [{"path": path_of(parent.owner) or [], "name": parent.feature.name}
                    for parent in getattr(feature, "parents", ()) if parent is not None],
    }


def _pick_from_candidate(
    local_csg: 'CutCSG', hit: 'OwnedFeatureHit',
) -> Optional[Tuple[List[str], 'CutCSG', str, str, Optional['CSGFeature'], Optional['CSGFeature']]]:
    """Everything a pick needs, for one chosen feature at the point.

    Returns (path, node, label, type, edge, declared_edge), or None when the
    feature's owner cannot be placed in the tree, which leaves the caller with
    what it had.
    """
    from kumiki.picking import derived_feature_owner, node_positions
    from kumiki.csg.cutcsg import CSGFeatureType

    feature = hit.feature
    positions = node_positions(local_csg)
    if feature.feature_type() in (CSGFeatureType.EDGE, CSGFeatureType.POINT):
        # A derived feature is placed by the deeper of the two parents that
        # form it; a declared one belongs to whoever declared it, and has no
        # such pair for derived_feature_owner to read. Trying derived first
        # tells them apart.
        kind = feature.feature_type().name
        owned = derived_feature_owner(local_csg, feature)
        if owned is not None:
            return (owned[1], owned[0], feature.name, kind, feature, None)
        placed = positions.get(id(hit.owner))
        if placed is None:
            return None
        return (placed[2], hit.owner, feature.name, kind, None, feature)

    placed = positions.get(id(hit.owner))
    if placed is None:
        return None
    return (placed[2], hit.owner, feature.name, feature.feature_type().name, None, None)


def _best_matching_candidate(
    feature_hits: List['OwnedFeatureHit'],
    timber: 'PerfectTimberWithin',
    held_geometry: Optional[GeometryWire],
    look: Optional[List[float]],
    payload: Optional[PickRequest] = None,
) -> Optional[int]:
    """Which feature under the pointer best finishes the measurement in hand.

    The most specific feature is the right answer to "what is this thing here" --
    an edge beats the two faces that form it -- and the wrong one while a
    measurement is being made. Holding a face and being handed the arris beside
    it means most hovers refuse, and the face you want is never the best answer
    anywhere: it shows as a line, and on that line the edge wins.

    So while something is held, a candidate that ADMITS A MEASUREMENT with it
    beats one that does not, and among those, one of the same type as the held
    feature breaks the tie. Type matching is the tie-break rather than the rule:
    a candidate matching by type that admits nothing is worse than one that does
    not match and admits a distance.

    None when nothing is held, when there is no camera to project by, or when no
    candidate admits anything -- all of which leave the ordinary answer standing.
    """
    if not held_geometry or not look or not feature_hits:
        return None

    held = _geometry_from_wire(held_geometry)
    best = None
    for index, hit in enumerate(feature_hits):
        located = hit.feature.locate_simple_unbounded(hit.owner)
        geometry = _located_geometry(located, timber)
        if not geometry or not _kinds_for_pair(held, geometry, look, payload or PickRequest()):
            continue
        # Earlier is more specific, so among equals the first wins. Same TYPE as
        # the held end breaks the tie -- an edge matching an edge -- which is
        # now asked of the two primitives rather than of two "kind" strings.
        rank = (0 if type(geometry) is type(held) else 1, index)
        if best is None or rank < best[0]:
            best = (rank, index)
    return None if best is None else best[1]


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
    from kumiki.drawings.drawing import ViewAxes, measures_nothing

    held_geometry, look = payload.get("heldGeometry"), payload.get("look")
    if not held_geometry or not look:
        return None
    if located_pick is None:
        return {"kinds": [], "plane": None, "anchors": None,
                "reason": "nothing-under-pointer"}
    geometry = _located_geometry(located_pick[2], timber)
    if geometry is None:
        # A cylinder's barrel, a lofted side: good to select, nothing to
        # measure to.
        return {"kinds": [], "plane": None, "anchors": None,
                "reason": "not-measurable"}
    # The end already held comes back as the viewer stored it, so it is turned
    # into the shape the rules take. This is the one edge that conversion
    # happens at; everything past it works in primitives.
    held = _geometry_from_wire(held_geometry)
    # The plane comes first and stands whether or not a kind does: where a pair
    # would be measured is a property of the two features and the camera, not of
    # what the pair happens to admit.
    plane = _plane_for_pick(located_pick, timber, payload)
    # Structured, not named: `angle` composes for a 3D angle and is also what
    # every measurement written before spaces called a projected one.
    admitted = _kinds_for_pair(held, geometry, look, payload)
    if not admitted:
        return {"kinds": [], "plane": plane, "anchors": None, "reason": "no-kind"}
    # A kind that comes to nothing is not a kind this pair admits. Asked of the
    # two features, NOT of placed ends: what a distance comes to is a property
    # of the geometries and the space, and holds wherever the dimension is
    # drawn. An arris lying ON a face is the ordinary way to reach this, and a
    # single tenoned timber offers a dozen such pairs.
    #
    # Per kind, because they do not fail together: two points one above the
    # other have a vertical distance worth measuring and a horizontal one that
    # is nothing at all.
    view = ViewAxes.from_wire(payload)
    kinds = [kind.as_wire() for kind in admitted
             if not measures_nothing(held, geometry, kind, view)]
    if not kinds:
        # Refused here, so the hover paints it red and the click says why --
        # both following from the verdict without either knowing this rule.
        return {"kinds": [], "plane": plane, "anchors": None, "angle": None,
                "reason": "degenerate"}
    # Where it would sit: anchors for a distance, a corner for an angle. By the
    # rules that place it once written, so the preview IS the measurement rather
    # than a likeness of one.
    placement = _pick_placement(state, located_pick, timber, payload, slot_state)
    return {
        "kinds": kinds,
        "plane": plane,
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


def _kinds_for_pair(
    one: Optional[Any], other: Optional[Any],
    look: Sequence[float], payload: PickRequest,
) -> Tuple[Any, ...]:
    """What a pair admits, judged in whichever space the view is.

    In the 3D view a face is a plane, not whatever shape it happens to present
    from here -- so two faces meeting at a corner admit an angle, and two
    parallel ones a distance. Projecting there instead called almost every face
    an AREA and refused it.
    """
    from kumiki.drawings.drawing import MeasurementSpace, projected_kinds, three_d_kinds

    if _pick_space(payload) is MeasurementSpace.THREE_D:
        return three_d_kinds(one, other)
    return projected_kinds(one, other, look)


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
    from kumiki.drawings.drawing import (MeasurementSpace, ViewAxes, angle_rays,
                                distance_anchors)

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
    normal = (plane or {}).get("normal") or look
    placed = _resolve_anchor_placed(frame, held, normal, in_three_d)
    if placed is None or placed[1] is None:
        return empty
    held_span = placed[1]

    picked_span = _measure_span(
        located_pick[0], located_pick[1], timber, located_pick[2],
        _root_csg_of(ss, payload.get("memberKey")), normal, in_three_d)
    if picked_span is None:
        return empty

    geometry = _located_geometry(located_pick[2], timber)
    held_geometry = _geometry_from_wire(placed[0].get("geometry"))
    admitted = _kinds_for_pair(held_geometry, geometry, normal, payload)
    if not admitted:
        return empty
    kind = admitted[0]
    view = ViewAxes.from_wire({**payload, "look": look})
    # The same answer a written measurement travels with, so the preview shows
    # the number the finished one will carry rather than a second derivation of
    # it. .claude/plans/measuring-states.md asks for exactly this and only half had it:
    # the picture came from the verdict, the number was worked out again in the
    # viewer.
    ends = {"a": held_geometry, "b": geometry}
    if kind.operation.value == "angle":
        rays = angle_rays(held_span, picked_span)
        settled = _settled_measurement(ends, rays, None, kind, admitted, in_three_d, normal, view)
        return {"anchors": None,
                "angle": rays.as_wire() if rays is not None else None,
                "settled": settled}
    at_held, at_picked = distance_anchors(held_span, picked_span, kind, view)
    settled = _settled_measurement(ends, None, None, kind, admitted, in_three_d, normal, view)
    return {"anchors": {"a": list(at_held), "b": list(at_picked)},
            "angle": None, "settled": settled}


def _root_csg_of(ss: SlotState, member_key: Optional[str]) -> Optional['CutCSG']:
    cached = (getattr(ss, "mesh_cache", None) or {}).get(member_key) or {}
    return cached.get("local_csg")


def _plane_for_pick(
    located_pick: Optional['LocatedPick'], timber: 'PerfectTimberWithin', payload: PickRequest,
) -> Optional[PlaneWire]:
    """The plane a measurement to this pick would be taken on, or None.

    None unless something is held and the viewer said which way it is looking:
    a plane needs both ends and a camera, and a first pick has neither.
    """
    held_geometry = payload.get("heldGeometry")
    look = payload.get("look")
    if located_pick is None or not held_geometry or not look:
        return None
    geometry = _located_geometry_payload(located_pick[2], timber)
    if geometry is None:
        return None
    anchor = _feature_anchor(located_pick[0], located_pick[1], timber, located_pick[2])
    return _measurement_plane(
        held_geometry, geometry, payload.get("heldAt"), anchor, look)


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


def scalar_of(value: float) -> float:
    """A float as the exact scalar the geometry code multiplies by."""
    from kumiki.rule import scalar

    return scalar(repr(float(value)))


def _measure_span(
    feature: 'CSGFeature', node: 'CutCSG', timber: 'PerfectTimberWithin', located: Optional['Located'],
    root_csg: Optional['CutCSG'],
    plane_normal: Optional['VectorLike'],
    in_three_d: bool = False,
) -> Optional['MeasureSpan']:
    """What a feature is, where the measurement is being taken.

    See MeasureSpan. The extent comes from what the feature occupies once
    cropped to the timber, not from what declared it: a cutter extended past the
    timber puts its declared extent out there with it.

    ON A SHEET a FACE becomes a line, because a face is only measurable when it
    is seen edge-on and a face seen edge-on draws as a line along itself. Which
    line depends on the plane, which is why this needs it. Without a plane, or
    for a face that is not edge-on, it falls back to the point it used to be.

    IN THE SOLID nothing is projected away: a face is a PLANE, and an edge
    pointing at the reader is still an edge. Both collapses below are the
    sheet's, and applying them there put an edge and the face it runs parallel
    to through the two-lines rule, which leaned the dimension.
    """
    from kumiki.csg.cutcsg import OwnedFeatureHit
    from kumiki.csg.feature_paths import FeatureHandle
    from kumiki.drawings.feature_span import feature_span

    handle = FeatureHandle(timber=timber, hit=OwnedFeatureHit(feature=feature, owner=node))
    return feature_span(handle, root_csg, plane_normal, in_three_d)


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
    from kumiki.drawings.drawing import (DEGENERATE_SEPARATION, MeasurementDirection,
                               MeasurementKind, MeasurementOperation,
                               MeasurementSpace, ViewAxes, angle_between,
                               angle_rays, distance_anchors, pair_separation,
                               projected_kinds, three_d_kinds)

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
        # What this pair admits from here, so the anchors are placed for the
        # measurement that will actually be drawn. Defaulting to perpendicular
        # instead put two crossing faces -- which admit an ANGLE and nothing
        # else -- through the parallel-line rule, and came out square to one of
        # them and not the other.
        # Judged in the same space, so what the pair admits and what its ends
        # came back as cannot disagree. Projecting a 3D measurement here
        # called its faces AREAs and left it with no kind at all.
        admitted = (three_d_kinds(ends["a"], ends["b"]) if in_three_d
                    else projected_kinds(ends["a"], ends["b"], plane))
        kind = declared or (admitted[0] if admitted else None)
        rays = None
        if kind is not None and kind.operation is MeasurementOperation.DISTANCE:
            at_a, at_b = distance_anchors(spans["a"], spans["b"], kind, view)
            resolved["a"] = {**resolved["a"], "at": list(at_a)}
            resolved["b"] = {**resolved["b"], "at": list(at_b)}
        elif kind is not None and kind.operation is MeasurementOperation.ANGLE:
            # Where the corner IS and which two ways it opens, worked out from
            # both features together. The viewer used to build the arc from each
            # feature's own anchor and its normal, which put the vertex wherever
            # two unrelated screen lines happened to cross -- often touching
            # neither of the features being measured.
            rays = angle_rays(spans["a"], spans["b"])
            resolved["angle"] = cast(AngleWire, rays.as_wire()) if rays is not None else None
        resolved["settled"] = _settled_measurement(
            ends, rays, declared, kind, admitted, in_three_d, plane, view)
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
    return {"kind": None, "available": [], "space": None, "value": None,
            "reason": reason, "a": None, "b": None}


def _measure_end_name(measure: MeasureWire, key: str) -> str:
    """One end of a measurement, named the way a person would look for it."""
    end = measure.get(key) or {}
    return str(end.get("feature") or end.get("timber") or "?")


def _settled_measurement(
    ends: Dict[str, Optional['Located']], rays: Optional['AngleRays'],
    declared: Optional['MeasurementKind'], kind: Optional['MeasurementKind'],
    admitted: Sequence['MeasurementKind'], in_three_d: bool, plane: 'VectorLike', view: Optional['ViewAxes'],
) -> SettledWire:
    """What this measurement comes to, decided here and sent with it.

    The viewer worked the same thing out for itself on every frame, from its own
    copy of the rules in measurements.js. Two derivations of one number is how
    the number drifts, and .claude/plans/measuring-states.md already asks for the other
    one -- "the preview is drawn from the verdict, never from a second
    calculation" -- which was true of the picture and not of the number beside
    it.

    It can be answered here because it does not depend on the camera: a
    measurement carries the plane it was taken on, and the value is read against
    that rather than against wherever the reader is standing. What the viewer
    still decides for itself is whether the view it is drawing into IS that
    plane, which is the one question a fixed answer cannot cover.

    `reason` is why there is nothing to draw, in the same words and the same
    order the viewer uses, so a row that says why and a dimension that is
    missing cannot disagree.
    """
    from dataclasses import replace

    from kumiki.drawings.drawing import (DEGENERATE_SEPARATION, MeasurementOperation,
                                ViewAxes, angle_between, pair_separation)
    from kumiki.rule import create_v3

    names = [one.name for one in admitted]
    space = "3d" if in_three_d else "projected"
    settled: SettledWire = {
        "kind": cast(MeasureKindWire, kind.as_wire()) if kind is not None else None,
        "available": names, "space": space, "value": None, "reason": None,
        "a": _settled_form(ends["a"], in_three_d, plane),
        "b": _settled_form(ends["b"], in_three_d, plane)}
    if not admitted:
        settled["reason"] = "not-measurable"
        return settled
    if declared is not None and declared.name not in names:
        settled["reason"] = "kind-unavailable"
        return settled
    if kind is None:
        settled["reason"] = "not-measurable"
        return settled

    if kind.operation is MeasurementOperation.ANGLE:
        # Off the RAYS, which are the two ways the corner opens -- so the number
        # and the arc drawn from them are one answer. Normals alone give the
        # same absolute dot for 45 degrees and 135.
        value = angle_between(rays)
        settled["value"] = {"unit": "angle", "value": 0.0 if value is None else value}
        return settled

    # Against the measurement's own plane, not the viewport's: `plane` is
    # already the one or the other, decided above.
    length = pair_separation(
        ends["a"], ends["b"], kind,
        replace(ViewAxes.from_wire(view), look=create_v3(*plane)))
    if length is None:
        settled["reason"] = "not-measurable"
        return settled
    settled["value"] = {"unit": "length", "value": length}
    if length < DEGENERATE_SEPARATION:
        settled["reason"] = "degenerate"
    return settled


def _settled_form(geometry: Optional['Located'], in_three_d: bool, plane: Any) -> SettledEndWire:
    """What one end behaves as, in the shape the viewer's own forms took.

    Settled here so the rule has one implementation; what crosses is the answer.
    "area" and "none" both mean nothing to measure to, and only this edge tells
    them apart.
    """
    from kumiki.drawings.drawing import project_geometry_for_measuring
    from kumiki.geometry import Line, Plane, Point, unit_vector

    if not in_three_d:
        seen = project_geometry_for_measuring(geometry, plane)
        if seen is None:
            return {"form": "area" if isinstance(geometry, Plane) else "none"}
        geometry = seen
    if isinstance(geometry, Plane):
        return {"form": "plane", "normal": list(unit_vector(geometry.normal))}
    if isinstance(geometry, Line):
        return {"form": "line", "direction": list(unit_vector(geometry.direction))}
    if isinstance(geometry, Point):
        return {"form": "point"}
    return {"form": "none"}


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


def _located_geometry(located: Optional['Located'], timber: 'PerfectTimberWithin') -> Optional['Located']:
    """A feature's unbounded geometry, in world space.

    The same Point, Line or Plane the CSG located, carried out of the timber's
    frame into the world's. This is what python measures with; the mapping the
    viewer reads is this, serialised -- see _located_geometry_payload.

    A plane keeps its normal and a line its direction, because those are what
    decide whether two features are parallel once projected -- which is what
    separates a separation from a distance between two points.
    """
    from kumiki.geometry import Line, Plane, Point

    def to_world(point: Any) -> Any:
        return timber.transform.local_to_global(point)

    def direction_to_world(direction: Any) -> Any:
        return timber.transform.local_to_global_direction(direction)

    if isinstance(located, Point):
        return Point(position=to_world(located.position))
    if isinstance(located, Line):
        return Line(point=to_world(located.point),
                    direction=direction_to_world(located.direction))
    if isinstance(located, Plane):
        # Plane, not whatever subclass it arrived as: an UnsignedPlane means
        # "ignore the sign of the normal", which is a fact about the cut that
        # declared it and not about the geometry being measured to.
        return Plane(point=to_world(located.point),
                     normal=direction_to_world(located.normal))
    return None


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


def _located_geometry_payload(located: Optional['Located'], timber: 'PerfectTimberWithin') -> Optional[GeometryWire]:
    """A feature's unbounded geometry, in world space, as the viewer wants it."""
    return _geometry_payload(_located_geometry(located, timber))


def _feature_anchor(
    feature: 'CSGFeature', node: 'CutCSG', timber: 'PerfectTimberWithin', located: Optional['Located'],
    root_csg: Optional['CutCSG'] = None,
) -> Optional[List[float]]:
    """Where to attach a dimension to this feature, in world space.

    From what the feature occupies once cropped to the timber, not from what
    declared it: a cutter extended past the timber puts its declared anchor out
    there with it, and a half space has no declared anchor at all. A face gives
    a region and a point gives itself; an edge gives a segment, which matters
    because an edge declared on an extended cutter runs off with it.

    Falls back to the declared extent when neither can be worked out -- a curved
    primitive, say -- since somewhere approximate beats nowhere.
    """
    from kumiki.drawings.feature_span import declared_line_span, line_pieces
    from kumiki.geometry import Line, Plane, Point
    from kumiki.csg.cropcsg import (
        approximately_crop_plane_to_area_on_csg,
        crop_line_to_segments_on_csg,
    )

    # A point is already where it is: nothing to crop, and cropping could only
    # say it is off the piece, which is a different question from where it is.
    if isinstance(located, Point):
        return _vector3_to_floats(timber.transform.local_to_global(located.position))

    if isinstance(located, (Plane, Line)):
        solid = timber.get_perfect_timber_within_csg_local()
        # Generous enough to contain the timber before clipping starts, and
        # measured from the timber rather than from the feature's own point,
        # which may be nowhere near it.
        reach = float(timber.length) * 4
        middle = None
        if isinstance(located, Plane):
            # Still the enclosing solids rather than the tree: cropping a plane
            # cannot subtract yet, so a face half taken away by a cut anchors at
            # the centroid of the whole face. See that function's docstring.
            cropped = approximately_crop_plane_to_area_on_csg(
                located, [node, solid], seed_reach=reach, near=solid.transform.position,
            )
            middle = cropped.centroid() if cropped is not None and not cropped.is_empty else None
        elif root_csg is not None:
            # The same bounds a measurement uses -- what the feature says about
            # itself, and where the timber leaves it. Cropping to the timber
            # alone gave a mortise hole's arris the length of the whole post,
            # and its midpoint the middle of the post, which is where a
            # half-made measurement was being drawn.
            pieces = line_pieces(
                located, [root_csg] if feature.real else [], reach, solid.transform.position,
                declared=declared_line_span(feature, node, located))
            if pieces:
                # The longest piece. A cut can leave an edge in several, and a
                # dimension has to attach to one of them -- the biggest is the
                # one a reader would point at.
                low, high = max(pieces, key=lambda piece: piece[1] - piece[0])
                middle = located.point + located.direction * scalar_of((low + high) / 2)
        if middle is not None:
            return _vector3_to_floats(timber.transform.local_to_global(middle))

    extent = feature.get_extent(node)
    if extent is None:
        return None
    return _vector3_to_floats(timber.transform.local_to_global(extent.anchor))


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
    span = _measure_span(feature, node, timber, located, root_csg, plane, solid_space)
    return ({
        "at": _feature_anchor(feature, node, timber, located, root_csg),
        "geometry": _located_geometry_payload(located, timber),
    }, span)


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
    from kumiki.picking import DECLARED_EDGE_FLOAT_NOISE
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
    from kumiki.picking import build_inv_transform_float, edge_highlight_segments, extract_highlight_mesh
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
        located = handle.feature.locate_simple_unbounded(handle.owner)
        result["at"] = _feature_anchor(handle.feature, handle.owner, timber, located, root)
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
    from kumiki.picking import label_name
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
    # Step 1: Invalidate Python's built-in import caches
    importlib.invalidate_caches()
    
    # Step 2: Aggressively purge project modules
    if _project_root is not None:
        keep_paths = {Path(__file__).resolve(), file_path.resolve()}
        _purge_project_modules(_project_root, keep_paths, verbose=verbose)
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
# is kumiki.picking; this turns its answers into wire forms.
# ===========================================================================

def _local_ray_from_payload(
    payload: PickRequest, rot: List[List[float]], pos: List[float],
) -> Optional[LocalRay]:
    """The pointer's ray in timber-local space, or None if it did not send one.

    None is ordinary rather than a fault: a pick can be made without a ray (the
    tests do, and so does any caller that has only a point), and everything on
    a surface is found from the point alone.
    """
    from kumiki.picking import inv_transform_direction, inv_transform_point
    ray = payload.get("ray")
    if not isinstance(ray, dict):
        return None
    origin, direction = ray.get("origin"), ray.get("direction")
    if not (isinstance(origin, list) and isinstance(direction, list)):
        return None
    if len(origin) != 3 or len(direction) != 3:
        return None
    return (
        inv_transform_point(rot, pos, [float(c) for c in origin]),
        inv_transform_direction(rot, [float(c) for c in direction]),
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
    from kumiki.picking import subtree_contains
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
    local_pt: List[float],
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
    from kumiki.picking import outward_normal_and_face, to_v3, label_name
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
    from kumiki.picking import node_positions
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
    from kumiki.picking import build_inv_transform_float, csg_point_on_boundary, derived_feature_owner, edge_highlight_segments, extract_highlight_mesh, features_at_point, inv_transform_point, navigate_csg_one_level, navigate_csg_to_leaf, node_positions, resolve_csg_at_path, resolve_derived_feature
    ss = slot_state if slot_state is not None else state._active
    member_key = payload.get("memberKey")
    point = payload.get("point")
    current_path = payload.get("currentPath") or []
    ctrl_click = payload.get("ctrlClick", False)
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
    local_pt = inv_transform_point(timber_rot, timber_pos, [float(p) for p in point])

    t0 = time.monotonic()

    # A plain click goes straight to the feature, which is what someone
    # clicking a shoulder or an edge is after. Ctrl holds it back to one level
    # per click, for walking down through the compounds on the way.
    if not ctrl_click:
        new_path, target_csg, feature_label = navigate_csg_to_leaf(local_csg, local_pt, eps)
    else:
        if current_path:
            node = resolve_csg_at_path(local_csg, current_path, local_pt, eps)
            on_boundary = csg_point_on_boundary(node, local_pt, eps)
            if not on_boundary:
                node = local_csg
                current_path = []
        else:
            node = local_csg

        new_path, target_csg, feature_label = navigate_csg_one_level(
            node, local_pt, current_path, eps,
        )

    # A click that has drilled far enough to name a face can name an edge
    # instead, when one is the better answer at that point. Only then: while a
    # click is still descending through compounds it selects them whole, and
    # jumping to an edge deep inside would skip the levels between.
    feature_type = None
    declared_edge = None
    feature_hits = features_at_point(
        local_csg, local_pt, eps, tolerances,
        local_ray=_local_ray_from_payload(payload, timber_rot, timber_pos),
    )
    edge = resolve_derived_feature(feature_hits) if feature_label is not None else None

    # Which of the features at this point is wanted, when more than one is.
    #
    # The caller may name one outright -- Tab steps through them -- or leave it
    # to the preference, which while a measurement is being made picks whichever
    # can actually finish it. Either way the choice is FINAL: the rules below
    # exist to guess what was meant, and they have nothing left to decide once
    # it has been said. Letting them run anyway puts the most specific feature
    # back, which is how cycling to a face landed on the arris again every time.
    held_geometry = payload.get("heldGeometry")
    look = payload.get("look")
    candidate_index = payload.get("candidateIndex")
    if candidate_index is None:
        candidate_index = _best_matching_candidate(
            feature_hits, timber, held_geometry, look, payload)
    picked = None
    # `is not None`, because ZERO IS A CHOICE. Stepping round to the first
    # feature, or picking the first row of the menu, is the caller naming one --
    # and treating it as "nothing named" dropped it back to the most specific
    # answer, which is the very thing cycling exists to get away from.
    if candidate_index is not None and feature_hits:
        chosen = feature_hits[int(candidate_index) % len(feature_hits)]
        picked = _pick_from_candidate(local_csg, chosen)
        if picked is not None:
            new_path, target_csg, feature_label, feature_type, edge, declared_edge = picked

    if picked is None:
        if edge is not None:
            owned = derived_feature_owner(local_csg, edge)
            if owned is not None:
                target_csg, new_path = owned[0], owned[1]
                feature_label = edge.name
                feature_type = edge.feature_type().name
        elif feature_label is not None and feature_hits:
            # A declared edge or point -- a timber's own arris or corner --
            # beats the face a click lands on, the same way a derived one does
            # and for the same reason: it is the more specific answer at that
            # point. Unlike a derived one it belongs to the node that declared
            # it, so it is placed the way any declared feature is.
            from kumiki.csg.cutcsg import CSGFeatureType

            best = feature_hits[0]
            if best.feature.feature_type() in (CSGFeatureType.EDGE, CSGFeatureType.POINT):
                placed = node_positions(local_csg).get(id(best.owner))
                if placed is not None:
                    new_path, target_csg = placed[2], best.owner
                    feature_label = best.feature.name
                    feature_type = best.feature.feature_type().name
                    declared_edge = best.feature

    parent_csg = None
    if new_path:
        parent_csg = resolve_csg_at_path(local_csg, new_path, local_pt, eps)

    # An edge is drawn as a line whether it was derived or declared: a timber's
    # own arris needs the line as much as a joint's does, and without this it
    # was picked and then nothing was drawn for it.
    highlight_edge = None
    edge_absent = False
    edge_feature = edge if edge is not None else declared_edge
    located_pick = _picked_located(feature_hits, feature_label, edge_feature, target_csg)
    if edge_feature is not None:
        highlight_edge, edge_absent = edge_highlight_segments(
            edge_feature, target_csg, timber, local_csg,
        )

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
        "candidateCount": len(feature_hits),
        # Enough per candidate to answer "why that one" and "why not mine" from
        # the viewer's own log, without turning the runner's pick log on: the
        # ordering is (real, kind, declared, group, priority), and all of it is
        # here.
        "candidates": [
            {
                "label": hit.feature.name,
                "type": hit.feature.feature_type().name,
                "real": bool(hit.feature.real),
                "derived": bool(hit.feature.is_derived()),
                "group": hit.feature.group.name,
                "priority": int(hit.feature.priority),
            }
            for hit in feature_hits
        ],
        # And WHICH of them this answer is, so the viewer can mark the one it is
        # showing -- the right-click menu lights the row the view is lighting,
        # rather than keeping a second opinion about which that is.
        #
        # Matched by name at the end rather than recorded on the way: the choice
        # can come from a named index, from the preference when none was named,
        # or from one of the fallbacks, and all of them have to be reported the
        # same way.
        "candidateIndex": next(
            (index for index, hit in enumerate(feature_hits)
             if hit.feature.name == feature_label),
            None,
        ),
        # Where the feature is, unbounded, in world space. What decides whether
        # a pair can be dimensioned is what each PROJECTS to, and the viewer
        # projects on every pointer move -- so it gets the plane or the line and
        # works that out itself between asking.
        "geometry": (_located_geometry_payload(located_pick[2], timber)
                     if located_pick is not None else None),
        # And where a dimension would attach, cropped to the solid the cuts have
        # left, which is the same anchor the saved measurement resolves to. An
        # edge in particular anchors at the middle of its longest surviving
        # piece, not at the extent it was declared with.
        "at": (_feature_anchor(located_pick[0], located_pick[1], timber,
                               located_pick[2], local_csg)
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
    member_key: str, local_pt: List[float], tolerances: 'FeatureTestTolerances',
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
    from kumiki.picking import build_inv_transform_float, extract_highlight_mesh, resolve_csg_at_path, label_name
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
    return result


def _resolve_slot(state: RunnerState, payload: Dict[str, Any]) -> SlotState:
    """Return the SlotState targeted by the request payload (defaults to active_slot)."""
    slot_name = payload.get("slot", state.active_slot)
    return state.get_slot(slot_name)


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
