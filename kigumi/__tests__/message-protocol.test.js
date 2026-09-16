const fs = require('fs');
const path = require('path');
const { TO_EXTENSION, TO_EXTENSION_REPLIES } = require('../message-types');

// The two sides of the protocol, reconciled against one declaration.
//
// They were related by nothing: string literals in the webview, string literals
// in the extension, and no way to ask whether they agreed. Two handlers existed
// for messages nobody sent, and one message was sent that nobody handled -- the
// measurement refusals, posted as `log` while the extension only knows
// `viewerLog`, so every reason a pick was refused went nowhere.
//
// This is what makes a dead branch visible and a new message impossible to
// forget. It does not need either side to import the declaration: a typo fails
// as an undeclared type, which is the same catch by a shorter road.

const root = path.join(__dirname, '..');
const session = fs.readFileSync(path.join(root, 'frame-view-session.js'), 'utf8');

/** Every type the extension's chain handles. */
// Either comparison: a listener that returns unless the type is its own is
// handling that type, just written from the other side.
const handled = new Set(
    [...session.matchAll(/message\.type (?:===|!==)\s*'([a-zA-Z]+)'/g)].map((m) => m[1]),
);

/** Every type the webview posts, as far as a read can tell. */
function postedTypes() {
    const dir = path.join(root, 'webview');
    const found = new Set();
    for (const name of fs.readdirSync(dir).filter((file) => file.endsWith('.js'))) {
        const source = fs.readFileSync(path.join(dir, name), 'utf8');
        for (const match of source.matchAll(/postMessage\(\s*\{[^}]*?type:\s*'([a-zA-Z]+)'/g)) {
            found.add(match[1]);
        }
    }
    return found;
}

const posted = postedTypes();
const declared = new Set([...TO_EXTENSION, ...TO_EXTENSION_REPLIES]);

describe('the declaration and the two sides agree', () => {
    test('there is a protocol to check', () => {
        expect(TO_EXTENSION.length).toBeGreaterThan(10);
        expect(handled.size).toBeGreaterThan(10);
        expect(posted.size).toBeGreaterThan(10);
    });

    test.each([...handled])('%s, which the extension handles, is declared', (type) => {
        // A handler for a message nobody sends is a dead branch that reads as
        // live. Two of them were.
        expect(declared.has(type)).toBe(true);
    });

    test.each([...posted])('%s, which the webview posts, is declared', (type) => {
        // A message nobody handles goes nowhere, and looks from the sending
        // side exactly like one that worked.
        expect(declared.has(type)).toBe(true);
    });

    test('every declared message reaches the chain', () => {
        // Except the round-trip replies, which are matched against the request
        // that asked for them and never reach it.
        const missing = TO_EXTENSION.filter((type) => !handled.has(type));

        expect(missing).toEqual([]);
    });

    test('and the replies deliberately do not', () => {
        for (const type of TO_EXTENSION_REPLIES) {
            expect(handled.has(type)).toBe(false);
        }
    });

    test('nothing is declared twice', () => {
        const all = [...TO_EXTENSION, ...TO_EXTENSION_REPLIES];

        expect(new Set(all).size).toBe(all.length);
    });
});

describe('a request survives being rebuilt field by field', () => {
    // The extension does not forward a message: it builds a new payload naming
    // each field. Anything added to the message and not added there is dropped
    // in silence, and the runner answers a question nobody asked. That has
    // happened four times -- tolerances, heldGeometry, look, and space.
    //
    // pick-payload-wiring checks the pick's own fields. This checks the SHAPE:
    // every rebuild forwards, and the two that must ask the same question do.

    /** The body of a handler in frame-view-session. */
    function handlerBody(name) {
        const at = session.search(new RegExp(`\\n    (?:async )?${name}\\(`));
        if (at === -1) {
            throw new Error(`${name} is not a handler`);
        }
        const open = session.indexOf('{', session.indexOf('(', at));
        let depth = 0;
        for (let end = open; end < session.length; end += 1) {
            if (session[end] === '{') depth += 1;
            if (session[end] === '}') {
                depth -= 1;
                if (depth === 0) return session.slice(open, end + 1);
            }
        }
        throw new Error(`${name} is never closed`);
    }

    /**
     * The fields a handler forwards TO THE RUNNER.
     *
     * The runner payload only, not the whole handler: the hover echoes its
     * request number back on the reply so the viewer can tell a stale answer
     * from a current one, and that is routing rather than part of the question.
     */
    function askedOf(name) {
        const body = handlerBody(name);
        // Built as a variable in one handler and inline at the call in the
        // other. Same payload either way.
        const declared = body.indexOf('const payload = {');
        const open = declared !== -1
            ? body.indexOf('{', declared)
            : body.indexOf('{', body.indexOf('slotRequest('));
        let depth = 0;
        let payload = '';
        for (let end = open; end < body.length; end += 1) {
            if (body[end] === '{') depth += 1;
            if (body[end] === '}') {
                depth -= 1;
                if (depth === 0) {
                    payload = body.slice(open, end + 1);
                    break;
                }
            }
        }
        return new Set(
            [...payload.matchAll(/([a-zA-Z][A-Za-z0-9_]*):\s*message\.\1/g)].map((m) => m[1]));
    }

    test('the hover and the pick ask the runner the same thing', () => {
        // Hover exists to say what a click would do. Asking a different
        // question is how a hover lights what a click then refuses.
        const hover = askedOf('_handleHoverFeatureAtPoint');
        const click = askedOf('_handleFindCSGAtPoint');

        expect([...hover].sort()).toEqual([...click].sort());
    });

    test('and they forward more than a couple of fields', () => {
        // If the extraction stops finding them, the test above passes by
        // comparing two empty sets.
        expect(askedOf('_handleFindCSGAtPoint').size).toBeGreaterThan(5);
    });

    test('the measurement commands carry what a measurement is made of', () => {
        const body = handlerBody('_handleDrawingsCommand');
        const forwarded = session.slice(session.indexOf('addMeasurement:'));

        for (const field of ['drawingId', 'viewportId', 'a', 'b', 'kind', 'plane']) {
            expect(forwarded).toContain(`${field}: message.${field}`);
        }
        expect(body.length).toBeGreaterThan(0);
    });
});
