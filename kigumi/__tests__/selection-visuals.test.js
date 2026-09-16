const {
    SELECTION_VISUAL_STATES,
    computeSelectionVisualContext,
    selectionVisualPolicy,
} = require('../webview/selection-visuals.js');

// Five states and a fallback, deciding what every timber in the frame looks
// like. The function was written inside viewer-app.js with a comment saying the
// decision is "pure and independently testable", and then never tested --
// nothing in node can load that file. Moving it out was the whole cost of
// testing it.

const focus = (extra = {}) => ({ timberKey: 'post#0', path: [], featureLabel: null, ...extra });

describe('which state a selection is in', () => {
    test('nothing selected', () => {
        const context = computeSelectionVisualContext([], null);

        expect(context.state).toBe(SELECTION_VISUAL_STATES.NOTHING_SELECTED);
        expect(context.hasSubselection).toBe(false);
    });

    test('nothing selected wins even when a focus is left behind', () => {
        // The selection is what says whether anything is selected.
        const context = computeSelectionVisualContext([], focus({ featureLabel: 'front' }));

        expect(context.state).toBe(SELECTION_VISUAL_STATES.NOTHING_SELECTED);
    });

    test('a timber, with nothing picked inside it', () => {
        const context = computeSelectionVisualContext(['post#0'], null);

        expect(context.state).toBe(SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB);
        expect(context.subselectionTimberKey).toBeNull();
    });

    test('a focus that names neither a path nor a feature is no subselection', () => {
        const context = computeSelectionVisualContext(['post#0'], focus());

        expect(context.state).toBe(SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB);
    });

    test('a feature beats a path: it is the most specific thing picked', () => {
        const context = computeSelectionVisualContext(
            ['post#0'], focus({ path: ['cut', 'deeper'], featureLabel: 'front' }));

        expect(context.state).toBe(SELECTION_VISUAL_STATES.FEATURE_SELECTED);
    });

    test('a path two deep, with no feature', () => {
        const context = computeSelectionVisualContext(
            ['post#0'], focus({ path: ['cut', 'deeper'] }));

        expect(context.state).toBe(SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB);
    });

    test('a path one deep, with no feature', () => {
        const context = computeSelectionVisualContext(['post#0'], focus({ path: ['cut'] }));

        expect(context.state).toBe(SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB);
    });
});

describe('which timber owns the subselection', () => {
    test('the focus says, when it names one', () => {
        const context = computeSelectionVisualContext(
            ['post#0', 'girt#0'], focus({ timberKey: 'girt#0', featureLabel: 'front' }));

        expect(context.subselectionTimberKey).toBe('girt#0');
    });

    test('with one timber selected and a focus naming none, it is that timber', () => {
        const context = computeSelectionVisualContext(
            ['post#0'], focus({ timberKey: null, featureLabel: 'front' }));

        expect(context.subselectionTimberKey).toBe('post#0');
    });

    test('with SEVERAL selected and a focus naming none, nobody owns it', () => {
        // Worth pinning because of what it does downstream: no member matches,
        // so every timber ghosts and the frame goes faint with nothing lit.
        const context = computeSelectionVisualContext(
            ['post#0', 'girt#0'], focus({ timberKey: null, featureLabel: 'front' }));

        expect(context.subselectionTimberKey).toBeNull();
    });

    test('the selected set comes back as a set, whatever went in', () => {
        const context = computeSelectionVisualContext(['post#0', 'post#0'], null);

        expect(context.selectedTimberSet.has('post#0')).toBe(true);
        expect(context.selectedTimberSet.size).toBe(1);
    });
});

describe('what a state does to the opacities', () => {
    const BASE = 0.4;

    test('nothing selected dims nothing', () => {
        const policy = selectionVisualPolicy(SELECTION_VISUAL_STATES.NOTHING_SELECTED, BASE);

        expect(policy.dimmedOpacity).toBe(1.0);
        expect(policy.selectedTimberOpacity).toBe(1.0);
    });

    test('a selected timber dims the rest to what the reader asked for', () => {
        const policy = selectionVisualPolicy(
            SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB, BASE);

        expect(policy.dimmedOpacity).toBe(BASE);
    });

    test.each([
        [SELECTION_VISUAL_STATES.FEATURE_SELECTED, 0.18],
        [SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB, 0.2],
        [SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB, 0.25],
    ])('a subselection dims the rest further than asked: %s', (state, ceiling) => {
        // The slider is a ceiling here, not the value: something is being
        // looked at INSIDE a timber, and the rest of the frame has to get out
        // of the way further than the general setting says.
        expect(selectionVisualPolicy(state, BASE).dimmedOpacity).toBe(ceiling);
    });

    test('and never dims LESS than asked, however low the slider goes', () => {
        for (const state of Object.values(SELECTION_VISUAL_STATES)) {
            const policy = selectionVisualPolicy(state, 0.02);
            expect(policy.dimmedOpacity).toBeLessThanOrEqual(
                state === SELECTION_VISUAL_STATES.NOTHING_SELECTED ? 1.0 : 0.02);
        }
    });

    test('the deeper the pick, the more the owning timber fades', () => {
        const owning = (state) => selectionVisualPolicy(state, BASE).selectedTimberOpacity;

        expect(owning(SELECTION_VISUAL_STATES.FEATURE_SELECTED))
            .toBeLessThan(owning(SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB));
        expect(owning(SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB))
            .toBeLessThan(owning(SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB));
    });

    test('every state has a policy', () => {
        for (const state of Object.values(SELECTION_VISUAL_STATES)) {
            expect(typeof selectionVisualPolicy(state, BASE).dimmedOpacity).toBe('number');
        }
    });

    test('and a state nobody has heard of still gets one', () => {
        // The fallback exists so a new state cannot make the frame render
        // undefined; it should behave like the shallowest subselection.
        const unknown = selectionVisualPolicy('something_new', BASE);

        expect(unknown).toEqual(
            selectionVisualPolicy(SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB, BASE));
    });
});

describe('folding the state into something comparable', () => {
    // The value the whole pulled design rests on: the frame loop folds the
    // state and redraws when the answer differs. Only its COMPLETENESS was
    // checked, by a test that reads the source; what it actually does with what
    // it is given was not checked at all until it came out of viewer-app.js.
    const { visualSignatureOf } = require('../webview/selection-visuals.js');

    const base = () => ({
        unselectedTransparencyPercent: 60,
        selectedTransparencyPercent: 0,
        edgeLineVisibilityPercent: 100,
        edgeMode: 'overlay',
        showDrawingGhosts: true,
        selected: ['post#0'],
        focus: { timberKey: 'post#0', path: ['cut'], featureLabel: 'front' },
        lit: { csg: { key: 'post#0|cut|front' }, hover: null, held: null },
        members: [['post#0', 'timber-default', false, false]],
    });

    test('the same state folds the same way', () => {
        expect(visualSignatureOf(base())).toBe(visualSignatureOf(base()));
    });

    test('and nothing at all is still an answer', () => {
        expect(typeof visualSignatureOf(undefined)).toBe('string');
        expect(visualSignatureOf(undefined)).toBe(visualSignatureOf({}));
    });

    test.each([
        ['unselectedTransparencyPercent', 61],
        ['selectedTransparencyPercent', 20],
        ['edgeLineVisibilityPercent', 50],
        ['edgeMode', 'none'],
        ['showDrawingGhosts', false],
    ])('changing %s changes it', (field, value) => {
        const changed = { ...base(), [field]: value };

        expect(visualSignatureOf(changed)).not.toBe(visualSignatureOf(base()));
    });

    test('selecting another timber changes it', () => {
        const changed = { ...base(), selected: ['post#0', 'girt#0'] };

        expect(visualSignatureOf(changed)).not.toBe(visualSignatureOf(base()));
    });

    test.each([
        ['timberKey', 'girt#0'],
        ['featureLabel', 'back'],
    ])('picking a different %s changes it', (field, value) => {
        const changed = { ...base(), focus: { ...base().focus, [field]: value } };

        expect(visualSignatureOf(changed)).not.toBe(visualSignatureOf(base()));
    });

    test('drilling deeper changes it', () => {
        const changed = { ...base(), focus: { ...base().focus, path: ['cut', 'deeper'] } };

        expect(visualSignatureOf(changed)).not.toBe(visualSignatureOf(base()));
    });

    test('a timber appearing or leaving changes it', () => {
        // A geometry rebuild, without anyone having to say so.
        const more = { ...base(), members: [...base().members, ['girt#0', 'timber-default', false, false]] };

        expect(visualSignatureOf(more)).not.toBe(visualSignatureOf(base()));
        expect(visualSignatureOf({ ...base(), members: [] }))
            .not.toBe(visualSignatureOf(base()));
    });

    test.each([
        ['being hidden', 2],
        ['leaving the drawing', 3],
    ])('a member %s changes it', (_what, index) => {
        const members = base().members.map((row) => [...row]);
        members[0][index] = true;

        expect(visualSignatureOf({ ...base(), members }))
            .not.toBe(visualSignatureOf(base()));
    });

    test('what is lit changes it', () => {
        const hovering = { ...base(), lit: { ...base().lit, hover: { key: 'girt#0|', refused: false } } };

        expect(visualSignatureOf(hovering)).not.toBe(visualSignatureOf(base()));
    });

    test('and so does the same thing turning red under a resting pointer', () => {
        const allowed = { ...base(), lit: { hover: { key: 'girt#0|', refused: false } } };
        const refused = { ...base(), lit: { hover: { key: 'girt#0|', refused: true } } };

        expect(visualSignatureOf(allowed)).not.toBe(visualSignatureOf(refused));
    });

    test('two different states cannot fold to one string', () => {
        // The focus contributes three adjacent fields -- member, path, feature.
        // Joined on a separator that can appear inside one of them, these two
        // states BOTH come out "a|b|c|d", and a collision here is a frame that
        // never redraws because the answer looked unchanged.
        const one = { ...base(), focus: { timberKey: 'a', path: ['b|c'], featureLabel: 'd' } };
        const other = { ...base(), focus: { timberKey: 'a|b', path: ['c'], featureLabel: 'd' } };

        expect(visualSignatureOf(one)).not.toBe(visualSignatureOf(other));
    });

});
