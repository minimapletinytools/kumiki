/**
 * Runs inside the standalone app (see run-app-tests.js): opens the repo as a
 * workspace, then checks the explorer, a frame viewer, the screenshot round
 * trip, a pattern opened through the quick pick, and the Log tab.
 */

const fs = require('fs');
const path = require('path');

const REPO = path.resolve(__dirname, '..', '..', '..');
const FRAME = path.join(REPO, 'patterns', 'structures', 'my_cute_frame.py');
const ARTIFACTS = process.env.KIGUMI_TEST_ARTIFACTS || null;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(check, { timeoutMs = 60000, intervalMs = 250 } = {}) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
        const value = await check();
        if (value) return value;
        if (Date.now() > deadline) throw new Error(`Timed out after ${timeoutMs}ms`);
        await sleep(intervalMs);
    }
}

module.exports = async function smoke({ runAppCommand, connection, window, logLines, onShellCommand, settings, panels }) {
    const results = [];
    const check = (name, ok, detail) => {
        results.push({ name, ok: !!ok, detail });
        console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` -- ${detail}` : ''}`);
    };
    const inShell = (script) => window().webContents.executeJavaScript(script);
    async function capture(name) {
        if (!ARTIFACTS) return;
        fs.mkdirSync(ARTIFACTS, { recursive: true });
        const image = await window().webContents.capturePage();
        fs.writeFileSync(path.join(ARTIFACTS, `${name}.png`), image.toPNG());
    }

    try {
        const sidebar = await waitFor(async () => {
            const snapshot = await runAppCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: false });
            return snapshot && snapshot.state.workspaceRoot && !snapshot.state.isScanning ? snapshot : null;
        });
        const roots = sidebar.roots.map((root) => root.label);
        check('explorer scans the workspace', sidebar.state.frameCount > 0 && sidebar.state.workspacePatternbookCount > 0,
            `${sidebar.state.frameCount} frames, ${sidebar.state.workspacePatternbookCount} patternbooks`);
        check('explorer shows Frames and Patterns', roots.some((l) => l.startsWith('Frames')) && roots.some((l) => l.startsWith('Patterns')));
        const rows = await waitFor(() => inShell(
            'document.querySelector("#slot-left iframe")?.contentDocument?.querySelectorAll(".ks-row").length || 0'));
        check('the explorer panel renders in the left slot', rows > 0, `${rows} rows`);
        await capture('01-shell');

        await runAppCommand('kigumi.openFrameFromSidebar', FRAME);
        const session = await runAppCommand('kigumi.testGetSessionSnapshot', { filePath: FRAME });
        check('a frame opens in a viewer tab', session && session.exists && connection().tabs.tabs.length === 1, session && session.panelTitle);
        const canvas = await waitFor(() => inShell(`(() => {
            const frame = document.querySelector('#slot-center iframe:not([hidden])');
            return !!(frame && frame.contentDocument && frame.contentDocument.querySelector('canvas'));
        })()`), { timeoutMs: 15000 });
        check('the viewer panel draws into a canvas', canvas);
        await sleep(1000);
        await capture('02-viewer');

        const shotPath = ARTIFACTS ? path.join(ARTIFACTS, '03-screenshot-command.png') : path.join(REPO, '.kigumi', 'automation', 'app-smoke.png');
        const shot = await runAppCommand('kigumi.captureScreenshot', { filePath: FRAME, outputPath: shotPath, timeoutMs: 15000 });
        check('the viewer answers a screenshot round trip', shot && shot.ok && shot.screenshot.byteLength > 1000,
            shot && shot.screenshot && `${shot.screenshot.width}x${shot.screenshot.height}`);

        // What an agent is told about the view: the frame, 3D, and what is selected (nothing yet).
        const listed = panels().list();
        const described = await panels().describe(`viewer:${FRAME}`);
        check('an agent can list the view and ask what it shows',
            listed.some((panel) => panel.kind === 'viewer' && panel.filePath === FRAME)
                && described && described.kind === 'viewer' && described.view === '3d' && described.frameName === 'My Cute Frame'
                && described.selection && Array.isArray(described.selection.members),
            described && JSON.stringify({ view: described.view, frame: described.frameName }));

        const picking = runAppCommand('kigumi.browsePatterns');
        await waitFor(() => inShell('!document.getElementById("quickpick").hidden && document.querySelectorAll("#quickpick .item").length'), { timeoutMs: 30000 });
        await capture('04-quickpick');
        const labels = await inShell('Array.from(document.querySelectorAll("#quickpick .item-label")).map((e) => e.textContent)');
        const wanted = labels[Math.min(1, labels.length - 1)];
        await inShell(`(() => {
            const filter = document.getElementById('quickpick-filter');
            filter.value = ${JSON.stringify(wanted)};
            filter.dispatchEvent(new Event('input'));
        })()`);
        const filtered = await inShell('Array.from(document.querySelectorAll("#quickpick .item-label")).map((e) => e.textContent)');
        check('the quick pick filters by name', filtered.length > 0 && filtered.every((label) => label.includes(wanted)), `${wanted}: ${filtered.join(', ')}`);
        await inShell(`document.getElementById('quickpick-filter').dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(filtered.length > 0 ? 'Enter' : 'Escape')} }))`);
        await picking;
        const tabs = connection().tabs.tabs.map((tab) => connection().panels.get(tab.id).title);
        check('the picked pattern opens in a second tab', tabs.length === 2 && tabs[1].includes(wanted), tabs.join(' | '));
        await sleep(1000);
        await capture('05-pattern');

        const refreshCount = async () => (await runAppCommand('kigumi.automationListSessions')).sessions
            .reduce((sum, one) => sum + (one.refreshSequence || 0), 0);
        const refreshesBefore = await refreshCount();
        window().webContents.forcefullyCrashRenderer();
        await waitFor(async () => (await refreshCount()) > refreshesBefore, { timeoutMs: 30000 });
        const rowsAfter = await waitFor(() => inShell(
            'document.querySelector("#slot-left iframe")?.contentDocument?.querySelectorAll(".ks-row").length || 0'));
        check('a crashed window reloads its panels and redraws the viewers', !window().webContents.isCrashed() && rowsAfter > 0,
            `refreshes ${refreshesBefore} -> ${await refreshCount()}, explorer rows ${rowsAfter}`);

        check('auto refresh defaults to on in the app', settings.get('viewer.autoRefreshOnFileChange') === true);
        const edited = { ...JSON.parse(fs.readFileSync(settings.filePath, 'utf8')), 'viewer.autoRefreshOnFileChange': false };
        fs.writeFileSync(settings.filePath, JSON.stringify(edited, null, 2));
        await waitFor(() => settings.get('viewer.autoRefreshOnFileChange') === false, { timeoutMs: 5000 });
        check('editing settings.json applies without a restart', true);

        onShellCommand('openLog');
        const logLinesShown = await waitFor(() => inShell(`(() => {
            const frame = document.querySelector('#slot-center iframe:not([hidden])');
            return frame && frame.contentDocument ? frame.contentDocument.querySelectorAll('#lines div').length : 0;
        })()`));
        check('the Log tab opens and shows the log', connection().activePanel && connection().activePanel.type === 'log' && logLinesShown > 0, `${logLinesShown} lines`);
        await capture('06-log');

        connection().activePanel.dispose();
        check('closing a tab activates a neighbour', connection().tabs.tabs.length === 2 && connection().tabs.activeId !== null);

        // Test Monaco editor panel opening
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
        check('closing editor tab succeeds', connection().tabs.tabs.length === 2);

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
            connection().activePanel.dispose();
        } finally {
            fs.rmSync(scratch, { force: true });
        }
        // Test layout toggles: explorer (left) and agent (right)
        await inShell(`(() => { document.querySelector('#toggle-left').click(); })()`);
        const leftHidden = await waitFor(() => inShell(`(() => {
            const slot = document.querySelector('#slot-left');
            return slot && slot.hidden;
        })()`));
        check('clicking toggle-left hides the explorer sidebar', leftHidden);

        await inShell(`(() => { document.querySelector('#toggle-left').click(); })()`);
        const leftRestored = await waitFor(() => inShell(`(() => {
            const slot = document.querySelector('#slot-left');
            return slot && !slot.hidden;
        })()`));
        check('clicking toggle-left restores the explorer sidebar', leftRestored);

        await inShell(`(() => { document.querySelector('#toggle-right').click(); })()`);
        const agentOpened = await waitFor(() => inShell(`(() => {
            const slot = document.querySelector('#slot-right');
            const frame = slot ? slot.querySelector('iframe') : null;
            return slot && !slot.hidden && frame !== null;
        })()`));
        check('clicking toggle-right opens the agent sidebar', agentOpened && connection().findPanel((p) => p.type === 'agent') !== undefined);

        await inShell(`(() => { document.querySelector('#toggle-right').click(); })()`);
        const agentHidden = await waitFor(() => inShell(`(() => {
            const slot = document.querySelector('#slot-right');
            return !slot || slot.hidden;
        })()`));
        // Hidden, not closed: the conversation is kept.
        check('clicking toggle-right again hides the agent and keeps it', agentHidden && connection().findPanel((p) => p.type === 'agent') !== undefined);

        const errors = logLines().filter((line) => /traceback|uncaught|\[error\]/i.test(line));
        check('no errors in the log', errors.length === 0, errors.slice(0, 3).join(' / '));
    } catch (error) {
        check('smoke run completed', false, error.stack || String(error));
    }

    if (ARTIFACTS) {
        fs.writeFileSync(path.join(ARTIFACTS, 'app.log'), logLines().join('\n'));
    }
    const failed = results.filter((result) => !result.ok);
    console.log(`${results.length - failed.length} passed, ${failed.length} failed`);
    return failed.length === 0;
};
