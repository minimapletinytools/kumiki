const fs = require('fs');
const path = require('path');

// The webview builds a pick request; the extension host rebuilds it FIELD BY
// FIELD before handing it to the runner. Anything added to the request and not
// added there is silently dropped, and the runner answers a question nobody
// asked -- there is no error, just a wrong answer.
//
// That has happened four times on this feature: tolerances arrived empty and
// edges stopped being selectable; heldGeometry and look went missing twice; and
// `space` went missing, so the runner kept projecting in the 3D view and every
// face came back unmeasurable and drew red.

const app = fs.readFileSync(
    path.join(__dirname, '..', 'webview', 'viewer-app.js'), 'utf8');
const session = fs.readFileSync(
    path.join(__dirname, '..', 'frame-view-session.js'), 'utf8');

/** The keys _heldForRequest puts on a pick request. */
function heldFields() {
    const at = app.indexOf('_heldForRequest() {');
    const body = app.slice(at, app.indexOf('\n    }', at));
    const returned = body.slice(body.lastIndexOf('return {'));
    return [...returned.matchAll(/^\s{12}([A-Za-z][A-Za-z0-9_]*):/gm)].map((m) => m[1]);
}

const fields = heldFields();

describe('everything the pick request carries survives the trip to the runner', () => {
    test('there is something to check', () => {
        // If the shape of _heldForRequest changes so nothing is found, every
        // test below would pass by matching nothing.
        expect(fields.length).toBeGreaterThan(4);
        expect(fields).toContain('heldReference');
    });

    test.each(fields)('frame-view-session forwards %s', (field) => {
        expect(session).toContain(`${field}: message.${field}`);
    });

    test('and forwards each of them to BOTH the click and the hover', () => {
        // Hover and click must ask the same question, or hover lights what a
        // click refuses.
        const missing = fields.filter((field) => {
            const forwarded = session.split(`${field}: message.${field}`).length - 1;
            return forwarded < 2;
        });

        expect(missing).toEqual([]);
    });
});

// Forwarding a field is not the same as forwarding its VALUE. `|| 0` and
// `|| null` look like defaults and are conversions: they rewrite the one value
// the runner reads as meaning something else.
describe('and means the same thing on arrival', () => {
    const forwarded = [...session.matchAll(
        /^\s*candidateIndex: ([^,\n]+),/gm)].map((m) => m[1].trim());

    test('candidateIndex is forwarded to both the click and the hover', () => {
        expect(forwarded).toHaveLength(2);
    });

    test.each([0, 1])('neither of them turns null into zero (%i)', (which) => {
        // The runner's contract, stated in its own comments: None is "choose
        // for me" and ZERO IS A CHOICE -- stepping round to the first feature,
        // or picking the first row of the menu. `|| 0` says the second when the
        // viewer said the first, which left _best_matching_candidate dead code
        // for every request the viewer makes.
        expect(forwarded[which]).not.toMatch(/\|\|/);
    });
});
