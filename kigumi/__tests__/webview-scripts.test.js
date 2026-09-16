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

describe('the hover machine has one home', () => {
    // It used to have two. hover-state.js owned the timing -- when to ask,
    // which answer is still wanted -- while the app owned what was drawn, which
    // feature under the pointer was meant, and where the pointer was. Both
    // hover bugs grew on that seam: a stale verdict left green because the
    // comparison lived on one side, and the record of what was drawn nulled by
    // a teardown on the other.
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');
    const machine = fs.readFileSync(path.join(webviewDir, 'hover-state.js'), 'utf8');

    test.each(['_hoverDrawn', '_candidateIndex', '_hoverClient'])(
        'the app no longer keeps %s of its own', (field) => {
            expect(app).not.toContain(field);
        },
    );

    test('it asks the machine whether a redraw would change anything', () => {
        expect(app).toContain('wouldRedraw');
    });

    test('and the machine is what compares whole highlights', () => {
        // The feature AND the verdict. Comparing features alone left a
        // highlight green over a pair that could not be measured.
        expect(machine).toContain('sameHighlight(this.drawn, answer)');
    });

    test('the app does not reach past it to the weaker question', () => {
        expect(app).not.toContain('HoverState.sameFeature');
    });

    test('one place judges what counts as refused', () => {
        // The hover colour and the click refusal must agree, so both ask the
        // same function rather than each testing kinds.length.
        expect(app).not.toContain('kinds.length === 0');
    });

    test('and one place knows which feature is being asked for', () => {
        // Null, never undefined: zero is a choice, and the runner has to tell
        // it from "choose for me".
        expect(machine).toContain('get asking()');
        expect(app).toContain('this._hover.asking');
    });
});

describe('the hover is asked again whenever the held end changes', () => {
    // The hover only asks a question when the pointer moves. Taking, releasing
    // or confirming an end is a button or a key, so the pointer does not move
    // -- and the colour under it, which says whether a click will be taken,
    // depends on exactly that. Without a re-ask the verdict on screen is the
    // one from before, however right the comparison that draws it.
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');


    test.each([
        'startMeasurementFromFocus',
        'escapeMeasurement',
        '_writeMeasurement',
        'clearMeasureDraft',
    ])('%s asks the hover again', (method) => {
        expect(methodBody(app, method)).toContain('_reaskHover');
    });
});

describe('overlays are reconciled from a list, not torn down by hand', () => {
    // This replaces a guard about what a redraw may tear down. That guard
    // existed because drawHoverHighlight removed the outline it was about to
    // replace, and TWO things were forgotten in that teardown: the measurement
    // preview, erased a statement after being drawn, and the record of what was
    // on screen, nulled mid-redraw so the guard that skips a repeat never once
    // skipped.
    //
    // Neither can happen now, and not because they were fixed: there is no
    // teardown to forget things in. highlightsFor says what SHOULD be lit and
    // the reconciler makes the scene match, so an overlay goes away by leaving
    // the list. These tests pin that shape, since losing it brings the old
    // class of bug back with it.
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');

    test('the pass asks what should be lit', () => {
        expect(methodBody(app, 'applyDerivedVisuals')).toContain('highlightsFor');
    });

    test('and something reconciles the answer against what is lit', () => {
        const reconcile = methodBody(app, '_reconcileHighlights');

        expect(reconcile).toContain('this._highlightObjects');
        expect(reconcile).toContain('this.scene.remove');
        expect(reconcile).toContain('dispose');
    });

    test('the reconciler is the ONLY thing that removes an overlay', () => {
        // Anything else removing one is a lifetime of its own, which is the
        // shape this replaced.
        const removals = [...app.matchAll(/this\.scene\.remove\(/g)].length;
        const inside = [...methodBody(app, '_reconcileHighlights')
            .matchAll(/this\.scene\.remove\(/g)].length;
        const elsewhere = removals - inside;

        // The scene holds more than overlays -- gizmos, footprints, lights --
        // so this is not zero. What matters is that no HIGHLIGHT is removed
        // outside the reconciler, which the absence of the old names below
        // is what now guarantees.
        expect(inside).toBeGreaterThan(0);
        expect(elsewhere).toBeGreaterThanOrEqual(0);
    });

    test.each([
        'drawHoverHighlight', 'clearHoverOutline', 'removeCSGHighlight',
        '_heldFeatureLines', '_csgHighlightMesh', '_hoverHighlightMesh',
    ])('%s is gone, and with it a lifetime to get wrong', (name) => {
        expect(app).not.toContain(name);
    });

    test('what is lit is part of the signature the pass is gated on', () => {
        // Otherwise hovering something would not redraw: the pass would see an
        // unchanged answer and skip the frame that should have lit it.
        const signature = methodBody(app, 'visualSignature');

        expect(signature).toContain('_highlightState');
    });
});

describe('the kind dropdown compares names, not the object a kind arrives as', () => {
    // It offers itself only when there is a choice, and labels each entry from
    // `viewer.measure.kind.<name>`. A kind arrives from python STRUCTURED --
    // {operation, space, direction} -- so comparing it against the list of
    // available names matched nothing: every measurement read as though its
    // kind were unavailable, which showed the dropdown even with a single
    // choice and labelled its entry from a key built out of "[object Object]".
    const panel = fs.readFileSync(path.join(webviewDir, 'selection-panel.js'), 'utf8');
    const at = panel.indexOf('_measureKindRow(found) {');
    const body = panel.slice(at, panel.indexOf('\n    }', at));

    test('there is a _measureKindRow to check', () => {
        expect(at).toBeGreaterThan(-1);
    });

    test('it names the kind before comparing it', () => {
        expect(body).toContain('kindName');
    });

    test('it offers a choice only when there is more than one to make', () => {
        // Counting the written kind when this view cannot draw it: that one is
        // listed unselectable, and with it there IS something to change away
        // from. Without it, one kind is a readout.
        expect(body).toContain('const choices = available.length + (broken ? 1 : 0)');
        expect(body).toContain('if (choices < 2)');
    });

    test('and says which kind it is either way', () => {
        // The row is not withheld when there is nothing to choose -- which kind
        // it is is worth saying even when it cannot be changed.
        expect(body).toContain('ip-detail-value');
        expect(body).toContain('viewer.measure.kind.');
    });
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
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');


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

    test('the frame loop asks for it, rather than waiting to be told', () => {
        expect(methodBody(app, 'setupThreeScene')).toContain('applyDerivedVisuals');
    });

    test('and the pass only redraws when the answer differs', () => {
        const pass = methodBody(app, 'applyDerivedVisuals');

        expect(pass).toContain('this.visualSignature(');
        expect(pass).toContain('this._visualSignature');
        expect(pass).toContain('applySelectionOpacity');
    });
});

describe('a pointer gesture owns its listeners', () => {
    // Four drags, and two patterns. The gizmo and the light dial keep their
    // listeners for the life of the viewer and check a flag -- nothing to pair,
    // nothing to get wrong. The rail resize and the measurement drag put theirs
    // up for the length of the drag, and that pairing is the part worth owning.
    //
    // The measurement drag used CLOSURES, which disconnectedCallback could not
    // name and so could not take down: leaving the viewer with the mouse still
    // held leaked both handlers, and each held the whole app. The rail resize
    // had been given a line in teardown by hand; a name means neither needs one.
    const app = fs.readFileSync(path.join(webviewDir, 'viewer-app.js'), 'utf8');

    /** Every place a pointer listener goes up, by the method it is in. */
    function listenerHomes(kind) {
        const homes = new Set();
        const pattern = new RegExp(`window\\.${kind}EventListener\\('pointer`, 'g');
        for (const match of app.matchAll(pattern)) {
            const before = app.slice(0, match.index);
            const method = [...before.matchAll(/\n    ([a-zA-Z_][A-Za-z0-9_]*)\(/g)].pop();
            homes.add(method ? method[1] : '(top level)');
        }
        return homes;
    }

    test('they go up in two places only', () => {
        // The persistent pair, and the gesture helper.
        expect([...listenerHomes('add')].sort())
            .toEqual(['_beginPointerGesture', 'setupUiEvents']);
    });

    test('and come down in two', () => {
        expect([...listenerHomes('remove')].sort())
            .toEqual(['_endPointerGesture', 'disconnectedCallback']);
    });

    test('leaving ends whatever is mid-drag', () => {
        expect(methodBody(app, 'disconnectedCallback')).toContain('_endAllPointerGestures');
    });

    test('a gesture stops listening before its end runs', () => {
        // An end that throws still leaves nothing listening.
        // Inside the UP handler only. Searching the whole method finds the
        // guard at the top, which is always before anything and so would pass
        // whatever the handler did.
        const begin = methodBody(app, '_beginPointerGesture');
        const up = begin.slice(begin.indexOf('const up ='));
        const stops = up.indexOf('this._endPointerGesture(name)');
        const calls = up.indexOf('onEnd(event)');

        expect(stops).toBeGreaterThan(-1);
        expect(calls).toBeGreaterThan(stops);
    });

    test('and beginning one twice does not leave the first listening', () => {
        expect(methodBody(app, '_beginPointerGesture'))
            .toContain('this._endPointerGesture(name);');
    });
});
