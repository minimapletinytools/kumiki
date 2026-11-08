// Kumiki in Pyodide, in Node, with manifold3d played by Manifold's WebAssembly build (manifold3d.py).
// Builds a frame and meshes every timber; prints compare.py's JSON (volumes, faces, watertight, times).
//
//   node run-frame.mjs <repo> <frame.py> <frame function>
//
// TRIMESH=trimesh==4.11.3 pins trimesh; DEBUG=<folder> records the booleans of one sawhorse leg there
// (record_booleans.py) instead.
import { loadPyodide } from 'pyodide';
import Manifold from 'manifold-3d';
import fs from 'fs';
const [repo, frameFile, fn] = process.argv.slice(2);
const t0 = Date.now();
const wasm = await Manifold();
wasm.setup();
const py = await loadPyodide();
await py.loadPackage(['numpy', 'sympy', 'lxml', 'networkx', 'micropip', 'scipy', 'typing-extensions'], { messageCallback: () => {} });
await py.pyimport('micropip').install(process.env.TRIMESH || 'trimesh');
const tLoad = (Date.now() - t0) / 1000;
py.mountNodeFS('/repo', repo);
if (process.env.DEBUG) { py.FS.mkdirTree('/out'); py.mountNodeFS('/out', process.env.DEBUG); }
py.registerJsModule('_manifold_wasm', { Manifold: wasm.Manifold, Mesh: wasm.Mesh });
py.FS.writeFile('/home/pyodide/manifold3d.py', fs.readFileSync(new URL('./manifold3d.py', import.meta.url)));
py.FS.writeFile('/home/pyodide/compare.py', fs.readFileSync(new URL('./compare.py', import.meta.url)));
if (process.env.DEBUG) {
  py.FS.writeFile('/home/pyodide/record_booleans.py', fs.readFileSync(new URL('./record_booleans.py', import.meta.url)));
  await py.runPythonAsync("import sys; sys.path[:0] = ['/home/pyodide', '/repo']; import record_booleans");
  process.exit(0);
}
const result = await py.runPythonAsync(`
import sys, json
sys.path[:0] = ['/home/pyodide', '/repo']
import compare
json.dumps(compare.run(${JSON.stringify(frameFile.replace(repo, '/repo'))}, ${JSON.stringify(fn)}))
`);
const out = JSON.parse(result);
out.load_s = tLoad;
console.log(JSON.stringify(out));
