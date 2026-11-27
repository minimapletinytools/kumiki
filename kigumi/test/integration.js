#!/usr/bin/env node
/**
 * Kigumi's integration tests, by name: the standalone app's scenarios (test/app), the extension in
 * VS Code (test/suite) and Kigumi in a browser (hosts/pyodide/test). Unit tests are `npm test`.
 *
 *   npm run test:int -- --list            what there is
 *   npm run test:int -- core              the ones to run on any change
 *   npm run test:int -- app:drawings vscode:parameters
 *   npm run test:int -- app               every suite of one host
 *   npm run test:int -- all               all but those needing another checkout, which run only
 *                                         when named (web:mcp); CI runs this on pushes to main
 *   npm run test:int -- app --changed origin/main
 *                                         of those, only the core suites and those whose `paths`
 *                                         changed since origin/main; CI runs this on pull requests
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const KIGUMI = path.resolve(__dirname, '..');

// `covers` names the workflows in docs/internal/agent-generated/kigumi-workflows.md they check.
// `core` suites are quick and cover the main workflow on each host: they always run. The others
// run with --changed only when a file matching their `paths` (repo-relative globs) changed.
// `seconds` is roughly what each took in CI (2026-11-25), to show what gating saves.
const SHELL = ['kigumi/webview/shell/**', 'kigumi/hosts/electron/**'];
const SUITES = [
    { name: 'app:explorer', core: true, seconds: 4, covers: 'explorer, open frame' },
    { name: 'app:viewer', core: true, seconds: 12, covers: 'view a frame, select, camera, rebuild on save' },
    { name: 'app:parameters', core: true, seconds: 10, covers: 'kiwari parameters' },
    { name: 'app:projects', core: true, seconds: 1, covers: 'open, make and close projects' },
    { name: 'app:tabs-and-editors', core: true, seconds: 9, covers: 'tabs, source editor, read-only files' },
    { name: 'app:log', core: true, seconds: 19, covers: 'build errors, the log' },
    { name: 'app:drawings', seconds: 89, covers: 'drawings, measurements', paths: [
        'kigumi/webview/viewer-drawings.js', 'kigumi/webview/drawing-*.js', 'kigumi/webview/measure*.js',
        'kigumi/webview/viewer-measuring.js', 'kigumi/webview/scale-ruler.js', 'kigumi/webview/dimension-text.js',
        'kigumi/webview/highlights.js', 'kigumi/webview/feature-states.js', 'kigumi/webview/hover-state.js',
        'kumiki/drawings/**', 'kumiki/viewer/picking.py', 'hidden_structures/my_cute_frame_drawing_test.py',
        'patterns/structures/my_cute_frame.py'] },
    { name: 'app:layout-edit', seconds: 30, covers: 'editing a drawing\'s layout', paths: [
        'kigumi/webview/viewer-layout-editing.js', 'kigumi/webview/viewport-layout.js', 'kumiki/drawings/layout.py',
        'hidden_structures/my_cute_frame_drawing_test.py'] },
    { name: 'app:stl-placement', seconds: 35, covers: 'mesh timbers', paths: [
        'kigumi/webview/stl-placement-*.js', 'kigumi/stl_placement.py', 'kigumi/stl-placement-source.js', 'kumiki/stl.py'] },
    { name: 'app:new-files', seconds: 14, covers: 'new frame, new file', paths: [
        'kigumi/new-files.js', 'kigumi/project-initializer.js', 'patterns/structures/my_cute_frame.py'] },
    { name: 'app:shared', seconds: 21, covers: 'share links', paths: [
        'kigumi/publishes.js', 'kigumi/library.js', 'kigumi/read-only.js', 'kigumi/agent/shared-tools.js'] },
    { name: 'app:sidebar', seconds: 9, covers: 'viewer sidebar', paths: [
        'kigumi/webview/view-sidebar.js', 'kigumi/webview/viewer-panels.js', 'kigumi/webview/kiwari-values.js'] },
    { name: 'app:mcp', seconds: 13, covers: 'MCP server', paths: ['kigumi/agent/mcp-*.js'] },
    { name: 'app:quick-pick', seconds: 7, covers: 'quick pick', paths: SHELL },
    { name: 'app:go-to-file', seconds: 1, covers: 'go to file, open in viewer', paths: SHELL },
    { name: 'app:layout', seconds: 1, covers: 'window layout', paths: SHELL },
    { name: 'app:recent-folders', seconds: 1, covers: 'recent projects', paths: SHELL },
    { name: 'app:switch-project', seconds: 15, covers: 'switch project', paths: [...SHELL, 'kigumi/project-root.js'] },
    { name: 'app:agent', seconds: 15, covers: 'agent panel', paths: ['kigumi/agent/**', 'kigumi/webview/agent/**'] },
    { name: 'app:settings', seconds: 1, covers: 'settings', paths: SHELL },
    { name: 'app:keyboard-shortcuts', seconds: 9, covers: 'keyboard shortcuts', paths: [...SHELL, 'kigumi/keybindings.js'] },
    { name: 'app:crash-recovery', seconds: 5, covers: 'crash recovery', paths: [...SHELL, 'kigumi/runner-session.js'] },
    { name: 'vscode:smoke', core: true, seconds: 2, covers: 'extension activates' },
    { name: 'vscode:initial-state', core: true, seconds: 10, covers: 'explorer, view a frame (VS Code)' },
    { name: 'vscode:automation', seconds: 4, covers: 'automation commands', paths: ['kigumi/kigumi-app.js', 'kigumi/extension.js'] },
    { name: 'vscode:assembly', seconds: 2, covers: 'assembly timeline', paths: [
        'kigumi/webview/assembly-timeline.js', 'kigumi/webview/viewer-assembly.js', 'kumiki/assembly.py'] },
    { name: 'vscode:fixture-switching', seconds: 7, covers: 'several views, explorer grouping, patterns', paths: [
        'kigumi/sidebar-*.js', 'kigumi/frame-view-session.js', 'kigumi/frame-scanner.js'] },
    { name: 'vscode:initialization', seconds: 8, covers: 'initialize a project', paths: [
        'kigumi/project-initializer.js', 'kigumi/python-*.js', 'patterns/structures/my_cute_frame.py'] },
    { name: 'vscode:parameters', seconds: 3, covers: 'kiwari parameters (VS Code)', paths: [
        'kigumi/webview/kiwari-values.js', 'kigumi/webview/viewer-panels.js', 'kumiki/kiwari.py'] },
    { name: 'web:browser', seconds: 90, covers: 'browser: projects, view, save, zip, reload', paths: [
        'kigumi/hosts/pyodide/**', 'kigumi/host.js', 'pyproject.toml', 'uv.lock'] },
    { name: 'web:phone', seconds: 28, covers: 'phone layout', paths: [
        'kigumi/hosts/pyodide/**', 'kigumi/webview/shell/phone*', 'kigumi/webview/viewer-compact.js',
        'kigumi/webview/touch-navigation.js'] },
    { name: 'web:mcp', covers: 'browser MCP', needs: 'a kigumi-backend checkout (KIGUMI_BACKEND_DIR)' },
];

// A change to any of these may break every suite of a host, so they all run.
const HARNESS = {
    app: ['kigumi/test/app/*.js', 'kigumi/test/integration.js'],
    vscode: ['kigumi/test/suite/index.js', 'kigumi/test/suite/suites.js', 'kigumi/test/run-extension-tests.js',
        'kigumi/test/integration.js'],
    web: ['kigumi/hosts/pyodide/test/node-runner.mjs', 'kigumi/test/integration.js'],
};
const EVERYTHING = ['kigumi/package.json', 'kigumi/package-lock.json', '.github/workflows/kigumi-tests.yml'];

/** Return whether repo-relative `file` matches `glob` (`**` any path, `*` within one name). */
function matches(file, glob) {
    const pattern = glob.split('**').map((part) => part.split('*').map((text) => text.replace(/[.+?^${}()|[\]\\]/g, '\\$&'))
        .join('[^/]*')).join('.*');
    return new RegExp(`^${pattern}$`).test(file);
}

/** Return the files a suite's own test lives in, repo-relative. */
function ownFiles(suite) {
    const [host, name] = suite.name.split(':');
    if (host === 'app') return [`kigumi/test/app/scenarios/${name}.js`];
    if (host === 'web') return [`kigumi/hosts/pyodide/test/${name}-smoke.cjs`];
    const { FILES } = require('./suite/suites');
    return FILES[name] ? [`kigumi/test/suite/${FILES[name]}`] : [];
}

/** Return which of `suites` `changedFiles` (repo-relative) call for: the core ones, and any whose paths changed. */
function affected(suites, changedFiles) {
    const any = (globs) => changedFiles.some((file) => globs.some((glob) => matches(file, glob)));
    if (any(EVERYTHING)) return suites;
    return suites.filter((suite) => {
        const host = suite.name.split(':')[0];
        return suite.core || any(HARNESS[host] || []) || any(suite.paths || []) || any(ownFiles(suite));
    });
}

/** Return the files changed since `base` (a git ref), repo-relative. */
function changedSince(base) {
    const result = spawnSync('git', ['diff', '--name-only', `${base}...HEAD`], { cwd: KIGUMI, encoding: 'utf8' });
    if (result.status !== 0) throw new Error(`git diff against ${base} failed: ${result.stderr}`);
    return result.stdout.split('\n').map((line) => line.trim()).filter(Boolean);
}

function choose(args) {
    const picked = new Set();
    for (const arg of args) {
        // A suite that needs something else set up runs only when named.
        const matches = SUITES.filter((suite) => suite.name === arg || (!suite.needs
            && (arg === 'all' || (arg === 'core' && suite.core) || suite.name.startsWith(`${arg}:`))));
        if (matches.length === 0) throw new Error(`No integration suite '${arg}'. See --list.`);
        for (const suite of matches) picked.add(suite);
    }
    return [...picked];
}

function run(command, args, options = {}) {
    console.log(`\n$ ${command} ${args.join(' ')}`);
    const env = { ...process.env, ...options.env };
    delete env.ELECTRON_RUN_AS_NODE;
    return spawnSync(command, args, { cwd: options.cwd || KIGUMI, stdio: 'inherit', env }).status === 0;
}

const electron = () => require('electron');
// No GPU (CI): draw with SwiftShader.
const GL_FLAGS = process.env.KIGUMI_SOFTWARE_GL === '1'
    ? ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] : [];

/** Run `suites`, one launch per host; return the names of the hosts that failed. */
function runSuites(suites) {
    const of = (host) => suites.filter((suite) => suite.name.startsWith(`${host}:`)).map((suite) => suite.name.split(':')[1]);
    const failed = [];
    const app = of('app');
    if (app.length && !run('node', ['test/app/run-app-tests.js'], { env: { KIGUMI_TEST_SCENARIO: app.join(',') } })) {
        failed.push(`app (${app.join(', ')})`);
    }
    const vscode = of('vscode');
    if (vscode.length && !run('node', ['test/run-extension-tests.js', '--suite', vscode.join(',')])) {
        failed.push(`vscode (${vscode.join(', ')})`);
    }
    const web = of('web');
    if (web.length) {
        const pyodide = path.join(KIGUMI, 'hosts', 'pyodide');
        if (!fs.existsSync(path.join(pyodide, 'node_modules')) && !run('npm', ['install'], { cwd: pyodide })) {
            failed.push('web (npm install)');
        } else if (!run('npm', ['run', 'build'], { cwd: pyodide })) {
            failed.push('web (build)');
        } else {
            for (const name of web) {
                if (!run(electron(), [path.join('test', `${name}-smoke.cjs`), ...GL_FLAGS], { cwd: pyodide })) failed.push(`web:${name}`);
            }
        }
    }
    return failed;
}

function main() {
    const args = process.argv.slice(2);
    if (args.length === 0 || args.includes('--list')) {
        const width = Math.max(...SUITES.map((suite) => suite.name.length));
        for (const suite of SUITES) {
            const note = [suite.core ? 'core' : '', suite.seconds ? `~${suite.seconds}s` : '',
                suite.needs ? `needs ${suite.needs}` : ''].filter(Boolean).join('; ');
            console.log(`${suite.name.padEnd(width)}  ${suite.covers}${note ? `  [${note}]` : ''}`);
        }
        console.log(`\nnpm run test:int -- core | all | <host> | <name>... [--changed <git ref>]   (hosts: app, vscode, web; ${os.platform()})`);
        return;
    }
    const at = args.indexOf('--changed');
    let chosen;
    if (at >= 0) {
        const base = args[at + 1];
        if (!base) throw new Error('--changed takes a git ref to compare with, e.g. origin/main');
        const rest = args.filter((_, index) => index !== at && index !== at + 1);
        const changed = changedSince(base);
        chosen = affected(choose(rest.length ? rest : ['all']), changed);
        const skipped = choose(rest.length ? rest : ['all']).filter((suite) => !chosen.includes(suite));
        console.log(`${changed.length} file(s) changed since ${base}; running ${chosen.map((suite) => suite.name).join(', ') || 'nothing'}`
            + (skipped.length ? `; skipping ${skipped.map((suite) => suite.name).join(', ')}` : ''));
    } else {
        chosen = choose(args);
    }
    const failed = runSuites(chosen);
    console.log(failed.length ? `\nFailed: ${failed.join('; ')}` : '\nAll integration suites passed.');
    process.exitCode = failed.length ? 1 : 0;
}

if (require.main === module) main();

module.exports = { SUITES, choose, affected, matches };
