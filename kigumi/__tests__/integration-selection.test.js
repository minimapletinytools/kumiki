const { SUITES, affected, choose, matches } = require('../test/integration');

const runnable = SUITES.filter((suite) => !suite.needs);
const extra = (files) => affected(runnable, files).filter((suite) => !suite.core).map((suite) => suite.name);

describe('which integration suites a change runs', () => {
    test('the core suites always run, and nothing else for a change no suite names', () => {
        const chosen = affected(runnable, ['kumiki/joints/workshop/mixed/mortise_and_tenon_joints.py']);
        expect(chosen.every((suite) => suite.core)).toBe(true);
        expect(chosen.length).toBe(runnable.filter((suite) => suite.core).length);
    });

    test('a slow suite runs when its feature changes', () => {
        expect(extra(['kigumi/webview/viewer-drawings.js'])).toEqual(['app:drawings']);
        expect(extra(['kumiki/drawings/svg.py'])).toEqual(['app:drawings']);
        expect(extra(['kigumi/hosts/pyodide/worker/main.js'])).toEqual(['web:browser', 'web:phone']);
    });

    test('a suite runs when its own test changes, and every suite of a host when its harness does', () => {
        expect(extra(['kigumi/test/app/scenarios/shared.js'])).toEqual(['app:shared']);
        expect(extra(['kigumi/test/app/helpers.js'])).toEqual(runnable
            .filter((suite) => !suite.core && suite.name.startsWith('app:')).map((suite) => suite.name));
    });

    test('a change to the dependencies or the workflow runs everything', () => {
        expect(affected(runnable, ['kigumi/package.json'])).toEqual(runnable);
    });

    test('only within what was asked for', () => {
        expect(affected(choose(['vscode']), ['kigumi/webview/viewer-drawings.js']).every((suite) => suite.name.startsWith('vscode:'))).toBe(true);
    });

    test('globs: ** spans folders, * stays within a name', () => {
        expect(matches('kumiki/drawings/sub/x.py', 'kumiki/drawings/**')).toBe(true);
        expect(matches('kigumi/webview/drawing-panel.js', 'kigumi/webview/drawing-*.js')).toBe(true);
        expect(matches('kigumi/webview/sub/x.js', 'kigumi/webview/*.js')).toBe(false);
    });
});
