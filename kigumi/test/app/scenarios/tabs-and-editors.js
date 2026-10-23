// Tabs: the Log tab; closing a tab activates its neighbour; a source file in the Monaco editor tab,
// described to an agent, and following a change made on disk.

const fs = require('fs');
const path = require('path');

module.exports = {
    name: 'tabs-and-editors',
    async run({ check, inShell, waitFor, capture, runAppCommand, connection, panels, onShellCommand, openFrame, REPO, FRAME }) {
        await openFrame(FRAME);
        onShellCommand('openLog');
        const logLinesShown = await waitFor(() => inShell(`(() => {
            const frame = document.querySelector('#slot-center iframe:not([hidden])');
            return frame && frame.contentDocument ? frame.contentDocument.querySelectorAll('#lines div').length : 0;
        })()`));
        check('the Log tab opens and shows the log', connection().activePanel && connection().activePanel.type === 'log' && logLinesShown > 0, `${logLinesShown} lines`);
        await capture('06-log');

        connection().activePanel.dispose();
        check('closing a tab activates a neighbour', connection().tabs.tabs.length === 1 && connection().activePanel !== null
            && connection().activePanel.type === 'viewer');

        await runAppCommand('kigumi.viewPatternSource', { data: { sourceFile: FRAME } });
        const editorPanel = await waitFor(() => {
            const active = connection().activePanel;
            return active && active.type === 'editor' ? active : null;
        });
        check('viewPatternSource opens a file in the Monaco editor panel', !!editorPanel && editorPanel.filePath === FRAME);
        const editorReady = await waitFor(() => inShell(`(() => {
            const frame = document.querySelector('#slot-center iframe:not([hidden])');
            return !!(frame && frame.contentDocument && frame.contentDocument.querySelector('.monaco-editor'));
        })()`), { timeoutMs: 15000 });
        check('Monaco editor initializes and renders inside iframe', editorReady);

        const editorDescribed = await panels().describe(`tab:${connection().activePanel.id}`);
        check('an agent can ask an editor tab what it shows',
            editorDescribed && editorDescribed.kind === 'editor' && editorDescribed.filePath === FRAME && editorDescribed.lineCount > 10,
            editorDescribed && `${editorDescribed.lineCount} lines`);

        connection().activePanel.dispose();
        check('closing editor tab succeeds', connection().tabs.tabs.length === 1);

        // A change made on disk while the tab is open, with nothing unsaved, comes into the tab.
        // Inside the workspace (a file outside it opens as a read-only copy), where git ignores it.
        const scratch = path.join(REPO, '.kigumi', `editor-smoke-${process.pid}.py`);
        fs.mkdirSync(path.dirname(scratch), { recursive: true });
        fs.writeFileSync(scratch, 'first = 1\n');
        try {
            await runAppCommand('kigumi.viewPatternSource', { data: { sourceFile: scratch } });
            const editorText = () => inShell(`(() => {
                const frame = document.querySelector('#slot-center iframe:not([hidden])');
                const win = frame && frame.contentWindow;
                const models = win && win.monaco ? win.monaco.editor.getModels() : [];
                return models.length ? models[0].getValue() : null;
            })()`);
            const opened = await waitFor(async () => (await editorText()) === 'first = 1\n', { timeoutMs: 15000 })
                .then(() => true, () => false);
            if (!opened) {
                const active = connection().activePanel;
                throw new Error(`scratch file did not open: active ${active && active.type} ${active && active.filePath}, text ${JSON.stringify(await editorText())}`);
            }
            fs.writeFileSync(scratch, 'second = 2\n');
            const updated = await waitFor(async () => (await editorText()) === 'second = 2\n', { timeoutMs: 15000 })
                .then(() => true, () => false);
            check('a change on disk comes into an open editor tab', updated);
        } finally {
            fs.rmSync(scratch, { force: true });
        }
    },
};
