const { createSelectionHistory, SELECTION_HISTORY_LIMIT } = require('../agent/selection-history');
const { createPanelDirectory } = require('../agent/panel-directory');
const { createKigumiTools } = require('../agent/tools');

const member = (key) => ({ key, name: key });
const entry = (keys, feature = null, panelId = 'viewer:/p/a.py') => ({
    panelId, filePath: '/p/a.py', view: '3d', selection: { frameName: 'a', members: keys.map(member), feature },
});

describe('the selection history', () => {
    test('keeps selections newest first, skipping empty ones and repeats', () => {
        const history = createSelectionHistory();
        history.record(entry(['post']));
        history.record(entry(['post']));
        history.record(entry([]));
        history.record(entry(['post', 'beam']));
        history.record(entry(['post'], { memberKey: 'post', path: 'cut', featureLabel: 'mortise' }));

        expect(history.list().map((one) => [one.selection.members.map((m) => m.key), Boolean(one.selection.feature)]))
            .toEqual([[['post'], true], [['post', 'beam'], false], [['post'], false]]);
        expect(history.list(1)).toHaveLength(1);
        expect(history.list()[0].at).toEqual(expect.any(String));
    });

    test(`keeps the last ${SELECTION_HISTORY_LIMIT}`, () => {
        const history = createSelectionHistory();
        for (let i = 0; i < SELECTION_HISTORY_LIMIT + 5; i++) history.record(entry([`t${i}`]));
        const kept = history.list();
        expect(kept).toHaveLength(SELECTION_HISTORY_LIMIT);
        expect(kept[0].selection.members[0].key).toBe(`t${SELECTION_HISTORY_LIMIT + 4}`);
    });

    test('get_selection_history gives them, with each file relative to the project', async () => {
        const selectionHistory = createSelectionHistory();
        selectionHistory.record(entry(['post']));
        const panels = createPanelDirectory({ views: () => [], host: { workspaceRootFor: () => '/p' }, selectionHistory });
        const tool = createKigumiTools({ panels, run: async () => ({}) }).find((one) => one.name === 'get_selection_history');

        expect(tool.effect).toBe('read');
        const { selections } = JSON.parse((await tool.run({}))[0].text);
        expect(selections).toEqual([expect.objectContaining({ relativePath: 'a.py', panelId: 'viewer:/p/a.py' })]);
    });
});
