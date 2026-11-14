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

        const kinds = await inShell(`(() => {
            const doc = ${viewDoc}, app = doc.querySelector('kigumi-app');
            const key = Array.from(app.sceneManager.keys())[0];
            const metadata = app.memberMetadataByKey.get(key);
            const originalClass = metadata.mesh.timberClass;
            const titles = {};
            try {
                for (const kind of ['Timber', 'Board', 'RoundTimber', 'RegularPolygonTimber', 'MeshTimber', 'STLTimber']) {
                    metadata.mesh.timberClass = kind;
                    app.selectMembers([key], false);
                    app.selectionPanel.updateInfo(app.currentFrameData);
                    titles[kind] = doc.querySelector('#info-panel .ip-breadcrumb').textContent;
                }
            } finally {
                metadata.mesh.timberClass = originalClass;
                app.selectMembers([], false);
            }
            return { titles, name: metadata.name };
        })()`);
        for (const [kind, suffix] of Object.entries({Timber:'', Board:'', RoundTimber:' (round)', RegularPolygonTimber:' (polygon)', MeshTimber:' (mesh)', STLTimber:' (mesh)'})) {
            check('selection title labels ' + kind, kinds.titles[kind] === 'Selected: ' + kinds.name + suffix, kinds.titles[kind]);
        }
        check('assembly preview has one beta option and no separate timeline toggle', await inShell(`(() => {
            const doc = ${viewDoc};
            return !!doc.querySelector('#beta-assembly-toggle') && !doc.querySelector('#assembly-timeline-toggle');
        })()`));

        // A right click on a timber in the view: focus on it, the features lit under the pointer, export it.
        const rightClick = await inShell(`(async () => {
            const doc = ${viewDoc};
            const app = doc.querySelector('kigumi-app');
            const canvas = app.renderRoot.querySelector('#c');
            const box = canvas.getBoundingClientRect();
            let at = null;
            for (let fy = 0.3; fy <= 0.7 && !at; fy += 0.05) {
                for (let fx = 0.3; fx <= 0.7 && !at; fx += 0.05) {
                    const x = box.left + box.width * fx, y = box.top + box.height * fy;
                    const hit = app._findMemberAtClientPoint(x, y);
                    if (hit) at = { x, y, key: hit.memberKey };
                }
            }
            if (!at) return { error: 'no timber under the canvas middle' };
            // Features light on a timber that is selected, as a first click selects it.
            app.selectMembers([at.key], false);
            await new Promise((resolve) => setTimeout(resolve, 100));
            const pointer = { bubbles: true, clientX: at.x, clientY: at.y };
            canvas.dispatchEvent(new doc.defaultView.PointerEvent('pointermove', pointer));
            for (let i = 0; i < 40 && !(app._hover && app._hover.drawn); i += 1) {
                await new Promise((resolve) => setTimeout(resolve, 100));
            }
            canvas.dispatchEvent(new doc.defaultView.MouseEvent('mousedown', { ...pointer, button: 2 }));
            doc.defaultView.dispatchEvent(new doc.defaultView.MouseEvent('mouseup', { ...pointer, button: 2 }));
            await new Promise((resolve) => setTimeout(resolve, 200));
            const menu = doc.querySelector('#member-context-menu');
            return {
                rows: menu ? Array.from(menu.children).map((row) => row.className.includes('divider') ? '---'
                    : (row.className.includes('heading') ? '# ' : '') + row.textContent.trim()) : [],
            };
        })()`);
        await capture('02e-timber-menu');
        const rows = rightClick.rows || [];
        const exportAt = rows.findIndex((row) => row.startsWith('# export '));
        await inShell(`${viewDoc}.querySelector('kigumi-app').selectMembers([], false)`);
        check('a right click on a timber offers to focus on it, the features under the pointer, then export',
            /^focus camera on \S/.test(rows[0] || '') && rows[1] === '---' && rows[2] && rows[2].startsWith('# features here')
                && rows[exportAt - 1] === '---' && rows[exportAt + 1] === 'stl' && rows[exportAt + 2] === 'step'
                && !rows.includes('copy for ai'),
            JSON.stringify(rightClick));
        const focused = await inShell(`(async () => {
            const app = ${viewDoc}.querySelector('kigumi-app');
            const before = app.cameraController.orbitDist;
            const row = ${viewDoc}.querySelector('#member-context-menu .context-menu-item');
            if (row) row.click();
            await new Promise((resolve) => setTimeout(resolve, 600));
            return { before, after: app.cameraController.orbitDist, open: Boolean(${viewDoc}.querySelector('#member-context-menu')) };
        })()`);
        check('choosing "focus camera on" frames that timber and closes the menu',
            focused.after < focused.before && !focused.open, JSON.stringify(focused));

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
