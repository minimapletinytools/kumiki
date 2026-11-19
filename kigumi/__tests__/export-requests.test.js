// A view's export requests (export-requests.js).
const { exportDirectory, pushCadqueryStatus } = require('../export-requests');

test("exports go in kigumi_exports/<the frame's file name>, made safe for a folder name", () => {
    expect(exportDirectory({ projectRoot: '/p', filePath: '/p/sheds/my shed!.py' })).toBe('/p/kigumi_exports/my_shed');
    expect(exportDirectory({ projectRoot: '/p', filePath: '/p/___.py' })).toBe('/p/kigumi_exports/frame');
});

test('the view is told whether STEP export can run, unless it closed while that was being asked', async () => {
    const view = { postMessage: jest.fn(() => Promise.resolve(true)) };
    const session = { panel: view, log: jest.fn(), runnerSession: { isCadqueryOcpInstalled: async () => true } };
    await pushCadqueryStatus(session);
    expect(view.postMessage).toHaveBeenCalledWith({ type: 'dependencyStatus', payload: { cadqueryOcpInstalled: true } });

    const closing = { panel: view, log: jest.fn(), runnerSession: { isCadqueryOcpInstalled: async () => { closing.panel = null; return false; } } };
    await expect(pushCadqueryStatus(closing)).resolves.toBeUndefined();
    expect(view.postMessage).toHaveBeenCalledTimes(1);
});
