const fs = require('fs');
const path = require('path');

// The viewer's keydown handler decides things in an order that matters, and
// the order is invisible: every branch reads correctly on its own.
//
// Ctrl-Z did nothing for the whole life of this branch because VS Code
// forwards key events from a webview to its own keybindings and marks ctrl-Z
// handled on the way through. The handler's `if (event.defaultPrevented)`
// guard then turned it away every time -- with a stack sitting there holding
// two undoable changes. Tab had already been moved above that guard for the
// same reason, and the reason was written down, and the accelerators were
// still below it.
//
// viewer-app.js has no runtime harness, so this reads the source.

const app = fs.readFileSync(
    path.join(__dirname, '..', 'webview', 'viewer-app.js'), 'utf8');

/** The body of a one-argument method, by brace matching. */
function methodBody(name) {
    const at = app.indexOf(`\n    ${name}(event) {`);
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

describe('what the keydown handler decides, and in what order', () => {
    const body = methodBody('onWindowKeyDown');
    const at = (needle) => body.indexOf(needle);

    const guard = at('if (event.defaultPrevented)');
    const undo = at("event.key === 'z'");
    const redo = at("event.key === 'y'");
    const typing = at('_isTypingTarget(event.target)');
    const tab = at("event.key === 'Tab'");
    const del = at("event.key === 'Delete'");

    test('all of the branches this is about are still there', () => {
        // Otherwise a rename turns every ordering test below green by making
        // both sides -1.
        for (const [name, found] of Object.entries(
            { guard, undo, redo, typing, tab, del })) {
            expect([name, found > -1]).toEqual([name, true]);
        }
    });

    test('undo is decided before the defaultPrevented guard', () => {
        // The host claims ctrl-Z. Below the guard, undo never runs at all.
        expect(undo).toBeLessThan(guard);
    });

    test('and so is redo', () => {
        expect(redo).toBeLessThan(guard);
    });

    test('as Tab already was, for the same reason', () => {
        expect(tab).toBeLessThan(guard);
    });

    test('but the caret still wins over the accelerators', () => {
        // Undo in a text field undoes typing. Moving the accelerators up must
        // not reach past the typing guard to take it.
        expect(typing).toBeLessThan(undo);
    });

    test('and ordinary keys still respect the guard', () => {
        // Only the keys the host claims jump it; Delete is not one of them,
        // and something else may legitimately have handled it.
        expect(del).toBeGreaterThan(guard);
    });
});
