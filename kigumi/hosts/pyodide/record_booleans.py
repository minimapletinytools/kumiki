"""Record each boolean that meshing a dovetailed sawhorse leg does: its operands and the result's volume,
to /out/ops.json, to replay through native manifold3d and see which side a difference comes from."""
import json, importlib.util
import numpy as np
import kumiki.csg.triangles as T
from kumiki.csg.triangles import mesh_cutcsg
ops = []
orig = T._manifold_boolean
def record(operation, meshes):
    out = orig(operation, meshes)
    ops.append({"op": operation, "operands": [{"v": np.asarray(m.vertices).tolist(), "f": np.asarray(m.faces).tolist()} for m in meshes],
                "volume": float(out.volume)})
    return out
T._manifold_boolean = record
spec = importlib.util.spec_from_file_location("s", "/repo/patterns/structures/dovetailed_sawhorse.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
frame = m.dovetailed_sawhorse()
leg = [c for c in frame.cut_timbers if c.timber.ticket.path == 'leg +x +y'][0]
mesh_cutcsg(leg.render_timber_with_cuts_csg_local())
open('/out/ops.json', 'w').write(json.dumps(ops))
print(len(ops), 'ops')
