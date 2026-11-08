// The worker's Python, in Node: install the built wheel and the bridge, then start a runner on a frame
// and send it a request. For debugging the bridge without a browser.
import { loadPyodide } from 'pyodide';
import Manifold from 'manifold-3d';
import fs from 'fs';
import path from 'path';
const dist = new URL('../dist/', import.meta.url).pathname;
const [frame] = process.argv.slice(2);
const py = await loadPyodide({ env: { HOME: '/home/pyodide', KUMIKI_TRIANGLES_PRISM_EXTENT: '10', KUMIKI_TRIANGLES_HALF_SPACE_EXTENT: '20' } });
await py.loadPackage(['numpy', 'sympy', 'lxml', 'networkx', 'scipy', 'typing-extensions', 'micropip'], { messageCallback: () => {} });
await py.pyimport('micropip').install('trimesh==4.11.3');
const wheel = JSON.parse(fs.readFileSync(path.join(dist, 'manifest.json'))).wheel;
py.FS.writeFile(`/tmp/${wheel}`, fs.readFileSync(path.join(dist, wheel)));
await py.runPythonAsync(`import micropip\nawait micropip.install('emfs:/tmp/${wheel}', deps=False)`);
const wasm = await Manifold(); wasm.setup();
py.registerJsModule('_manifold_wasm', { Manifold: wasm.Manifold, Mesh: wasm.Mesh });
const files = JSON.parse(fs.readFileSync(path.join(dist, 'kigumi-files.json')));
for (const [file, text] of Object.entries(files)) { py.FS.mkdirTree(path.dirname(file)); py.FS.writeFile(file, text); }
const site = py.runPython('import site; site.getsitepackages()[0]');
py.FS.writeFile(`${site}/manifold3d.py`, files['/python/manifold3d.py']);
py.FS.writeFile(`${site}/kigumi_pyodide.py`, files['/python/kigumi_pyodide.py']);
const project = '/home/pyodide/projects/p/Shed';
py.FS.mkdirTree(`${project}/.kigumi`);
py.FS.writeFile(`${project}/.kigumi/kumiki.yaml`, 'kumiki_version: latest\n');
py.FS.writeFile(`${project}/my_cute_frame.py`, fs.readFileSync(frame));
const bridge = py.pyimport('kigumi_pyodide');
const out = [];
const session = bridge.RunnerSession('/kigumi/runner.py', JSON.stringify([`${project}/my_cute_frame.py`, project]),
    (line) => out.push(line.trim()), (line) => process.stderr.write(line));
console.log('started', session.start());
for (const line of out.splice(0)) console.log('OUT', line.slice(0, 300));
session.handle(JSON.stringify({ id: 1, command: 'get_frame', payload: {} }));
for (const line of out.splice(0)) console.log('OUT', line.slice(0, 300));
