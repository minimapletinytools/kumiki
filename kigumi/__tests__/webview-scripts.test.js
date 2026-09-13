const fs = require('fs');
const path = require('path');

// The webview loads its modules as plain scripts, wired in three places at
// once: a <script> placeholder in viewer.html, a URI built in viewer.js, and a
// .replace() joining them. Miss any one and the module simply is not there --
// and because viewer-app.js reaches for these globals in its CONSTRUCTOR, a
// missing one throws before anything renders and the viewer comes up blank,
// with nothing on screen to say why.
//
// That has happened. These guard it.

const webviewDir = path.join(__dirname, '..', 'webview');
const html = fs.readFileSync(path.join(webviewDir, 'viewer.html'), 'utf8');
const viewerJs = fs.readFileSync(path.join(__dirname, '..', 'viewer.js'), 'utf8');

/** Every `__X_JS_URI__` the template asks for, in load order. */
const placeholders = [...html.matchAll(/src="(__[A-Z0-9_]+_URI__)"/g)].map((m) => m[1]);

/** Every placeholder viewer.js fills in, and the variable it fills it with. */
const filled = new Map(
    [...viewerJs.matchAll(/\.replace\('(__[A-Z0-9_]+_URI__)',\s*([A-Za-z0-9_]+)\)/g)]
        .map((m) => [m[1], m[2]]),
);

/**
 * Every `const someJsUri = ... path.join(webviewDir, ...) ...` viewer.js builds,
 * mapped to the path relative to webview/.
 *
 * Every quoted segment, not just the filename: the vendor scripts live a
 * directory down, and taking the last one alone loses where they are.
 */
const built = new Map(
    [...viewerJs.matchAll(/const\s+([A-Za-z0-9_]+)\s*=\s*webview\.asWebviewUri\([^;]*?path\.join\(webviewDir,([^)]*)\)/g)]
        .map(([, variable, args]) => [
            variable,
            path.join(...[...args.matchAll(/'([^']+)'/g)].map((m) => m[1])),
        ]),
);

describe('every script the template asks for is actually wired', () => {
    test.each(placeholders)('%s is filled in by viewer.js', (placeholder) => {
        expect(filled.has(placeholder)).toBe(true);
    });

    test.each(placeholders)('%s resolves to a file that exists', (placeholder) => {
        const file = built.get(filled.get(placeholder));

        expect(file).toBeDefined();
        expect(fs.existsSync(path.join(webviewDir, file))).toBe(true);
    });

    test('no placeholder is filled in that the template never asks for', () => {
        // A dead .replace() is the other half of the same mistake: the module
        // is built and never loaded.
        const asked = new Set(placeholders);
        const dead = [...filled.keys()].filter(
            (name) => !asked.has(name) && html.indexOf(name) === -1);

        expect(dead).toEqual([]);
    });
});

describe('every global the webview reaches for is loaded before it is used', () => {
    /** Which file defines each `globalScope.X = ...`. */
    const defines = new Map();
    for (const name of fs.readdirSync(webviewDir)) {
        if (!name.endsWith('.js')) {
            continue;
        }
        const source = fs.readFileSync(path.join(webviewDir, name), 'utf8');
        for (const match of source.matchAll(/globalScope\.([A-Za-z0-9_]+)\s*=/g)) {
            defines.set(match[1], name);
        }
    }

    /** The webview files loaded by the template, in order. */
    const loaded = placeholders
        .map((placeholder) => built.get(filled.get(placeholder)))
        .filter(Boolean);

    // Every `window.Kigumi*` or known store the app and its panels use.
    const used = new Set();
    for (const name of ['viewer-app.js', 'selection-panel.js', 'drawing-panel.js']) {
        const source = fs.readFileSync(path.join(webviewDir, name), 'utf8');
        for (const match of source.matchAll(/window\.([A-Za-z0-9_]+)/g)) {
            if (defines.has(match[1])) {
                used.add(match[1]);
            }
        }
    }

    test('there is something to check', () => {
        expect(used.size).toBeGreaterThan(5);
    });

    test.each([...used])('%s is defined by a script the template loads', (global) => {
        expect(loaded).toContain(defines.get(global));
    });

    test('and loaded before viewer-app.js, which uses them in its constructor', () => {
        const appAt = loaded.indexOf('viewer-app.js');
        const late = [...used].filter((global) => {
            const at = loaded.indexOf(defines.get(global));
            return appAt !== -1 && at > appAt;
        });

        expect(late).toEqual([]);
    });
});
