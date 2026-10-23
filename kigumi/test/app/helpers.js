/**
 * What the app's scenarios (scenarios/*.js) share: the files they open, waiting, the shell and view
 * pages to script, and the reset that puts the app back to a known layout before each one.
 */

const fs = require('fs');
const path = require('path');

const REPO = path.resolve(__dirname, '..', '..', '..');
const FRAME = path.join(REPO, 'patterns', 'structures', 'my_cute_frame.py');
const PARAMETER_FRAME = path.join(REPO, 'patterns', 'structures', 'dovetailed_sawhorse.py');
// A frame with drawings, in rough stock: its views draw dotted perfect faces and centerlines.
const DRAWING_FRAME = path.join(REPO, 'patterns', 'structures', 'my_cute_frame_drawing_test.py');
const ARTIFACTS = process.env.KIGUMI_TEST_ARTIFACTS || null;

// The settings a scenario may change, as every scenario starts with them.
const SETTINGS_AT_START = {
    'viewer.drawingBeta': false,
    'mcp.enabled': false,
    'viewer.autoRefreshOnFileChange': true,
};

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

/** The view in front, as script text for inShell. */
const viewDoc = 'document.querySelector("#slot-center iframe:not([hidden])").contentDocument';

/**
 * What a scenario is given: the app (from main.js's test hooks), checking, scripting the shell
 * page, the view's sidebar, and screenshots.
 */
function createContext(app, record) {
    const { window, connection, runAppCommand } = app;
    const inShell = (script) => window().webContents.executeJavaScript(script);
    const ctx = {
        ...app,
        REPO, FRAME, PARAMETER_FRAME, DRAWING_FRAME, ARTIFACTS,
        sleep, waitFor, viewDoc, inShell,
        check: record,
        clipboard: require('electron').clipboard,

        async capture(name) {
            if (!ARTIFACTS) return;
            fs.mkdirSync(ARTIFACTS, { recursive: true });
            const image = await window().webContents.capturePage();
            fs.writeFileSync(path.join(ARTIFACTS, `${name}.png`), image.toPNG());
        },

        /** Opens a frame in a viewer tab; returns whether it drew into a canvas within a minute. */
        async openFrame(filePath = FRAME) {
            await runAppCommand('kigumi.openFrameFromSidebar', filePath);
            return waitFor(() => inShell(`(() => {
                const frame = document.querySelector('#slot-center iframe:not([hidden])');
                return !!(frame && frame.contentDocument && frame.contentDocument.querySelector('canvas'));
            })()`), { timeoutMs: 60000 }).then(() => true, () => false);
        },

        showTab: (tab) => inShell(`${viewDoc}.querySelector('.vsb-tab[data-tab="${tab}"]').click()`),
        shownPage: () => inShell(`[...${viewDoc}.querySelectorAll('.vsb-page')].filter((page) => !page.hidden).map((page) => page.dataset.tab).join()`),

        /** Puts the app back as every scenario starts: no tabs, explorer shown, agent hidden, settings as at start. */
        async reset() {
            await inShell(`(() => {
                const pick = document.getElementById('quickpick');
                if (pick && !pick.hidden) {
                    document.getElementById('quickpick-filter').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
                }
            })()`).catch(() => null);
            for (const tab of [...connection().tabs.tabs]) {
                const panel = connection().panels.get(tab.id);
                if (panel) panel.dispose();
            }
            for (const [key, value] of Object.entries(SETTINGS_AT_START)) {
                if (app.settings.get(key) !== value) app.settings.set(key, value);
            }
            connection().setSideShown('left', true);
            connection().setSideShown('right', false);
            await waitFor(() => connection().tabs.tabs.length === 0, { timeoutMs: 10000 });
        },
    };
    return ctx;
}

module.exports = { createContext, REPO, FRAME, PARAMETER_FRAME, DRAWING_FRAME };
