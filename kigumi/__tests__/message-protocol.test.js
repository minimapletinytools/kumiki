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

describe('a command rebuilt field by field', () => {
    test('the measurement commands carry what a measurement is made of', () => {
        const forwarded = session.slice(session.indexOf('addMeasurement:'));

        for (const field of ['drawingId', 'viewportId', 'a', 'b', 'kind', 'plane']) {
            expect(forwarded).toContain(`${field}: message.${field}`);
        }
    });
});
