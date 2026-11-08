"""manifold3d's API, as kumiki uses it, over Manifold's WebAssembly build (npm manifold-3d) in Pyodide.

Only what kumiki/csg/triangles.py calls: Manifold(Mesh64(...)), Manifold.batch_boolean, subtraction,
status and to_mesh64. The browser build takes float32 vertices, so each mesh is given a tolerance of its
own instead of the one float32 input would get (which grows with a solid's size).
"""
import numpy as np
from pyodide.ffi import to_js
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


class Manifold:
    def __init__(self, mesh=None, _js=None):
        if _js is not None:
            self._js = _js
            return
        verts = np.ascontiguousarray(mesh.vert_properties, dtype=np.float32).ravel()
        tris = np.ascontiguousarray(mesh.tri_verts, dtype=np.uint32).ravel()
        options = to_js({"numProp": 3, "vertProperties": to_js(verts), "triVerts": to_js(tris),
                         "tolerance": TOLERANCE}, dict_converter=Object.fromEntries)
        js_mesh = _m.Mesh.new(options)
        js_mesh.merge()
        self._js = _m.Manifold.new(js_mesh)

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
        verts = np.asarray(js_mesh.vertProperties.to_py(), dtype=np.float32).astype(np.float64).reshape(-1, num_prop)
        tris = np.asarray(js_mesh.triVerts.to_py(), dtype=np.uint32).reshape(-1, 3)
        return Mesh64(verts, tris)

    def __del__(self):
        try:
            self._js.delete()
        except Exception:
            pass
