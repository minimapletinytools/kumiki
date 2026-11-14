const fs = require('fs');
const os = require('os');
const path = require('path');
const { placement, configuration, agentPrompt } = require('../webview/stl-placement-model');
const { applyPlacementEdit } = require('../stl-placement-source');

test('placement preserves independent axes and rejects invalid scales', () => {
    const value = placement({ scale: [2, 3, 4], rotation: [90, 0, -90] });
    expect(value.translation).toEqual([0, 0, 0]);
    expect(configuration(value)).toContain('"scale":[2,3,4]');
    expect(agentPrompt('leg', value)).toContain('shared by several timbers');
    expect(() => placement({ scale: [0, 1, 1] })).toThrow();
    expect(() => placement({ translation: [Infinity, 0, 0] })).toThrow();
});

test('source update refuses unsaved or changed source', async () => {
    const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'stl-placement-'));
    const file = path.join(folder, 'frame.py');
    fs.writeFileSync(file, 'before');
    const edit = { path: file, expected: 'before', updated: 'after' };
    try {
        await expect(applyPlacementEdit({ getDocumentState: async () => ({ isDirty: true }) }, edit)).rejects.toThrow('unsaved');
        expect(fs.readFileSync(file, 'utf8')).toBe('before');
        await expect(applyPlacementEdit({ getDocumentState: async () => ({ isDirty: false }) }, { ...edit, expected: 'stale' })).rejects.toThrow('changed');
        await applyPlacementEdit({ getDocumentState: async () => ({ isDirty: false }) }, edit);
        expect(fs.readFileSync(file, 'utf8')).toBe('after');
    } finally { fs.rmSync(folder, { recursive: true }); }
});
