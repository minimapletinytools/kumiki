const { memberStateFor, appearanceFor } = require('../webview/member-states.js');
const {
    SELECTION_VISUAL_STATES, computeSelectionVisualContext, selectionVisualPolicy,
} = require('../webview/selection-visuals.js');

const DRAWING_CONTEXT_OPACITY = 0.12;
const PROFILE = { edgeOpacity: 0.9, reflectionOpacity: 0.2 };

/** _memberAppearance as it was before member states, kept to check nothing changed. */
function previousAppearance(memberKey, { hidden, visualContext, policy, baseSelectedOpacity, drawnMembers,
    showDrawingGhosts, profile, edgeLineVisibilityPercent, edgeMode }) {
    let name = 'normal';
    let opacity = baseSelectedOpacity;
    if (hidden) {
        name = 'hidden';
    } else if (visualContext.state === SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB) {
        const selected = visualContext.selectedTimberSet.has(memberKey);
        name = selected ? 'selected' : 'ghost';
        opacity = selected ? baseSelectedOpacity : policy.dimmedOpacity;
    } else if (visualContext.hasSubselection) {
        const selected = visualContext.subselectionTimberKey === memberKey;
        name = selected ? 'selected' : 'ghost';
        opacity = selected ? policy.selectedTimberOpacity : policy.dimmedOpacity;
    }
    const isDrawingContext = name !== 'hidden' && Boolean(drawnMembers) && !drawnMembers.has(memberKey);
    if (isDrawingContext) {
        name = showDrawingGhosts ? 'ghost' : 'hidden';
        opacity = Math.min(opacity, DRAWING_CONTEXT_OPACITY);
    }
    const edgeOpacity = (profile ? profile.edgeOpacity * (edgeLineVisibilityPercent / 100)
        : (edgeLineVisibilityPercent / 100)) * (isDrawingContext ? DRAWING_CONTEXT_OPACITY : 1);
    return {
        name, opacity, edgeOpacity, edgesVisible: edgeMode !== 'none',
        reflectionOpacity: (profile ? profile.reflectionOpacity : 0.14) * opacity,
    };
}

const SELECTIONS = {
    nothing: [[], null],
    timber: [['post'], null],
    node: [['post'], { timberKey: 'post', path: ['cut'] }],
    deeperNode: [['post'], { timberKey: 'post', path: ['cut', 'tenon'] }],
    feature: [['post'], { timberKey: 'post', path: ['cut'], featureLabel: 'cheek' }],
};

describe('member states reproduce the appearance they replaced', () => {
    const cases = [];
    for (const [selectionName, [selected, focus]] of Object.entries(SELECTIONS)) {
        for (const memberKey of ['post', 'girt']) {
            for (const hidden of [false, true]) {
                for (const drawnMembers of [null, new Set(['post']), new Set(['girt'])]) {
                    for (const showDrawingGhosts of [true, false]) {
                        for (const profile of [PROFILE, null]) {
                            cases.push([selectionName, memberKey, hidden, drawnMembers, showDrawingGhosts,
                                profile, selected, focus]);
                        }
                    }
                }
            }
        }
    }

    test.each(cases)('%s / %s hidden=%s drawn=%p ghosts=%s', (
        _name, memberKey, hidden, drawnMembers, showDrawingGhosts, profile, selected, focus) => {
        const visualContext = computeSelectionVisualContext(selected, focus);
        const policy = selectionVisualPolicy(visualContext.state, 0.4);
        const settings = {
            baseSelectedOpacity: 0.95, policy, profile, edgeLineVisibilityPercent: 70, edgeMode: 'overlay',
            showDrawingGhosts, drawingContextOpacity: DRAWING_CONTEXT_OPACITY,
        };

        const state = memberStateFor(memberKey, { hidden, visualContext, drawnMembers });

        expect(appearanceFor(state, settings)).toEqual(previousAppearance(memberKey, {
            hidden, visualContext, policy, drawnMembers, ...settings,
        }));
    });
});

describe('member states', () => {
    const context = (selected, focus) => computeSelectionVisualContext(selected, focus);

    test.each([
        ['nothing', 'post', 'none'],
        ['timber', 'post', 'selected'],
        ['timber', 'girt', 'dimmed'],
        ['feature', 'post', 'drilledInto'],
        ['feature', 'girt', 'dimmed'],
    ])('with %s selected, %s is %s', (selection, key, expected) => {
        const [selected, focus] = SELECTIONS[selection];

        expect(memberStateFor(key, { visualContext: context(selected, focus) }).selection).toBe(expected);
    });

    test('a drawing names its subjects and leaves the rest as context', () => {
        const drawnMembers = new Set(['post']);
        const visualContext = context([], null);

        expect(memberStateFor('post', { visualContext, drawnMembers }).drawing).toBe('subject');
        expect(memberStateFor('girt', { visualContext, drawnMembers }).drawing).toBe('context');
        expect(memberStateFor('girt', { visualContext }).drawing).toBe('none');
    });

    test('a state is plain data, so it can be compared and folded', () => {
        const state = memberStateFor('post', { hidden: true, visualContext: context(['post'], null) });

        expect(JSON.parse(JSON.stringify(state))).toEqual(state);
    });
});
