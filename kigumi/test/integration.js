#!/usr/bin/env node
/**
 * Kigumi's integration tests, by name: the standalone app's scenarios (test/app), the extension in
 * VS Code (test/suite) and Kigumi in a browser (hosts/pyodide/test). Unit tests are `npm test`.
 *
 *   npm run test:int -- --list            what there is
 *   npm run test:int -- core              the ones to run on any change
 *   npm run test:int -- app:drawings vscode:parameters
 *   npm run test:int -- app               every suite of one host
 *   npm run test:int -- all               what CI runs: all but those needing another checkout,
 *                                         which run only when named (web:mcp)
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const KIGUMI = path.resolve(__dirname, '..');

// `covers` names the workflows in docs/internal/agent-generated/kigumi-workflows.md they check.
// `core` suites are quick and cover the main workflow on each host.
const SUITES = [
    { name: 'app:explorer', core: true, covers: 'explorer, open frame' },
    { name: 'app:viewer', core: true, covers: 'view a frame, select, camera, rebuild on save' },
    { name: 'app:drawings', core: true, covers: 'drawings, measurements' },
    { name: 'app:parameters', core: true, covers: 'kiwari parameters' },
    { name: 'app:projects', core: true, covers: 'open, make and close projects' },
    { name: 'app:tabs-and-editors', core: true, covers: 'tabs, source editor, read-only files' },
    { name: 'app:log', core: true, covers: 'build errors, the log' },
    { name: 'app:stl-placement', covers: 'mesh timbers' },
    { name: 'app:new-files', covers: 'new frame, new file' },
    { name: 'app:shared', covers: 'share links' },
    { name: 'app:sidebar', covers: 'viewer sidebar' },
    { name: 'app:mcp', covers: 'MCP server' },
    { name: 'app:quick-pick', covers: 'quick pick' },
    { name: 'app:go-to-file', covers: 'go to file, open in viewer' },
    { name: 'app:layout', covers: 'window layout' },
    { name: 'app:recent-folders', covers: 'recent projects' },
    { name: 'app:switch-project', covers: 'switch project' },
    { name: 'app:agent', covers: 'agent panel' },
    { name: 'app:settings', covers: 'settings' },
    { name: 'app:keyboard-shortcuts', covers: 'keyboard shortcuts' },
    { name: 'app:crash-recovery', covers: 'crash recovery' },
    { name: 'vscode:smoke', core: true, covers: 'extension activates' },
    { name: 'vscode:initial-state', core: true, covers: 'explorer, view a frame (VS Code)' },
    { name: 'vscode:automation', covers: 'automation commands' },
    { name: 'vscode:assembly', covers: 'assembly timeline' },
    { name: 'vscode:fixture-switching', covers: 'several views, explorer grouping, patterns' },
    { name: 'vscode:initialization', covers: 'initialize a project' },
    { name: 'vscode:parameters', covers: 'kiwari parameters (VS Code)' },
    { name: 'web:browser', covers: 'browser: projects, view, save, zip, reload' },
    { name: 'web:phone', covers: 'phone layout' },
    { name: 'web:mcp', covers: 'browser MCP', needs: 'a kigumi-backend checkout (KIGUMI_BACKEND_DIR)' },
];

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
            const note = [suite.core ? 'core' : '', suite.needs ? `needs ${suite.needs}` : ''].filter(Boolean).join('; ');
            console.log(`${suite.name.padEnd(width)}  ${suite.covers}${note ? `  [${note}]` : ''}`);
        }
        console.log(`\nnpm run test:int -- core | all | <host> | <name>...   (hosts: app, vscode, web; ${os.platform()})`);
        return;
    }
    const failed = runSuites(choose(args));
    console.log(failed.length ? `\nFailed: ${failed.join('; ')}` : '\nAll integration suites passed.');
    process.exitCode = failed.length ? 1 : 0;
}

if (require.main === module) main();

module.exports = { SUITES, choose };
