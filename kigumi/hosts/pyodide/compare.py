"""Build a frame and mesh each timber: volumes, sizes and times, as JSON. Runs natively and in Pyodide."""
import json, sys, time, importlib.util

def run(frame_file, function):
    t0 = time.time()
    import kumiki
    from kumiki.csg.triangles import mesh_cutcsg
    t_import = time.time() - t0
    spec = importlib.util.spec_from_file_location("frame_under_test", frame_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    t1 = time.time()
    frame = getattr(module, function)()
    t_build = time.time() - t1
    t2 = time.time()
    timbers = []
    for cut in frame.cut_timbers:
        mesh = mesh_cutcsg(cut.render_timber_with_cuts_csg_local())
        mesh = getattr(mesh, "mesh", mesh)
        timbers.append({"name": cut.timber.ticket.path, "volume": float(mesh.volume), "faces": int(len(mesh.faces)),
                        "watertight": bool(mesh.is_watertight)})
    t_mesh = time.time() - t2
    return {"import_s": round(t_import, 2), "build_s": round(t_build, 2), "mesh_s": round(t_mesh, 2), "timbers": timbers}

if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1], sys.argv[2])))
