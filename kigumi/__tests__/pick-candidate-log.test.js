// describeCandidates is a pure function at the top of viewer-app.js, which is a
// browser module -- so this pulls just that function out of the source rather
// than loading the whole app.
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '../webview/viewer-app.js'), 'utf8');
const start = source.indexOf('function describeCandidates(');
const end = source.indexOf('\n}\n', start) + 3;
// eslint-disable-next-line no-eval
const describeCandidates = eval('(' + source.slice(start, end) + ')');

const AXIS = { label: 'peg_hole_axis', type: 'EDGE', real: false, derived: false, group: 'NONE', priority: 0 };
const WALL = { label: 'side.0', type: 'FACE', real: true, derived: false, group: 'NONE', priority: 1000 };
const SHOULDER_EDGE = { label: 'shoulder×rough.right', type: 'EDGE', real: true, derived: true, group: 'A', priority: 0 };

describe('candidate logging', () => {
    test('nothing under the pointer logs an empty list, not a missing field', () => {
        expect(describeCandidates({}).candidates).toEqual([]);
        expect(describeCandidates({ candidates: [] }).candidates).toEqual([]);
    });

    test('the chosen candidate is marked and the rest are not', () => {
        const lines = describeCandidates({ candidates: [WALL, AXIS], candidateIndex: 1 }).candidates;
        expect(lines[0].startsWith(' ')).toBe(true);
        expect(lines[1].startsWith('>')).toBe(true);
    });

    test('each line carries what the ordering sorted on', () => {
        // Why that one, and why not mine: neither is answerable from the label.
        const [line] = describeCandidates({ candidates: [SHOULDER_EDGE], candidateIndex: 0 }).candidates;
        expect(line).toContain('EDGE');
        expect(line).toContain('derived');
        expect(line).toContain('real');
        expect(line).toContain('A');
        expect(line).toContain('p0');
        expect(line).toContain('shoulder×rough.right');
    });

    test('a non-real feature says so', () => {
        const [line] = describeCandidates({ candidates: [AXIS], candidateIndex: 0 }).candidates;
        expect(line).toContain('non-real');
        expect(line).toContain('peg_hole_axis');
    });
});
