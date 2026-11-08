# Kumiki in Pyodide (spike)

Can kumiki run inside a web page, so Kigumi could live at kumiki.build/try with nothing to host? This
folder is the first test of that: kumiki in [Pyodide](https://pyodide.org), in Node, with Manifold's
WebAssembly build standing in for `manifold3d`.

```sh
cd kigumi/hosts/pyodide && npm install
node run-frame.mjs <repo> <repo>/patterns/structures/my_cute_frame.py my_cute_frame
```

`compare.py` builds a frame and meshes every timber, and prints each one's volume, face count and
whether it is watertight, with timings. Run it natively for the reference:
`.venv/bin/python kigumi/hosts/pyodide/compare.py <frame.py> <function>`.

## What runs where

- **Pyodide 0.28.3 (Python 3.13)** ships sympy, numpy, lxml, networkx, scipy and typing-extensions.
  trimesh is pure Python and comes from PyPI (micropip).
- **manifold3d** has no Pyodide build. kumiki uses only its booleans (`_manifold_boolean` in
  `kumiki/csg/triangles.py`), so `manifold3d.py` here plays that part over npm `manifold-3d` (the
  official WebAssembly build, which browser CAD tools such as OpenSCAD's playground use): a
  `Manifold` from a `Mesh64`, `batch_boolean`, subtraction, `to_mesh64`.
- kumiki itself loads from the repo unchanged.

## Findings (2026-11-07)

**It works.** kumiki imports and builds frames in Pyodide, and the stand-in meshes them.

| Frame | Timbers | Mesh time, native | Mesh time, Pyodide |
| --- | --- | --- | --- |
| my_cute_frame | 4 | 0.02 s | 0.06 s |
| dovetailed_sawhorse | 5 | 0.02 s | 0.05 s |
| cat_corner_cot | 96 | 0.13 s | 0.25 s |
| oscarshed | 25 | 0.11 s | 0.24 s (0.45 s with 1 km boxes) |
| tinyhouse120 | 75 | 0.52 s | 0.83 s |

Loading Pyodide and its packages takes about 2.5 s, and importing kumiki about 2-3.5 s, once.

**Precision: the browser build hands back float32.** Its meshes are float32 in and out (`MeshOptions`
takes a `tolerance`, which the stand-in sets small). Coordinates near a frame are precise to well
under a micron in float32, but kumiki meshes a half space as a box 2 km across and infinite prisms
100 m long, and chains booleans through those: an intersection of two half-space boxes came back
1.3 mm off at a kilometre, and by the last boolean a sawhorse leg had lost a ¾" face (57% of its
volume). Replaying the same operands through native manifold3d gives the same wrong answer, so the
stand-in is faithful; the difference is in what kumiki hands it.

With smaller boxes (prisms 10 m, half spaces 20 m) every frame above matches native to within 5e-7
of each timber's volume, all 205 timbers watertight.

**But the box size is fragile natively too.** With those same 10 m / 20 m boxes, native manifold3d
loses cuts on two sawhorse legs (31% of their volume); kumiki's own comment records the same at
10 km. The cuts survive or not by luck with the box sizes, on both runtimes.

## Next

1. **kumiki: size each half-space box and infinite prism to the solid it cuts,** not to a fixed
   size, so the booleans don't depend on luck (native and Pyodide alike). Check with the full test
   suite and this comparison.
2. Load kumiki and its packages in a browser page (a Web Worker), with `manifold-3d` from the same
   origin.
3. Kigumi's core in the page: run `kigumi/runner.py` in the worker, speaking its JSON-lines
   protocol, with the project's files in Pyodide's file system (from the browser's storage), and the
   existing shell, explorer and viewers on top.
