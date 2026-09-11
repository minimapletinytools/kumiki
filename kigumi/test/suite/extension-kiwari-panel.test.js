const assert = require('assert');
const path = require('path');
const vscode = require('vscode');

async function waitFor(predicate, timeoutMs = 20000, intervalMs = 150) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const value = await predicate();
        if (value) {
            return value;
        }
        await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    throw new Error(`Timed out waiting for condition after ${timeoutMs}ms`);
}

async function activateKigumiExtension() {
    const extension = vscode.extensions.all.find((candidate) =>
        candidate.id.toLowerCase().endsWith('.kigumi'));
    assert.ok(extension, 'Expected Kigumi extension to be available in Extension Host');
    await extension.activate();
}

const FIXTURE = path.resolve(__dirname, '..', '..', 'test-fixtures', 'kiwari_frame.py');

async function snapshotFor(filePath) {
    return waitFor(async () => {
        const candidate = await vscode.commands.executeCommand('kigumi.testGetSessionSnapshot', {
            filePath,
            includePanelSnapshot: true,
            timeoutMs: 5000,
        });
        if (!candidate || !candidate.exists || !candidate.runnerAlive || !candidate.panelSnapshot) {
            return null;
        }
        return candidate;
    }, 30000, 200);
}

describe('Kigumi parameters panel', () => {
    it('renders a control for every parameter the frame declares', async function () {
        this.timeout(90000);

        await activateKigumiExtension();
        await vscode.commands.executeCommand('workbench.action.closeAllEditors');

        const openResult = await vscode.commands.executeCommand('kigumi.automationOpenFileInViewer', {
            filePath: FIXTURE,
        });
        assert.ok(openResult && openResult.ok, 'Expected the fixture to open');

        const snapshot = await snapshotFor(FIXTURE);
        const panel = snapshot.panelSnapshot;

        assert.strictEqual(panel.hasKiwariControls, true, 'Expected the parameters panel to be rendered');
        assert.deepStrictEqual(
            panel.kiwariKeys,
            ['posts', 'post_height', 'spacing', 'size', 'lean', 'alternating', 'cap', 'cap_end'],
            'Expected one row per declared parameter, in declaration order',
        );
        assert.deepStrictEqual(panel.kiwariChangedKeys, [],
            'Nothing has been touched, so nothing should be marked as changed');
        assert.deepStrictEqual(panel.kiwariBadKeys, [],
            'Every box holds what the frame was built with, so none should be marked bad');
        assert.strictEqual(panel.kiwariBuildDisabled, true,
            'Nothing has been edited, so there is nothing to build');
        assert.strictEqual(snapshot.frame.name, 'Kiwari Test Frame (2 posts)');

        // `cap` is optional and defaults to nothing, so it is the one row with
        // a switch, and that switch starts off.
        assert.deepStrictEqual(panel.kiwariOptionalKeys, ['cap'],
            'Expected only the optional parameter to carry a switch');
        assert.deepStrictEqual(panel.kiwariSwitchedOffKeys, ['cap'],
            'Expected the optional parameter to start switched off');
        assert.deepStrictEqual(panel.kiwariChangedKeys, [],
            'An optional parameter that is off by design is not a change');
    });

    it('shows no parameters panel for a frame that declares none', async function () {
        this.timeout(90000);

        await activateKigumiExtension();
        await vscode.commands.executeCommand('workbench.action.closeAllEditors');

        const plain = path.resolve(__dirname, '..', '..', 'test-fixtures', 'minimal_frame.py');
        await vscode.commands.executeCommand('kigumi.automationOpenFileInViewer', { filePath: plain });

        const panel = (await snapshotFor(plain)).panelSnapshot;
        assert.strictEqual(panel.hasKiwariControls, false,
            'A frame with no parameters should show no panel at all');
        assert.strictEqual(panel.hasRenderControls, true,
            'The settings panel should still be there beside it');
    });
});
