"""STL stock, timber-local placement, and source-call provenance."""

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping, Optional, Sequence
import ast
import hashlib
import inspect
import math

from .rule import Transform, create_v2
from .timber import MeshTimber, PerfectTimberWithin
from .csg.meshcsg import TriangleSolid


@dataclass(frozen=True)
class STLPlacement:
    """Place a mesh in timber-local space: scale, XYZ Euler rotation in degrees, then translation in metres."""

    translation: Sequence[float] = (0, 0, 0)
    rotation: Sequence[float] = (0, 0, 0)
    scale: Sequence[float] = (1, 1, 1)

    def __post_init__(self):
        for name in ('translation', 'rotation', 'scale'):
            values = tuple(float(v) for v in getattr(self, name))
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError(f"STL {name} must contain three finite numbers")
            if name == 'scale' and any(v <= 0 for v in values):
                raise ValueError('STL scales must be positive')
            object.__setattr__(self, name, values)

    def to_dict(self):
        return {name: list(getattr(self, name)) for name in ('translation', 'rotation', 'scale')}

    def matrix(self):
        import numpy as np
        from trimesh.transformations import euler_matrix
        # Three.js Euler XYZ composes Rx * Ry * Rz (rotating intrinsic axes).
        matrix = euler_matrix(*(math.radians(v) for v in self.rotation), axes='rxyz')
        matrix[:3, :3] = matrix[:3, :3] @ np.diag(self.scale)
        matrix[:3, 3] = self.translation
        return matrix


@dataclass(frozen=True)
class STLSource:
    path: str
    line: int
    call: str
    digest: str


def _source_call(path: Path, line: int) -> Optional[STLSource]:
    try:
        with path.open(encoding="utf-8", newline="") as file:
            text = file.read()
        tree = ast.parse(text)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and node.lineno <= line <= (node.end_lineno or node.lineno)
                 and (isinstance(node.func, ast.Name) and node.func.id == 'create_stl_timber'
                      or isinstance(node.func, ast.Attribute) and node.func.attr == 'create_stl_timber')]
        if len(calls) != 1:
            return None
        call = ast.get_source_segment(text, calls[0])
        if call is None:
            return None
        return STLSource(str(path), calls[0].lineno, call, hashlib.sha256(text.encode()).hexdigest())
    except (OSError, SyntaxError, UnicodeError):
        return None


def load_stl(path: Path, units: str) -> TriangleSolid:
    """Load a closed, consistently wound STL and convert its vertices to metres."""
    import numpy as np
    import trimesh
    factors = {'m': 1.0, 'mm': .001, 'cm': .01, 'in': .0254}
    if units not in factors:
        raise ValueError('STL units must be m, mm, cm, or in')
    mesh = trimesh.load_mesh(str(path), file_type='stl', process=True)
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError('STL must contain a triangle mesh')
    if not np.isfinite(mesh.vertices).all() or not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError('STL must be finite, watertight, and consistently wound')
    if mesh.volume < 0:
        mesh.invert()
    if not mesh.is_volume:
        raise ValueError("STL must enclose a positive volume")
    return TriangleSolid(vertices=tuple((float(p[0]) * factors[units], float(p[1]) * factors[units], float(p[2]) * factors[units]) for p in mesh.vertices),
                         faces=tuple((int(f[0]), int(f[1]), int(f[2])) for f in mesh.faces))


@dataclass(frozen=True)
class STLTimber(MeshTimber):
    """Represent STL stock, or a reference prism awaiting placement when `placement` is None."""

    stl_path: str = field(kw_only=True)
    mesh: TriangleSolid = field(kw_only=True, repr=False)
    placement: Optional[STLPlacement] = field(default=None, kw_only=True)
    source: Optional[STLSource] = field(default=None, kw_only=True, repr=False, compare=False)
    units: str = field(default='mm', kw_only=True)

    @property
    def needs_stl_placement(self) -> bool:
        return self.placement is None

    def placed_mesh(self) -> TriangleSolid:
        import numpy as np
        vertices = np.asarray(self.mesh.vertices)
        matrix = (self.placement or STLPlacement()).matrix()
        placed = vertices @ matrix[:3, :3].T + matrix[:3, 3]
        return replace(self.mesh, vertices=tuple(tuple(float(v) for v in p) for p in placed), label=self.csg_label('rough'))

    def is_perfect_timber(self) -> bool:
        return self.needs_stl_placement

    def get_rough_half_sizes(self):
        if self.needs_stl_placement:
            return super().get_rough_half_sizes()
        bounds = self.placed_mesh().get_aabb()
        assert bounds.max_x is not None and bounds.min_x is not None
        assert bounds.max_y is not None and bounds.min_y is not None
        return (create_v2(max(0, bounds.max_x), max(0, -bounds.min_x)),
                create_v2(max(0, bounds.max_y), max(0, -bounds.min_y)))

    def get_actual_csg_local(self, with_feature_labels: bool = True):
        if self.needs_stl_placement:
            return super().get_extended_actual_csg_local(False, False, with_feature_labels)
        return self.placed_mesh()

    def get_extended_actual_csg_local(self, extend_bot: bool, extend_top: bool, with_feature_labels: bool = True):
        return self.get_actual_csg_local(with_feature_labels)


def create_stl_timber(reference: PerfectTimberWithin, stl_path, *, units: str = 'mm',
                      placement: Optional[Mapping[str, Sequence[float]]] = None) -> STLTimber:
    """Load STL stock relative to this source file, using `reference` for joinery coordinates.

    Omit placement to show a placeholder in Kigumi. Placement has translation (metres),
    rotation (XYZ degrees), and positive scale triples, all relative to the reference timber.
    STL stock cannot extend itself to accommodate end joints.
    """
    current = inspect.currentframe()
    caller = current.f_back if current else None
    assert caller is not None, "STL source resolution requires a Python caller frame"
    try:
        source_path = Path(caller.f_code.co_filename).resolve()
        source = _source_call(source_path, caller.f_lineno)
    finally:
        del caller, current
    path = Path(stl_path)
    if not path.is_absolute():
        path = source_path.parent / path
    configured = None if placement is None else STLPlacement(**placement)
    return STLTimber(length=reference.length, size=reference.size, transform=reference.transform,
                     ticket=reference.ticket, stl_path=str(path.resolve()), mesh=load_stl(path, units),
                     placement=configured, source=source, units=units)
