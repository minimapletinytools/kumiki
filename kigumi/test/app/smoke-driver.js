/**
 * Runs inside the standalone app (see run-app-tests.js): opens the repo as a
 * workspace, then checks the explorer, a frame viewer, the screenshot round
 * trip, a pattern opened through the quick pick, and the Log tab.
 */

const fs = require('fs');
const path = require('path');

const REPO = path.resolve(__dirname, '..', '..', '..');
const FRAME = path.join(REPO, 'patterns', 'structures', 'my_cute_frame.py');
const PARAMETER_FRAME = path.join(REPO, 'patterns', 'structures', 'dovetailed_sawhorse.py');
// A frame with drawings, in rough stock: its views draw dotted perfect faces and centerlines.
const DRAWING_FRAME = path.join(REPO, 'patterns', 'structures', 'my_cute_frame_drawing_test.py');
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

        // The explorer's "All files": opened folder by folder, then a frame opened from its right-click menu.
        const inExplorer = (body) => inShell(`(() => {
            const doc = document.querySelector("#slot-left iframe")?.contentDocument;
            if (!doc) return null;
            const row = (key) => doc.querySelector('.ks-row[data-key="' + CSS.escape(key) + '"]');
            ${body}
        })()`);
        const firstRow = await inExplorer(`const first = doc.querySelector('.ks-tree .ks-row');
            return first && { key: first.dataset.key, expanded: first.getAttribute('aria-expanded') };`);
        check('All files is the explorer\'s first row, collapsed', firstRow && firstRow.key === 'files-root' && firstRow.expanded === 'false',
            JSON.stringify(firstRow));
        const openFolder = async (key, child) => {
            await inExplorer(`row(${JSON.stringify(key)})?.querySelector('.ks-twistie')?.click(); return true;`);
            return waitFor(() => inExplorer(`return !!row(${JSON.stringify(child)});`), { timeoutMs: 10000 }).catch(() => false);
        };
        const rootListed = await openFolder('files-root', `file-folder:${path.join(REPO, 'patterns')}`);
        const venvHidden = await inExplorer(`return !row(${JSON.stringify(`file-folder:${path.join(REPO, '.venv')}`)});`);
        check('All files lists the workspace when opened, leaving out .venv', rootListed && venvHidden);
        await openFolder(`file-folder:${path.join(REPO, 'patterns')}`, `file-folder:${path.join(REPO, 'patterns', 'structures')}`);
        const frameListed = await openFolder(`file-folder:${path.join(REPO, 'patterns', 'structures')}`, `file:${FRAME}`);
        const frameIcon = await inExplorer(`return !!row(${JSON.stringify(`file:${FRAME}`)})?.querySelector('.codicon-fish2-very-sad');`);
        check('a frame in All files has the frame icon', frameListed && frameIcon);
        await inExplorer(`const target = row(${JSON.stringify(`file:${FRAME}`)});
            const box = target.getBoundingClientRect();
            target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: box.left + 10, clientY: box.top + 5 }));
            return true;`);
        const choseOpen = await waitFor(() => inExplorer(`const item = [...doc.querySelectorAll('.ks-menu-item')]
            .find((one) => one.textContent.includes('Open in Viewer'));
            if (!item) return false;
            item.click();
            return true;`), { timeoutMs: 10000 }).catch(() => false);
        const openedFromMenu = await waitFor(async () => {
            const snapshot = await runAppCommand('kigumi.testGetSessionSnapshot', { filePath: FRAME });
            return snapshot && snapshot.exists ? snapshot : null;
        }, { timeoutMs: 60000 }).catch(() => null);
        check('right-click > Open in Viewer on a frame in All files opens it', choseOpen && openedFromMenu && connection().tabs.tabs.length === 1);
        await inExplorer(`row('files-root')?.querySelector('.ks-twistie')?.click(); return true;`);

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

        // Every panel over the view collapses from its header, and comes back.
        const viewDoc = 'document.querySelector("#slot-center iframe:not([hidden])").contentDocument';
        const overlayState = () => inShell(`(() => {
            const doc = ${viewDoc};
            return {
                selection: !doc.querySelector('#info-panel .ip-body'),
                layers: doc.querySelector('#layers-view .lp-panel').classList.contains('lp-collapsed'),
                camera: doc.getElementById('gizmo-panel').classList.contains('is-collapsed'),
            };
        })()`);
        const clickHeaders = () => inShell(`(() => {
            const doc = ${viewDoc};
            for (const selector of ['#info-panel .ov-header', '#layers-view .ov-header', '#gizmo-panel .ov-header']) {
                doc.querySelector(selector).click();
            }
        })()`);
        const before = await overlayState();
        await clickHeaders();
        await sleep(200);
        const toggled = await overlayState();
        await capture('02b-collapsed');
        await clickHeaders();
        await sleep(200);
        const restored = await overlayState();
        await capture('02c-expanded');
        const cubeWidth = await waitFor(() => inShell(`${viewDoc}.getElementById('gizmo-cube-c').width`), { timeoutMs: 5000 });
        check('the selection, layers and camera panels collapse from their headers and come back',
            ['selection', 'layers', 'camera'].every((name) => toggled[name] !== before[name] && restored[name] === before[name])
                && cubeWidth > 50,
            `${JSON.stringify(before)} -> ${JSON.stringify(toggled)}, cube ${cubeWidth}px`);

        // A right click on a row of the layers tree offers to copy it for an assistant, not the
        // browser's cut/copy/paste.
        const { clipboard } = require('electron');
        clipboard.writeText('');
        const menuItems = await inShell(`(async () => {
            const doc = ${viewDoc};
            doc.querySelector('#layers-view .ov-header').click();
            await new Promise((resolve) => setTimeout(resolve, 100));
            const row = doc.querySelector('#layers-view .lp-row-timber');
            const box = row.getBoundingClientRect();
            row.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: box.left + 5, clientY: box.top + 5 }));
            await new Promise((resolve) => setTimeout(resolve, 100));
            return Array.from(doc.querySelectorAll('#member-context-menu .context-menu-item')).map((item) => item.textContent.trim());
        })()`);
        await inShell(`(() => {
            const doc = ${viewDoc};
            const copy = Array.from(doc.querySelectorAll('#member-context-menu .context-menu-item'))
                .find((item) => item.textContent.trim() === 'copy for ai');
            if (copy) copy.click();
            doc.querySelector('#layers-view .ov-header').click();
        })()`);
        const copied = await waitFor(() => clipboard.readText() || null, { timeoutMs: 5000 }).catch(() => '');
        check('a right click on a timber in the layers tree copies its name for an assistant',
            menuItems.includes('copy for ai') && menuItems.includes('copy with details for ai')
                && copied.startsWith('patterns/structures/my_cute_frame.py \u203a '),
            `${menuItems.join(' | ')} -> ${JSON.stringify(copied)}`);

        // The inspector under the tabs shows the view's members; a click there selects in the view,
        // and the selection comes back to the inspector.
        const inspectorDoc = 'document.querySelector("#slot-bottom iframe")?.contentDocument';
        const memberRows = await waitFor(() => inShell(`${inspectorDoc}?.querySelectorAll("#member-rows tr").length || 0`), { timeoutMs: 15000 })
            .catch(() => 0);
        check('the inspector lists the members of the view', memberRows > 0, `${memberRows} members`);
        check('the view leaves its member list to the inspector', await inShell(`(() => {
            const frame = document.querySelector('#slot-center iframe:not([hidden])');
            const panels = frame && frame.contentDocument.getElementById('panels');
            return !!panels && frame.contentWindow.getComputedStyle(panels).display === 'none';
        })()`));
        await inShell(`${inspectorDoc}.querySelector("#member-rows tr").click()`);
        const selectedRows = await waitFor(() => inShell(`${inspectorDoc}?.querySelectorAll("#member-rows tr.is-selected").length || 0`), { timeoutMs: 5000 })
            .catch(() => 0);
        const viewSelection = (await panels().describe(`viewer:${FRAME}`)).selection;
        check('a click in the inspector selects in the view, and shows it',
            selectedRows === 1 && viewSelection && viewSelection.members.length === 1,
            `${selectedRows} row, ${viewSelection && viewSelection.members.length} selected in the view`);
        await capture('03b-inspector');

        // The options are drawn in the inspector against a stand-in for the view: a change there
        // reaches the view, and its answer comes back.
        const lengthOfFirstRow = () => inShell(`${inspectorDoc}.querySelector("#member-rows tr").children[4].textContent`);
        const metricLength = await lengthOfFirstRow();
        await inShell(`(() => {
            ${inspectorDoc}.querySelector('.inspector-tab[data-tab="options"]').click();
            const units = ${inspectorDoc}.getElementById('units-select');
            units.value = 'imperial';
            units.dispatchEvent(new Event('change', { bubbles: true }));
        })()`);
        const imperialLength = await waitFor(async () => {
            const length = await lengthOfFirstRow();
            return length !== metricLength ? length : null;
        }, { timeoutMs: 5000 }).catch(() => null);
        check('an option changed in the inspector changes the view',
            imperialLength !== null && await inShell(`${inspectorDoc}.getElementById('units-select').value`) === 'imperial',
            `${metricLength} -> ${imperialLength}`);
        await capture('03c-options');
        await inShell(`(() => {
            const units = ${inspectorDoc}.getElementById('units-select');
            units.value = 'metric';
            units.dispatchEvent(new Event('change', { bubbles: true }));
        })()`);
        await waitFor(async () => (await lengthOfFirstRow()) === metricLength, { timeoutMs: 5000 }).catch(() => null);
        check('the view leaves its options to the inspector', await inShell(`(() => {
            const frame = document.querySelector('#slot-center iframe:not([hidden])');
            const controls = frame && frame.contentDocument.getElementById('top-controls');
            return !!controls && frame.contentWindow.getComputedStyle(controls).display === 'none';
        })()`));

        // A drawing's dotted lines, clipped per timber by the member id pass: drawn, and every shader
        // they need compiled. Nothing else here enters a drawing, so nothing else draws them.
        // Drawings are behind a beta setting, read when a viewer opens.
        fs.writeFileSync(settings.filePath, JSON.stringify(
            { ...JSON.parse(fs.readFileSync(settings.filePath, 'utf8')), 'viewer.drawingBeta': true }, null, 2));
        await waitFor(() => settings.get('viewer.drawingBeta') === true, { timeoutMs: 5000 });
        await runAppCommand('kigumi.openFrameFromSidebar', DRAWING_FRAME);
        const viewerApp = 'document.querySelector("#slot-center iframe:not([hidden])").contentDocument.querySelector("kigumi-app")';
        const drawingId = await waitFor(() => inShell(`(() => {
            const app = ${viewerApp};
            const drawings = app && app.sceneStore ? app.sceneStore.drawings() : [];
            return drawings.length && Array.from(app.sceneManager.bundles()).length ? drawings[drawings.length - 1].id : null;
        })()`), { timeoutMs: 90000 }).catch(() => null);
        let entered = null;
        const drawn = drawingId && await (async () => {
            entered = await inShell(`(() => { try { ${viewerApp}.enterDrawing(${JSON.stringify(drawingId)}); return 'ok'; }
                catch (error) { return String(error && error.stack || error); } })()`);
            return waitFor(() => inShell(`(() => {
                const app = ${viewerApp};
                const lines = Array.from(app.sceneManager.bundles()).flatMap((bundle) => bundle.drawingLines || []);
                const shown = lines.filter((line) => line.object.visible).length;
                const programs = app.renderer.info.programs || [];
                const broken = programs.filter((program) => program.diagnostics && !program.diagnostics.runnable).length;
                return shown > 0 ? { shown, lines: lines.length, broken, glError: app.renderer.getContext().getError() } : null;
            })()`), { timeoutMs: 30000 });
        })().catch(() => null);
        const state = drawn ? null : await inShell(`(() => {
            const frames = [...document.querySelectorAll('#slot-center iframe')].map((f) => (f.hidden ? 'hidden' : 'shown')
                + ':' + (f.contentDocument && f.contentDocument.querySelector('kigumi-app') ? 'app' : 'no app'));
            const app = ${viewerApp};
            const lines = app ? Array.from(app.sceneManager.bundles()).flatMap((bundle) => bundle.drawingLines || []) : [];
            const meshes = app ? Array.from(app.sceneManager.bundles()).map((bundle) => [
                (bundle.drawingLines || []).length, !!bundle.idMesh]) : [];
            return JSON.stringify({ entered: ${'${JSON.stringify(entered)}'}, inDrawing: app && app.isInDrawing,
                active: app && app.sceneStore.activeScene().id, lines: lines.length, meshes,
                frames, scenes: app && app.sceneStore ? app.sceneStore.sceneIds() : null,
                drawings: app && app.sceneStore ? app.sceneStore.drawings().length : null,
                members: app && app.sceneManager ? Array.from(app.sceneManager.bundles()).length : null,
                title: app && app.frameName });
        })()`).catch((error) => String(error));
        check('a drawing draws its dotted lines, clipped per timber, with every shader compiled',
            !!drawn && drawn.broken === 0 && drawn.glError === 0,
            drawn ? `${drawn.shown} of ${drawn.lines} lines shown, ${drawn.broken} broken programs, GL error ${drawn.glError}`
                : `drawing ${drawingId}; ${state}`);
        await capture('03c-drawing-dotted-lines');
        connection().activePanel.dispose();

        // A frame's parameters: typed in the inspector, held by the view, shown back.
        await runAppCommand('kigumi.openFrameFromSidebar', PARAMETER_FRAME);
        await inShell(`${inspectorDoc}.querySelector('.inspector-tab[data-tab="parameters"]').click()`);
        const parameterRows = await waitFor(() => inShell(`${inspectorDoc}?.querySelectorAll(".kiwari-row").length || 0`), { timeoutMs: 60000 })
            .catch(() => 0);
        await inShell(`(() => {
            const box = ${inspectorDoc}.querySelector('input.kiwari-box[type="text"]');
            box.value = '7';
            box.dispatchEvent(new Event('input', { bubbles: true }));
        })()`);
        const parameterEdits = await waitFor(() => inShell(`${inspectorDoc}.querySelectorAll(".kiwari-row-changed, .kiwari-problem").length`), { timeoutMs: 5000 })
            .catch(() => 0);
        check('the inspector shows a frame\'s parameters, and an edit there reaches the view',
            parameterRows > 0 && parameterEdits > 0, `${parameterRows} parameters`);
        await capture('03d-parameters');
        connection().activePanel.dispose();
        await inShell(`${inspectorDoc}.querySelector('.inspector-tab[data-tab="members"]').click()`);

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
        check('closing a tab activates a neighbour', connection().tabs.tabs.length === 2 && connection().activePanel !== null);

        // Test Monaco editor panel opening
        await runAppCommand('kigumi.viewPatternSource', { data: { sourceFile: FRAME } });
        const editorPanel = await waitFor(() => {
            const active = connection().activePanel;
            return active && active.type === 'editor' ? active : null;
        });
        check('viewPatternSource opens a file in the Monaco editor panel', !!editorPanel && editorPanel.filePath === FRAME);
        const inspectedTitle = await inShell('document.querySelector("#slot-bottom iframe")?.contentDocument?.getElementById("view-title").textContent');
        check('with a source file in front, the inspector keeps showing the last view', inspectedTitle === tabs[1], inspectedTitle);
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
