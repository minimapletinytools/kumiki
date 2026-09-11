const values = require('../webview/kiwari-values');

const PAYLOAD = {
    schema: [
        { key: 'posts', kind: 'count', about: 'How many', default: { value: 2 }, minimum: 1, maximum: 8 },
        { key: 'height', kind: 'length', default: { value: 2.4, text: '2400mm' } },
        { key: 'splay', kind: 'angle', default: { value: 0, text: '0deg' } },
        { key: 'waste', kind: 'number', default: { value: 0.1 } },
        { key: 'capped', kind: 'flag', default: { value: false } },
        { key: 'label', kind: 'text', default: { value: 'shed' } },
        {
            key: 'end', kind: 'choice', default: { value: 'TOP' },
            choices: [{ value: 'TOP', label: 'Top' }, { value: 'BOTTOM', label: 'Bottom' }],
        },
        { key: 'origin', kind: 'point3', default: { value: { x: 0, y: 0, z: 0 } } },
    ],
    applied: {
        posts: { value: 2 },
        height: { value: 2.4, text: '2400mm' },
        splay: { value: 0, text: '0deg' },
        waste: { value: 0.1 },
        capped: { value: false },
        label: { value: 'shed' },
        end: { value: 'TOP' },
        origin: { value: { x: 0, y: 0, z: 0 } },
    },
    changed: [],
    canSave: true,
};

const state = () => values.fromPayload(PAYLOAD);

describe('taking the runner’s kiwari apart', () => {
    test('a draft starts as the text the value was typed with', () => {
        expect(state().drafts.height).toBe('2400mm');
        expect(state().drafts.posts).toBe('2');
        expect(state().drafts.capped).toBe(false);
        expect(state().drafts.origin).toEqual({ x: '0mm', y: '0mm', z: '0mm' });
    });

    test('an empty payload is a panel with nothing in it', () => {
        const empty = values.fromPayload(null);
        expect(empty.schema).toEqual([]);
        expect(empty.canSave).toBe(false);
    });

    test('entries with no key are dropped rather than drawn', () => {
        expect(values.fromPayload({ schema: [{ kind: 'count' }, { key: '', kind: 'count' }] }).schema)
            .toEqual([]);
    });
});

describe('telling someone a box is wrong', () => {
    test('says nothing while every box reads', () => {
        expect(values.problems(state(), 'metric')).toEqual({});
    });

    test('a measurement that is not one is named with its reason', () => {
        const edited = values.withDraft(state(), 'height', 'yea high');
        expect(values.problems(edited, 'metric').height).toMatch(/not a measurement/);
    });

    test('a count has to be whole', () => {
        const edited = values.withDraft(state(), 'posts', '2.5');
        expect(values.problems(edited, 'metric').posts).toMatch(/whole number/);
    });

    test('bounds are reported in the unit being typed in', () => {
        expect(values.problems(values.withDraft(state(), 'posts', '0'), 'metric').posts)
            .toMatch(/at least 1/);
        expect(values.problems(values.withDraft(state(), 'posts', '99'), 'metric').posts)
            .toMatch(/at most 8/);
    });

    test('an empty box is a problem unless the parameter is optional', () => {
        expect(values.problems(values.withDraft(state(), 'height', ''), 'metric').height)
            .toMatch(/needs a value/);
        const optional = values.fromPayload({
            schema: [{ key: 'trim', kind: 'length', optional: true, default: { value: null } }],
            applied: { trim: { value: null } },
        });
        expect(values.problems(optional, 'metric')).toEqual({});
    });

    test('one bad axis makes the whole point bad, and says which', () => {
        const edited = values.withAxisDraft(state(), 'origin', 'y', 'sideways');
        expect(values.problems(edited, 'metric').origin).toMatch(/^y: /);
    });

    test('a flag, a text and a choice cannot be wrong', () => {
        let edited = values.withDraft(state(), 'label', 'anything at all');
        edited = values.withDraft(edited, 'capped', true);
        expect(values.problems(edited, 'metric')).toEqual({});
    });
});

describe('what goes on the wire', () => {
    test('a measurement carries both the number and how it was typed', () => {
        const edited = values.withDraft(state(), 'height', '10ft');
        expect(values.toWire(edited, 'metric').height).toEqual({ value: 3.048, text: '10ft' });
    });

    test('a bare number takes the unit the viewer is set to', () => {
        expect(values.toWire(values.withDraft(state(), 'height', '18'), 'imperial').height.value)
            .toBeCloseTo(0.4572, 9);
        expect(values.toWire(values.withDraft(state(), 'height', '18'), 'metric').height.value)
            .toBeCloseTo(0.018, 9);
    });

    test('a count is sent whole', () => {
        expect(values.toWire(values.withDraft(state(), 'posts', '5'), 'metric').posts).toEqual({ value: 5 });
    });

    test('a point is sent as its axes', () => {
        const edited = values.withAxisDraft(state(), 'origin', 'x', '100mm');
        expect(values.toWire(edited, 'metric').origin.value.x).toBeCloseTo(0.1, 9);
    });

    test('nothing is sent while a box does not read', () => {
        expect(values.toWire(values.withDraft(state(), 'height', 'yea high'), 'metric')).toBeNull();
    });
});

describe('marking what has been touched', () => {
    test('a box matching what was built is not edited', () => {
        for (const parameter of state().schema) {
            expect(values.isEdited(state(), parameter, 'metric')).toBe(false);
        }
    });

    test('a box differing from what was built is edited', () => {
        const edited = values.withDraft(state(), 'posts', '5');
        const posts = edited.schema.find((p) => p.key === 'posts');
        expect(values.isEdited(edited, posts, 'metric')).toBe(true);
    });

    test('the same measurement written another way is not an edit', () => {
        const edited = values.withDraft(state(), 'height', '2.4m');
        const height = edited.schema.find((p) => p.key === 'height');
        expect(values.isEdited(edited, height, 'metric')).toBe(false);
    });

    test('changed-from-default is measured against the code, not a saved file', () => {
        // The runner says posts is away from its default; the box still reads 2,
        // which is the default — a saved file is why, and the mark must stay.
        const loaded = values.fromPayload({ ...PAYLOAD, changed: ['posts'] });
        const posts = loaded.schema.find((p) => p.key === 'posts');
        expect(values.isChangedFromDefault(loaded, posts, 'metric')).toBe(true);
    });

    test('typing a different value marks it before any refresh', () => {
        const edited = values.withDraft(state(), 'posts', '5');
        const posts = edited.schema.find((p) => p.key === 'posts');
        expect(values.isChangedFromDefault(edited, posts, 'metric')).toBe(true);
    });

    test('resetting puts every box back to what the code says', () => {
        let edited = values.withDraft(state(), 'posts', '7');
        edited = values.withDraft(edited, 'height', '10ft');
        const back = values.resetToDefaults(edited);
        expect(back.drafts.posts).toBe('2');
        expect(back.drafts.height).toBe('2400mm');
        for (const parameter of back.schema) {
            expect(values.isChangedFromDefault({ ...back, changed: new Set() }, parameter, 'metric')).toBe(false);
        }
    });
});

describe('which unit a bare number means', () => {
    test('follows the viewer, and an angle is always degrees', () => {
        expect(values.defaultUnitFor('length', 'metric')).toBe('mm');
        expect(values.defaultUnitFor('length', 'imperial')).toBe('in');
        expect(values.defaultUnitFor('angle', 'imperial')).toBe('deg');
    });
});

describe('an optional parameter', () => {
    const OPTIONAL = {
        schema: [
            { key: 'trim', kind: 'length', optional: true, default: { value: null } },
            {
                key: 'chamfer', kind: 'length', optional: true,
                default: { value: 0.006, text: '6mm' },
            },
            { key: 'posts', kind: 'count', default: { value: 2 }, minimum: 1 },
        ],
        applied: {
            trim: { value: null },
            chamfer: { value: 0.006, text: '6mm' },
            posts: { value: 2 },
        },
        changed: [],
        canSave: true,
    };
    const state = () => values.fromPayload(OPTIONAL);
    const param = (s, key) => s.schema.find((p) => p.key === key);

    test('starts switched off when it arrived as nothing', () => {
        expect(values.isEnabled(state(), param(state(), 'trim'))).toBe(false);
        expect(values.isEnabled(state(), param(state(), 'chamfer'))).toBe(true);
    });

    test('a parameter that is not optional is always on', () => {
        expect(values.isEnabled(state(), param(state(), 'posts'))).toBe(true);
    });

    test('switched off it sends nothing, whatever the box says', () => {
        const off = values.withEnabled(values.withDraft(state(), 'chamfer', '10mm'), 'chamfer', false);
        expect(values.toWire(off, 'metric').chamfer).toEqual({ value: null });
    });

    test('switched on it sends what the box says', () => {
        const on = values.withDraft(values.withEnabled(state(), 'trim', true), 'trim', '3mm');
        expect(values.toWire(on, 'metric').trim).toEqual({ value: 0.003, text: '3mm' });
    });

    test('keeps its value while off, so switching back on restores it', () => {
        let s = values.withDraft(state(), 'chamfer', '10mm');
        s = values.withEnabled(s, 'chamfer', false);
        expect(s.drafts.chamfer).toBe('10mm');
        s = values.withEnabled(s, 'chamfer', true);
        expect(values.toWire(s, 'metric').chamfer).toEqual({ value: 0.01, text: '10mm' });
    });

    test('one that is off but has a code default starts with it in the box', () => {
        // trim defaults to nothing, so its box is empty; a parameter that
        // defaults to a real value keeps it ready even while switched off.
        const withDefault = values.fromPayload({
            schema: [{ key: 'chamfer', kind: 'length', optional: true, default: { value: 0.006, text: '6mm' } }],
            applied: { chamfer: { value: null } },
        });
        expect(withDefault.drafts.chamfer).toBe('6mm');
        expect(values.isEnabled(withDefault, withDefault.schema[0])).toBe(false);
    });

    test('a box that does not read is not a problem while it is switched off', () => {
        let s = values.withDraft(state(), 'chamfer', 'yea thick');
        expect(values.problems(s, 'metric').chamfer).toMatch(/not a measurement/);
        s = values.withEnabled(s, 'chamfer', false);
        expect(values.problems(s, 'metric')).toEqual({});
        expect(values.toWire(s, 'metric')).not.toBeNull();
    });

    test('switching one on and saying what it is counts as a change', () => {
        const on = values.withDraft(values.withEnabled(state(), 'trim', true), 'trim', '3mm');
        expect(values.isChangedFromDefault(on, param(on, 'trim'), 'metric')).toBe(true);

        const off = values.withEnabled(state(), 'chamfer', false);
        expect(values.isChangedFromDefault(off, param(off, 'chamfer'), 'metric')).toBe(true);
    });

    test('and counts as an edit, so build becomes available', () => {
        const off = values.withEnabled(state(), 'chamfer', false);
        expect(values.isEdited(off, param(off, 'chamfer'), 'metric')).toBe(true);
    });

    test('reset puts the switches back the way the code has them', () => {
        let s = values.withEnabled(state(), 'trim', true);
        s = values.withEnabled(s, 'chamfer', false);
        const back = values.resetToDefaults(s);
        expect(values.isEnabled(back, param(back, 'trim'))).toBe(false);
        expect(values.isEnabled(back, param(back, 'chamfer'))).toBe(true);
    });
});

describe('an optional parameter switched on with nothing in it', () => {
    const state = () => values.fromPayload({
        schema: [{ key: 'trim', kind: 'length', optional: true, default: { value: null } }],
        applied: { trim: { value: null } },
    });

    test('is asked to say what it is, rather than quietly meaning nothing', () => {
        // The switch is the only way to say nothing, so an empty box on a
        // parameter that is switched on is someone part-way through typing.
        const on = values.withEnabled(state(), 'trim', true);
        expect(values.problems(on, 'metric').trim).toMatch(/needs a value/);
        expect(values.toWire(on, 'metric')).not.toBeNull();
    });

    test('and is no longer asked once it is switched back off', () => {
        expect(values.problems(state(), 'metric')).toEqual({});
    });
});
