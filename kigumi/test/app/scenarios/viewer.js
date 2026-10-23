// A frame in a viewer tab: drawn, screenshotted, described to an agent; its panels collapse and come
// back; a timber in the layers tree is copied for an assistant.

const path = require('path');

module.exports = {
    name: 'viewer',
    async run({ check, inShell, waitFor, sleep, capture, runAppCommand, connection, panels, openFrame, viewDoc, clipboard, REPO, FRAME, ARTIFACTS }) {
        const drew = await openFrame(FRAME);
        const session = await runAppCommand('kigumi.testGetSessionSnapshot', { filePath: FRAME });
        check('a frame opens in a viewer tab', session && session.exists && connection().tabs.tabs.length === 1, session && session.panelTitle);
        check('the viewer panel draws into a canvas', drew);
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
        clipboard.writeText('');
        const menuItems = await inShell(`(async () => {
            const doc = ${viewDoc};
            if (doc.querySelector('#layers-view .lp-panel').classList.contains('lp-collapsed')) {
                doc.querySelector('#layers-view .ov-header').click();
            }
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
        })()`);
        const copied = await waitFor(() => clipboard.readText() || null, { timeoutMs: 5000 }).catch(() => '');
        check('a right click on a timber in the layers tree copies its name for an assistant',
            menuItems.includes('copy for ai') && menuItems.includes('copy with details for ai')
                && copied.startsWith('patterns/structures/my_cute_frame.py › '),
            `${menuItems.join(' | ')} -> ${JSON.stringify(copied)}`);
    },
};
