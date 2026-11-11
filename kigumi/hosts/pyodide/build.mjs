// Build Kigumi in a browser into dist/: static files, nothing to run on a server.
//
//   dist/index.html            the app's shell page, with the page scripts (page/) before shell.js
//   dist/auth.html             where signing in to the agent's account comes back to
//   dist/worker.js             Kigumi's core and its Node stand-ins (worker/), bundled
//   dist/webview/              the shell, explorer, viewer and editor pages and their assets
//   dist/page/                 the page's scripts: the worker connection and the projects page
//   dist/kigumi-files.json     files the core and Python read at run time (runner.py, templates, ...),
//                              written into Pyodide's file system when the worker starts
//   dist/kumiki-*.whl          kumiki, built from this checkout
//
//   node build.mjs   (from kigumi/hosts/pyodide, after npm install)

import * as esbuild from 'esbuild';
import { execFileSync } from 'child_process';
import { createHash } from 'crypto';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const KIGUMI = path.resolve(HERE, '../..');
const REPO = path.resolve(KIGUMI, '..');
const DIST = path.join(HERE, 'dist');

// Where each file is in Pyodide's file system: kigumi/ at /kigumi, the repo's docs at /docs.
function virtualPath(file) {
    const relative = path.relative(REPO, file).split(path.sep).join('/');
    return `/${relative}`;
}

const shims = {
    fs: path.join(HERE, 'worker/shims/fs.js'),
    child_process: path.join(HERE, 'worker/shims/child_process.js'),
    os: path.join(HERE, 'worker/shims/os.js'),
    https: path.join(HERE, 'worker/shims/https.js'),
    crypto: path.join(HERE, 'worker/shims/crypto.js'),
    worker_threads: path.join(HERE, 'worker/shims/worker_threads.js'),
    path: path.join(HERE, 'node_modules/path-browserify/index.js'),
};

// Each module's __dirname and __filename, as it would be in Pyodide's file system.
const dirnamePlugin = {
    name: 'virtual-dirname',
    setup(build) {
        build.onLoad({ filter: /\.js$/ }, async (args) => {
            if (!args.path.startsWith(KIGUMI) || args.path.includes(`${path.sep}node_modules${path.sep}`)) return undefined;
            const source = await fs.promises.readFile(args.path, 'utf8');
            if (!/__dirname|__filename/.test(source)) return undefined;
            const file = virtualPath(args.path);
            return { contents: `var __filename = ${JSON.stringify(file)}; var __dirname = ${JSON.stringify(path.posix.dirname(file))};\n${source}`, loader: 'js' };
        });
    },
};

function copyDir(from, to, skip = () => false) {
    fs.mkdirSync(to, { recursive: true });
    for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
        const source = path.join(from, entry.name);
        if (skip(source)) continue;
        if (entry.isDirectory()) copyDir(source, path.join(to, entry.name), skip);
        else fs.copyFileSync(source, path.join(to, entry.name));
    }
}

function walk(dir, keep, out = []) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            if (!['node_modules', 'vendor', '__pycache__'].includes(entry.name)) walk(full, keep, out);
        } else if (keep(full)) {
            out.push(full);
        }
    }
    return out;
}

fs.rmSync(DIST, { recursive: true, force: true });
fs.mkdirSync(DIST, { recursive: true });

// The worker: Kigumi's core, with Node's modules played by the stand-ins.
await esbuild.build({
    entryPoints: [path.join(HERE, 'worker/main.js')],
    outfile: path.join(DIST, 'worker.js'),
    bundle: true,
    format: 'esm',
    platform: 'browser',
    target: 'es2022',
    alias: shims,
    inject: [path.join(HERE, 'worker/shims/globals.mjs')],
    plugins: [dirnamePlugin],
    external: ['electron'],
    logLevel: 'warning',
    sourcemap: 'linked',
});

// The pages and their assets, and the page's own scripts.
copyDir(path.join(KIGUMI, 'webview'), path.join(DIST, 'webview'));
copyDir(path.join(HERE, 'page'), path.join(DIST, 'page'), (file) => /auth\.(html|js)$/.test(file));

// The sign-in page, its script inline and allowed by its hash.
const authScript = fs.readFileSync(path.join(HERE, 'page/auth.js'), 'utf8');
const authHash = createHash('sha256').update(authScript).digest('base64');
fs.writeFileSync(path.join(DIST, 'auth.html'), fs.readFileSync(path.join(HERE, 'page/auth.html'), 'utf8')
    .replace('AUTHHASH', authHash).replace('AUTHSCRIPT', () => authScript));

// The shell page's policy. Panels are shown as blobs, and a blob page also gets the policy of the page
// that made it, so this one allows what the panels need (inline scripts and styles); each panel's own
// policy, which names its scripts by nonce, still applies on top.
const SHELL_POLICY = [
    "default-src 'none'",
    "script-src 'self' 'unsafe-inline' blob:",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    "img-src 'self' data: blob:",
    "frame-src 'self' blob:",
    "worker-src 'self' blob:",
    "connect-src 'self'",
].join('; ');

// The shell page, with the page scripts first and room for blob panels and the worker.
const shell = fs.readFileSync(path.join(KIGUMI, 'webview/shell/shell.html'), 'utf8');
const index = shell
    .replace(/<meta http-equiv="Content-Security-Policy" content="[^"]*">/, `<meta http-equiv="Content-Security-Policy" content="${SHELL_POLICY}">`)
    .replace('<head>', '<head>\n    <base href="webview/shell/">')
    .replace('<link rel="stylesheet" href="shell.css">', '<link rel="stylesheet" href="shell.css">\n    <link rel="stylesheet" href="../../page/web.css">\n    <link rel="icon" type="image/png" href="../../page/favicon.png">')
    .replace('<script src="shell.js">', ['zip.js', 'web-projects.js', 'loading.js', 'transport.js']
        .map((name) => `<script src="../../page/${name}"></script>`).join('\n    ') + '\n    <script src="shell.js">');
if (index === shell || !index.includes('page/transport.js')) throw new Error('shell.html changed: update build.mjs');
fs.writeFileSync(path.join(DIST, 'index.html'), index);

// Files the core and Python read at run time.
const runtimeFiles = [
    path.join(KIGUMI, 'package.json'),
    path.join(KIGUMI, 'legacy-doc-hashes.json'),
    ...fs.readdirSync(KIGUMI).filter((name) => name.endsWith('.py')).map((name) => path.join(KIGUMI, name)),
    // The agent's instructions and its kumiki_api tool's script.
    path.join(KIGUMI, 'agent/system-prompt.md'),
    path.join(KIGUMI, 'agent/kumiki_api.py'),
    ...walk(path.join(KIGUMI, 'webview'), (file) => file.endsWith('.html')),
    ...walk(path.join(KIGUMI, 'i18n/locales'), (file) => file.endsWith('.json')),
    ...walk(path.join(REPO, 'docs'), (file) => file.endsWith('.md') && !file.includes(`${path.sep}internal${path.sep}`)),
].filter((file) => fs.existsSync(file));
const files = Object.fromEntries(runtimeFiles.map((file) => [virtualPath(file), fs.readFileSync(file, 'utf8')]));
for (const name of ['manifold3d.py', 'kigumi_pyodide.py']) {
    const source = name === 'manifold3d.py' ? path.join(HERE, name) : path.join(HERE, 'python', name);
    files[`/python/${name}`] = fs.readFileSync(source, 'utf8');
}
fs.writeFileSync(path.join(DIST, 'kigumi-files.json'), JSON.stringify(files));

// kumiki, as a wheel built from this checkout.
execFileSync('uv', ['build', '--wheel', '--out-dir', DIST, '-q'], { cwd: REPO, stdio: 'inherit' });
const wheel = fs.readdirSync(DIST).find((name) => name.endsWith('.whl'));
fs.writeFileSync(path.join(DIST, 'manifest.json'), JSON.stringify({ wheel }));

console.log(`Built ${path.relative(process.cwd(), DIST) || 'dist'}: ${wheel}, ${Object.keys(files).length} runtime files.`);
