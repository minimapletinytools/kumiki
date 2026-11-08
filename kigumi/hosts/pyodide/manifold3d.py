"""manifold3d's API, as kumiki uses it, over Manifold's WebAssembly build (npm manifold-3d) in Pyodide.

Only what kumiki/csg/triangles.py calls: Manifold(Mesh64(...)), Manifold.batch_boolean, subtraction,
status and to_mesh64. The browser build's meshes carry float32 vertices, though Manifold works in double:
each mesh is given a tolerance of its own instead of the one float32 input would get (which grows with a
solid's size), and its vertices are set exactly, in and out, through warpBatch, which sees them as double.
Rounded to float32, a sliver triangle tilts, and the viewer shades it as a crease.
"""
import numpy as np
from pyodide.ffi import create_proxy, to_js
from js import Object
import _manifold_wasm as _m

# Metres. Far below any cut kumiki makes; Manifold works in double inside.
TOLERANCE = 1e-7


class OpType:
    Add = "add"
    Subtract = "subtract"
    Intersect = "intersect"


class Mesh64:
    def __init__(self, vert_properties, tri_verts):
        self.vert_properties = np.asarray(vert_properties, dtype=np.float64)
        self.tri_verts = np.asarray(tri_verts)


def _keys(points):
    """Each point's float32 rounding, as bytes: how a float32 vertex finds its double."""
    rounded = np.ascontiguousarray(np.asarray(points, dtype=np.float64).reshape(-1, 3).astype(np.float32))
    return [row.tobytes() for row in rounded]


def _warp(js_manifold, change):
    """js_manifold.warpBatch with `change(points)` on its vertices as doubles (an (n, 3) array, changed in place)."""
    def warp(verts, count):
        points = np.asarray(verts.to_py(), dtype=np.float64).reshape(-1, 3)[:count]
        if change(points):
            verts.assign(np.ascontiguousarray(points, dtype=np.float64).ravel())

    proxy = create_proxy(warp)
    try:
        return js_manifold.warpBatch(proxy)
    finally:
        proxy.destroy()


class Manifold:
    def __init__(self, mesh=None, _js=None):
        if _js is not None:
            self._js = _js
            return
        exact = np.asarray(mesh.vert_properties, dtype=np.float64).reshape(-1, 3)
        verts = np.ascontiguousarray(exact, dtype=np.float32).ravel()
        tris = np.ascontiguousarray(mesh.tri_verts, dtype=np.uint32).ravel()
        options = to_js({"numProp": 3, "vertProperties": to_js(verts), "triVerts": to_js(tris),
                         "tolerance": TOLERANCE}, dict_converter=Object.fromEntries)
        js_mesh = _m.Mesh.new(options)
        js_mesh.merge()
        rounded = _m.Manifold.new(js_mesh)
        by_key = dict(zip(_keys(exact), exact))

        def unround(points):
            for i, key in enumerate(_keys(points)):
                found = by_key.get(key)
                if found is not None:
                    points[i] = found
            return True

        self._js = _warp(rounded, unround)
        rounded.delete()

    @staticmethod
    def batch_boolean(solids, op):
        items = to_js([s._js for s in solids])
        if op == OpType.Add:
            return Manifold(_js=_m.Manifold.union(items))
        if op == OpType.Intersect:
            return Manifold(_js=_m.Manifold.intersection(items))
        return Manifold(_js=_m.Manifold.difference(items))

    def __sub__(self, other):
        return Manifold(_js=self._js.subtract(other._js))

    def status(self):
        return self._js.status()

    def to_mesh64(self):
        js_mesh = self._js.getMesh()
        num_prop = int(js_mesh.numProp)
        verts = np.asarray(js_mesh.vertProperties.to_py(), dtype=np.float32).astype(np.float64).reshape(-1, num_prop)[:, :3]
        tris = np.asarray(js_mesh.triVerts.to_py(), dtype=np.uint32).reshape(-1, 3)
        # The vertices as doubles, read through warpBatch, matched to the float32 ones by their rounding.
        exact = {}

        def read(points):
            exact.update(zip(_keys(points), points.copy()))
            return False

        _warp(self._js, read).delete()
        verts = np.array([exact.get(key, row) for key, row in zip(_keys(verts), verts)], dtype=np.float64).reshape(-1, 3)
        return Mesh64(verts, tris)

    def __del__(self):
        try:
            self._js.delete()
        except Exception:
            pass
