const fs = require('fs');
const path = require('path');
const { csgIndentPx, MEMBER_ROW_INDENT_PX } = require('../webview/layers-panel.js');

// The left rail has no visual test harness, so these guard the one failure it
// has actually hit: the two panes share appearance rules, and a shared rule
// that also carries SIZING silently hands whichever selector comes later in
// the file control of the other pane's height.
describe('left rail layout', () => {
    const css = fs.readFileSync(path.join(__dirname, '..', 'webview', 'viewer.css'), 'utf8');

    /** Every rule whose selector mentions `selector`, with its declarations. */
    function rulesFor(selector) {
        return [...css.matchAll(/([^\n{}]*)\{([^}]*)\}/g)]
            .map((m) => ({ sel: m[1].trim().replace(/\s+/g, ' '), body: m[2] }))
            .filter((r) => r.sel.includes(selector));
    }

    function heightDeclarations(selector) {
        return rulesFor(selector)
            .map((r) => ({ sel: r.sel, height: (r.body.match(/(^|\s)height:\s*([^;]*)/) || [])[2] }))
            .filter((r) => r.height)
            .map((r) => ({ sel: r.sel, height: r.height.trim() }));
    }

    test('the info pane sizes to its content, never to the full rail', () => {
        // Regression: it briefly shared `height: 100%` with the timber list,
        // so an empty selection filled the rail and hid the list entirely.
        // Sizing is therefore kept out of the rule the two panes share.
        const heights = heightDeclarations('.ip-panel');
        expect(heights.length).toBeGreaterThan(0);
        for (const rule of heights) {
            expect(rule.height).not.toBe('100%');
        }
    });

    test('the timber list still fills its share of the rail', () => {
        const heights = heightDeclarations('.lp-panel');
        expect(heights.some((r) => r.sel === '.lp-panel' && r.height === '100%')).toBe(true);
    });

    test('no rule sets a height for both panes at once', () => {
        const shared = heightDeclarations('.ip-panel')
            .filter((r) => r.sel.includes('.lp-panel'));
        expect(shared).toEqual([]);
    });

    test('the rail is a column so one pane pushes the other', () => {
        const rail = rulesFor('#left-rail').find((r) => r.sel === '#left-rail');
        expect(rail).toBeDefined();
        expect(rail.body).toMatch(/flex-direction:\s*column/);
    });

    test('the rail starts at the top of the viewport', () => {
        // Regression: it reserved 64px for the old floating #info box, which
        // now lives inside the rail -- leaving a gap above the info pane.
        const rail = rulesFor('#left-rail').find((r) => r.sel === '#left-rail');
        const top = (rail.body.match(/top:\s*([0-9]+)px/) || [])[1];
        expect(Number(top)).toBeLessThanOrEqual(16);
    });

    test('rail width is a variable, so resizing moves both panes together', () => {
        const rail = rulesFor('#left-rail').find((r) => r.sel === '#left-rail');
        expect(rail.body).toMatch(/width:\s*var\(--kigumi-rail-width/);
        expect(rulesFor('#rail-resize').length).toBeGreaterThan(0);
    });

    test('the info pane wraps rather than truncating what it shows', () => {
        for (const sel of ['.ip-breadcrumb', '.ip-detail-value']) {
            const rule = rulesFor(sel).find((r) => r.sel === sel);
            expect(rule).toBeDefined();
            expect(rule.body).not.toMatch(/white-space:\s*nowrap/);
            expect(rule.body).not.toMatch(/text-overflow:\s*ellipsis/);
        }
    });

    test('the tree scrolls sideways instead of truncating deep rows', () => {
        const tree = rulesFor('.lp-tree').find((r) => r.sel === '.lp-tree');
        expect(tree.body).toMatch(/overflow:\s*auto/);
        // Rows must size to content, or there is never anything to scroll.
        const csg = rulesFor('.lp-row-csg').find((r) => r.sel === '.lp-row-csg');
        expect(csg.body).toMatch(/width:\s*max-content/);
    });

    test('csg rows are coloured apart from member rows', () => {
        const csg = rulesFor('.lp-row-csg').find((r) => r.sel === '.lp-row-csg');
        const colour = (csg.body.match(/(?:^|\s)color:\s*([^;]+)/) || [])[1];
        expect(colour).toBeDefined();
        // .lp-row inherits the panel's --hv-text; csg rows must not.
        expect(colour).not.toMatch(/--hv-text/);
    });

    test('the timber list can shrink rather than overflow the rail', () => {
        const view = rulesFor('kigumi-layers-view').find((r) => r.sel === 'kigumi-layers-view');
        expect(view).toBeDefined();
        expect(view.body).toMatch(/min-height:\s*0/);
        expect(view.body).toMatch(/flex:\s*1 1 auto/);
    });
});

describe('csg tree indentation', () => {
    // Regression: the old step started a tree shallower than the timber row it
    // hung under, so the CSG read as a sibling of its own timber.
    test('a tree under a timber starts deeper than the timber row', () => {
        expect(csgIndentPx(1)).toBeGreaterThan(MEMBER_ROW_INDENT_PX[0]);
    });

    test('a tree under a joint cutting starts deeper than the cutting row', () => {
        expect(csgIndentPx(2)).toBeGreaterThan(MEMBER_ROW_INDENT_PX[1]);
    });

    test('each level indents further than the last', () => {
        for (let depth = 1; depth < 6; depth += 1) {
            expect(csgIndentPx(depth + 1)).toBeGreaterThan(csgIndentPx(depth));
        }
    });

    test('the step is big enough to read as a level', () => {
        expect(csgIndentPx(2) - csgIndentPx(1)).toBeGreaterThanOrEqual(12);
    });
});
