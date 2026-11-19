const fs = require('fs');
const path = require('path');
const { viewerSource, viewerSourceFiles } = require('../test/viewer-source');

// The webview loads its modules as plain scripts, wired in two places at
// once: a <script> placeholder in viewer.html and a row of WEBVIEW_ASSETS in
// viewer.js. Miss either one and the module simply is not there --
// and because viewer-app.js reaches for these globals in its CONSTRUCTOR, a
// missing one throws before anything renders and the viewer comes up blank,
// with nothing on screen to say why.
//
// That has happened. These guard it.

const webviewDir = path.join(__dirname, '..', 'webview');
/**
 * The body of a method of viewer-app.js, by brace matching.
 *
 * The opening brace is found after the PARAMETER LIST closes, not at the first
 * brace after the name: `_memberAppearance(key, bundle, { a, b, c })` puts one
 * in its own parameters, and taking that one reads the destructuring pattern as
 * though it were the method -- which quietly reported six of its twelve reads.
 */
function methodBody(source, name) {
    const at = source.search(new RegExp(`\\n    ${name}\\(`));
    if (at === -1) {
        throw new Error(`${name} is not a method of viewer-app.js`);
    }
    const params = source.indexOf('(', at);
    let depth = 0;
    let open = -1;
    for (let i = params; i < source.length; i += 1) {
        if (source[i] === '(') depth += 1;
        if (source[i] === ')') {
            depth -= 1;
            if (depth === 0) {
                open = source.indexOf('{', i);
                break;
            }
        }
    }
    if (open === -1) {
        throw new Error(`${name} has no body`);
    }
    depth = 0;
    for (let end = open; end < source.length; end += 1) {
        if (source[end] === '{') depth += 1;
        if (source[end] === '}') {
            depth -= 1;
            if (depth === 0) return source.slice(open, end + 1);
        }
    }
    throw new Error(`${name} is never closed`);
}

const html = fs.readFileSync(path.join(webviewDir, 'viewer.html'), 'utf8');
const viewerJs = fs.readFileSync(path.join(__dirname, '..', 'viewer.js'), 'utf8');

/** Every `__X_JS_URI__` the template asks for, in load order. */
const placeholders = [...html.matchAll(/src="(__[A-Z0-9_]+_URI__)"/g)].map((m) => m[1]);

/** Every placeholder viewer.js fills in, mapped to its path relative to webview/. */
const filled = new Map(
    [...viewerJs.matchAll(/\['(__[A-Z0-9_]+_URI__)',\s*'([^']+)'\]/g)]
        .map(([, placeholder, file]) => [placeholder, path.join(...file.split('/'))]),
);

describe('every script the template asks for is actually wired', () => {
    test.each(placeholders)('%s is filled in by viewer.js', (placeholder) => {
        expect(filled.has(placeholder)).toBe(true);
    });

    test.each(placeholders)('%s resolves to a file that exists', (placeholder) => {
        const file = filled.get(placeholder);

        expect(file).toBeDefined();
        expect(fs.existsSync(path.join(webviewDir, file))).toBe(true);
    });

    test('no placeholder is filled in that the template never asks for', () => {
        // A dead table row is the other half of the same mistake: the module
        // is built and never loaded.
        const asked = new Set(placeholders);
        const dead = [...filled.keys()].filter(
            (name) => !asked.has(name) && html.indexOf(name) === -1);

        expect(dead).toEqual([]);
    });
});

describe('the view is ES modules, and every import is there', () => {
    // The page loads three.js, the scripts the extension host shares (feature flags, selection
    // copy) and the boot diagnostics that must run first as classic scripts; everything else is
    // imported from viewer-app.js. A missing file only shows as a blank view.
    const files = [...fs.readdirSync(webviewDir), ...fs.readdirSync(path.join(webviewDir, 'sidebar')).map((name) => `sidebar/${name}`)]
        .filter((name) => name.endsWith('.js'));
    const imports = files.flatMap((name) => {
        const source = fs.readFileSync(path.join(webviewDir, name), 'utf8');
        return [...source.matchAll(/^import (?:[^;]*? from )?'(\.[^']+)';$/gm)].map((match) => ({ name, target: match[1] }));
    });

    test('there is something to check', () => {
        expect(imports.length).toBeGreaterThan(40);
    });

    test('every relative import names a file', () => {
        const missing = imports.filter(({ name, target }) => !fs.existsSync(path.join(webviewDir, path.dirname(name), target)));
        expect(missing).toEqual([]);
    });

    test('every module is imported by another, or is a page\'s entry', () => {
        // A module nothing imports never runs: layers-panel.js, which defines <kigumi-layers-view>,
        // went missing that way and the tree page was empty.
        const imported = new Set(imports.map(({ name, target }) => path.normalize(path.join(path.dirname(name), target))));
        const entries = new Set(['viewer-app.js', path.join('sidebar', 'sidebar-app.js')]);
        const unloaded = files.filter((name) => /^export /m.test(fs.readFileSync(path.join(webviewDir, name), 'utf8')))
            .map((name) => path.normalize(name))
            .filter((name) => !imported.has(name) && !entries.has(name));
        expect(unloaded).toEqual([]);
    });

    test('the template loads only the classic scripts and the app', () => {
        const loaded = placeholders.map((placeholder) => filled.get(placeholder)).filter(Boolean);
        expect(loaded.filter((name) => !name.startsWith('vendor/'))).toEqual(
            ['boot-diagnostics.js', 'feature-flags.js', 'selection-copy.js', 'viewer-app.js']);
    });

    test('no module reaches for another through window', () => {
        const reach = files.filter((name) => /^(import|export) /m.test(fs.readFileSync(path.join(webviewDir, name), 'utf8')))
            .flatMap((name) => [...fs.readFileSync(path.join(webviewDir, name), 'utf8').matchAll(/(?:window|globalThis)\.(Kigumi\w+|[A-Z]\w+Store|CsgTreeView|TagIndex)\b/g)]
                .map((match) => `${name}: ${match[1]}`))
            .filter((entry) => !/KigumiSelectionCopy|KigumiBootDiagnostics/.test(entry));
        expect(reach).toEqual([]);
    });
});

describe('every argument a shared decision takes is actually passed', () => {
    // choosePickAction gained `inDrawing`, was unit tested, and neither caller
    // was updated -- so in a drawing the store refused the timber selection,
    // the pick never became a 'csg', and nothing selected or hovered at all.
    // A pure function is easy to test and easy to leave unwired.
    const app = viewerSource();

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

describe('everything the frame is drawn from is in the signature it is drawn for', () => {
    // What a member looks like is PULLED: the frame loop folds the state into a
    // signature and redraws when it differs, so nothing has to remember to
    // announce a change. That removes the "eleven callers can forget" problem
    // and leaves exactly one way to get it wrong -- reading an input in
    // _memberAppearance that visualSignature does not fold, which would let the
    // frame stop following the state with nothing to say so.
    //
    // This is that check. It is the reason the pulled design is safe to rely
    // on, so it is not decoration.
    const app = viewerSource();


    /**
     * Reads that are not state of their own, with why each is safe.
     *
     * Every entry here is a claim. If one stops being true, what is drawn can
     * drift and this test will not say so.
     */
    const NOT_STATE = {
        // The members being walked. The signature walks the same list, so a
        // member appearing or leaving changes it by construction.
        sceneManager: true,
        // Folded as the selected keys and the focus.
        selectionManager: true,
        // Reads RENDER_PROFILES, which is frozen at module load. The per-member
        // half is bundle.profileId, which the signature does fold.
        resolveRenderProfile: true,
        // The function whose reads are being collected here.
        _memberAppearance: true,
        // Reads the selected timbers and the focus. Both folded.
        _getSelectionVisualContext: true,
        // Pure, from a state and a base opacity: the state comes from the
        // context above and the opacity from a slider the signature folds.
        _getSelectionVisualPolicy: true,
        // Each member's state, which the signature folds whole, per member.
        _memberState: true,
    };

    const signature = methodBody(app, 'visualSignature');
    const reads = new Set();
    for (const method of ['_memberAppearance', 'applySelectionOpacity']) {
        for (const match of methodBody(app, method).matchAll(/this\.([A-Za-z_][A-Za-z0-9_]*)/g)) {
            reads.add(match[1]);
        }
    }

    test('there is something to check', () => {
        // If the shape changes so nothing is found, everything below passes by
        // being about nothing.
        expect(reads.size).toBeGreaterThan(4);
        expect(reads.has('edgeMode')).toBe(true);
        expect(signature.length).toBeGreaterThan(200);
    });

    test.each([...reads].filter((name) => !NOT_STATE[name]))(
        'the signature folds %s', (name) => {
            expect(signature).toContain(name);
        },
    );
});
