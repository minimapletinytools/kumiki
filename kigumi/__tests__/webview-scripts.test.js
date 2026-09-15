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

describe('every argument a shared decision takes is actually passed', () => {
    // choosePickAction gained `inDrawing`, was unit tested, and neither caller
    // was updated -- so in a drawing the store refused the timber selection,
    // the pick never became a 'csg', and nothing selected or hovered at all.
    // A pure function is easy to test and easy to leave unwired.
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');

    /** Each `choosePickAction({ ... })` call in the app, with its argument text. */
    function callsTo(name) {
        const calls = [];
        let at = app.indexOf(`${name}({`);
        while (at !== -1) {
            const open = app.indexOf('{', at);
            let depth = 0;
            let end = open;
            for (; end < app.length; end += 1) {
                if (app[end] === '{') depth += 1;
                if (app[end] === '}') {
                    depth -= 1;
                    if (depth === 0) break;
                }
            }
            calls.push(app.slice(open, end + 1));
            at = app.indexOf(`${name}({`, end);
        }
        return calls;
    }

    const picks = callsTo('choosePickAction');

    test('the app calls choosePickAction in more than one place', () => {
        expect(picks.length).toBeGreaterThan(1);
    });

    test.each(['hits', 'selectedTimbers', 'inDrawing', 'measuring'])(
        'every call passes %s', (argument) => {
            // Either spelling: `hits: along.hits` or the shorthand `hits,`.
            const passed = new RegExp(`\\b${argument}\\s*[,:}]`);
            const missing = picks.filter((call) => !passed.test(call));

            expect(missing).toEqual([]);
        },
    );
});

describe('the app asks the draft what is held, rather than deciding again', () => {
    // _heldForRequest tells the runner which end a pick is being measured
    // against. It decided that itself, as `state === HOLDING`, and so stopped
    // answering the moment a second end was picked -- leaving every further
    // pick judged as if nothing were held. The draft answers it now, and the
    // answer is unit tested there.
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');
    const at = app.indexOf('_heldForRequest() {');
    const body = app.slice(at, app.indexOf('\n    }', at));

    test('there is a _heldForRequest to check', () => {
        expect(at).toBeGreaterThan(-1);
    });

    test('it reads the held end off the draft', () => {
        expect(body).toContain('heldEnd');
    });

    test('and does not re-decide which states still hold one', () => {
        // PENDING holds a first end too. Naming one state here is the bug.
        expect(body).not.toContain('STATES.HOLDING');
    });
});

describe('the hover redraws when the verdict changes, not just the feature', () => {
    // handleHoverResult skips redrawing an answer about the same feature. The
    // colour it draws says whether the click will be taken, and that turns on
    // what is held -- so the skip has to account for it. Comparing features
    // alone left the highlight green over a pair that could not be measured.
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');

    test('it compares whole highlights', () => {
        expect(app).toContain('HoverState.sameHighlight');
    });

    test('and never the feature alone, which is the weaker question', () => {
        expect(app).not.toContain('HoverState.sameFeature');
    });

    test('with one place judging what counts as refused', () => {
        // The hover colour and the click refusal must agree, so both ask the
        // same function rather than each testing kinds.length.
        expect(app).not.toContain('kinds.length === 0');
    });
});

describe('the hover is asked again whenever the held end changes', () => {
    // The hover only asks a question when the pointer moves. Taking, releasing
    // or confirming an end is a button or a key, so the pointer does not move
    // -- and the colour under it, which says whether a click will be taken,
    // depends on exactly that. Without a re-ask the verdict on screen is the
    // one from before, however right the comparison that draws it.
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');

    /** The body of a no-argument method, by brace matching. */
    function body(name) {
        const at = app.indexOf(`\n    ${name}() {`);
        if (at === -1) {
            throw new Error(`${name} is not a method of viewer-app.js`);
        }
        const open = app.indexOf('{', at + name.length + 5);
        let depth = 0;
        for (let end = open; end < app.length; end += 1) {
            if (app[end] === '{') depth += 1;
            if (app[end] === '}') {
                depth -= 1;
                if (depth === 0) return app.slice(open, end + 1);
            }
        }
        throw new Error(`${name} is never closed`);
    }

    test.each([
        'startMeasurementFromFocus',
        'escapeMeasurement',
        'confirmMeasurement',
        'clearMeasureDraft',
    ])('%s asks the hover again', (method) => {
        expect(body(method)).toContain('_reaskHover');
    });
});
