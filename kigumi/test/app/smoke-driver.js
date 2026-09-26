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

module.exports = async function smoke({ runAppCommand, shell, logLines, onShellCommand }) {
    const results = [];
    const check = (name, ok, detail) => {
        results.push({ name, ok: !!ok, detail });
        console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` -- ${detail}` : ''}`);
    };
    async function capture(name, contents) {
        if (!ARTIFACTS) return;
        fs.mkdirSync(ARTIFACTS, { recursive: true });
        const image = await contents.capturePage();
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
        await sleep(500);
        await capture('01-shell', shell().window.webContents);
        await capture('01-sidebar', shell().sidebar.view.webContents);

        await runAppCommand('kigumi.openFrameFromSidebar', FRAME);
        const session = await runAppCommand('kigumi.testGetSessionSnapshot', { filePath: FRAME });
        check('a frame opens in a viewer tab', session && session.exists && shell().tabs.tabs.length === 1, session && session.panelTitle);
        await sleep(1000);
        await capture('02-viewer', shell().activeSurface.view.webContents);
        await capture('02-shell', shell().window.webContents);

        const shotPath = ARTIFACTS ? path.join(ARTIFACTS, '03-screenshot-command.png') : path.join(REPO, '.kigumi', 'automation', 'app-smoke.png');
        const shot = await runAppCommand('kigumi.captureScreenshot', { filePath: FRAME, outputPath: shotPath, timeoutMs: 15000 });
        check('the viewer answers a screenshot round trip', shot && shot.ok && shot.screenshot.byteLength > 1000,
            shot && shot.screenshot && `${shot.screenshot.width}x${shot.screenshot.height}`);

        console.log('... browsing patterns');
        const picking = runAppCommand('kigumi.browsePatterns');
        const overlay = shell().overlay.webContents;
        await waitFor(() => shell().pendingPick !== null, { timeoutMs: 30000 });
        console.log('... quick pick requested');
        await waitFor(async () => !overlay.isLoading() && overlay.getURL()
            && overlay.executeJavaScript('document.querySelectorAll(".item").length'), { timeoutMs: 30000 });
        console.log('... quick pick shown');
        await capture('04-quickpick', overlay);
        const labels = await overlay.executeJavaScript('Array.from(document.querySelectorAll(".item-label")).map((e) => e.textContent)');
        const wanted = labels[Math.min(1, labels.length - 1)];
        await overlay.executeJavaScript(`
            const filter = document.getElementById('filter');
            filter.value = ${JSON.stringify(wanted)};
            filter.dispatchEvent(new Event('input'));
        `);
        const filtered = await overlay.executeJavaScript('Array.from(document.querySelectorAll(".item-label")).map((e) => e.textContent)');
        check('the quick pick filters by name', filtered.length > 0 && filtered.every((label) => label.includes(wanted)), `${wanted}: ${filtered.join(', ')}`);
        await overlay.executeJavaScript(`
            document.getElementById('filter').dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(filtered.length > 0 ? 'Enter' : 'Escape')} }));
        `);
        await picking;
        const tabs = shell().tabs.snapshot();
        check('the picked pattern opens in a second tab', tabs.tabs.length === 2 && tabs.tabs[1].title.includes(wanted), tabs.tabs.map((t) => t.title).join(' | '));
        await sleep(1000);
        await capture('05-pattern', shell().activeSurface.view.webContents);

        onShellCommand('openLog');
        await sleep(800);
        check('the Log tab opens', shell().activeSurface && shell().activeSurface.kind === 'log');
        await capture('06-log', shell().activeSurface.view.webContents);

        const active = shell().activeSurface;
        active.dispose();
        check('closing a tab activates a neighbour', shell().tabs.tabs.length === 2 && shell().tabs.activeId !== null);

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
