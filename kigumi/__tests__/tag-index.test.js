const { buildTagIndex, tagSelectionState } = require('../webview/tag-index.js');

const HIERARCHY = {
    timbers: [
        { key: 'A', tags: [{ kind: 'member', name: 'post' }, { kind: 'slice', name: 'bent1' }] },
        { key: 'B', tags: [{ kind: 'slice', name: 'bent1' }, { kind: 'generic', name: 'wonky' }] },
        { key: 'C', tags: [] },
    ],
};

describe('buildTagIndex', () => {
    test('a tag collects every member wearing it', () => {
        const bent1 = buildTagIndex(HIERARCHY).find((entry) => entry.name === 'bent1');
        expect(bent1.memberKeys).toEqual(['A', 'B']);
    });

    test('kinds sort structure-first, then names alphabetically', () => {
        expect(buildTagIndex(HIERARCHY).map((entry) => entry.id)).toEqual([
            'member:post',
            'slice:bent1',
            'generic:wonky',
        ]);
    });

    test('the same name in two kinds stays two tags', () => {
        const index = buildTagIndex({
            timbers: [{ key: 'A', tags: [{ kind: 'slice', name: 'gable' }, { kind: 'generic', name: 'gable' }] }],
        });
        expect(index.map((entry) => entry.id)).toEqual(['slice:gable', 'generic:gable']);
    });

    test('a member is listed once however many times it repeats a tag', () => {
        const index = buildTagIndex({
            timbers: [{ key: 'A', tags: [{ kind: 'slice', name: 'gable' }, { kind: 'slice', name: 'gable' }] }],
        });
        expect(index[0].memberKeys).toEqual(['A']);
    });

    test('a hierarchy with nothing in it is an empty index, not a throw', () => {
        expect(buildTagIndex(undefined)).toEqual([]);
        expect(buildTagIndex({ timbers: [] })).toEqual([]);
    });
});

describe('tagSelectionState', () => {
    const bent1 = { id: 'slice:bent1', kind: 'slice', name: 'bent1', memberKeys: ['A', 'B'] };

    test('none of its members selected reads as none', () => {
        expect(tagSelectionState(bent1, new Set(['C']))).toBe('none');
    });

    test('some of its members selected reads as partial', () => {
        expect(tagSelectionState(bent1, new Set(['A', 'C']))).toBe('partial');
    });

    test('all of its members selected reads as all', () => {
        expect(tagSelectionState(bent1, new Set(['A', 'B', 'C']))).toBe('all');
    });

    test('a tag no member wears is never selected', () => {
        expect(tagSelectionState({ memberKeys: [] }, new Set(['A']))).toBe('none');
    });
});
