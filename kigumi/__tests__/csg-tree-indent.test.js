const { csgIndentPx, MEMBER_ROW_INDENT_PX } = require('../webview/layers-panel.js');

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
