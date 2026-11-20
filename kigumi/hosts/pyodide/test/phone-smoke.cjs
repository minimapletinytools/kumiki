/**
 * Kigumi in a browser on a phone, end to end (webview/shell/phone-layout.js): a phone-sized window
 * at ?layout=phone. The projects page, a new project's frames as the menu, the starter frame filling
 * the screen with its menu at the top left, a pattern opened read-only with Back to the frame, the
 * agent's sheet opening and folding, and closing the frame.
 *
 *   npm run build && env -u ELECTRON_RUN_AS_NODE ../../node_modules/.bin/electron test/phone-smoke.cjs
 */
const { app, BrowserWindow, session } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const HERE = path.join(__dirname, '..');
const ARTIFACTS = path.join(HERE, 'test-artifacts', 'phone');
const PORT = '8126';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const results = [];
function check(name, ok, detail = '') {
    results.push(Boolean(ok));
    console.log(`${ok ? 'PASS' : 'FAIL'} [phone] ${name}${detail ? ` -- ${detail}` : ''}`);
}

app.whenReady().then(async () => {
    const server = spawn('node', [path.join(HERE, 'serve.mjs')], { env: { ...process.env, PORT }, stdio: 'ignore' });
    await sleep(800);
    fs.mkdirSync(ARTIFACTS, { recursive: true });
    const window = new BrowserWindow({ width: 390, height: 844, show: false, useContentSize: true,
        webPreferences: { backgroundThrottling: false } });
    const errors = [];
    window.webContents.on('console-message', (event) => {
        const text = String(event.message || '');
        if (/kigumi-backend.*blocked by CORS|kigumi-backend.*net::ERR_FAILED/.test(text)) return;
        if (event.level === 'error' || /Uncaught/.test(text)) errors.push(text);
    });
    const js = (code) => window.webContents.executeJavaScript(code);
    async function wait(code, timeoutMs = 60000) {
        const deadline = Date.now() + timeoutMs;
        for (;;) {
            const result = await js(code).catch(() => null);
            if (result) return result;
            if (Date.now() > deadline) return null;
            await sleep(300);
        }
    }
    const shot = async (name) => fs.writeFileSync(path.join(ARTIFACTS, `${name}.png`), (await window.webContents.capturePage()).toPNG());
    const menu = 'document.querySelector(".phone-menu iframe")?.contentDocument';
    const view = 'document.querySelector(".phone-main iframe:not([hidden])")?.contentDocument';
    const agent = 'document.querySelector(".phone-agent iframe")?.contentDocument';
    const shown = (selector, doc = 'document') => `(() => { const e = ${doc}?.querySelector(${JSON.stringify(selector)});
        return !!e && !e.hidden && e.getClientRects().length > 0; })()`;
    try {
        await session.defaultSession.clearStorageData();
        await window.loadURL(`http://127.0.0.1:${PORT}/?layout=phone`);
        window.showInactive();
        check('Python, kumiki and Kigumi start in the page', await wait("document.body.classList.contains('kigumi-ready')", 240000) === true);
        check('the page is laid out for a phone', await js("document.body.dataset.layout") === 'phone');
        const projects = await wait(`${shown('.web-new-project')} && !${shown('.shell')}`, 30000);
        await shot('1-projects');
        check('with no project open, the projects page fills the screen', projects === true);
        check("the projects page doesn't point to an agent on the right", !await js(shown('#web-agent-hint')));

        await js(`(() => {
            document.querySelector('.web-new-project input').value = 'Shed';
            document.querySelector('.web-new-project button').click();
        })()`);
        const starter = await wait(`[...(${menu}?.querySelectorAll('.ks-phone-list button') || [])]
            .find((one) => one.textContent.includes('cute'))?.textContent.trim()`, 120000);
        const home = await js(`document.querySelector('.phone').classList.contains('is-home')`);
        await shot('2-home');
        check('a new project shows its frames as the menu, with no file open', Boolean(starter) && home, starter);
        check('the agent is a sheet along the bottom, folded to its text box',
            await wait(`${agent}?.body.classList.contains('is-phone') && !${agent}.body.classList.contains('is-sheet-open') || null`, 30000) === true);

        // New frame starts a prompt to the agent, in its opened sheet, for the user to finish.
        await js(`${menu}.querySelector('.ks-phone-list [data-key="new-frame"]').click()`);
        const drafted = await wait(`document.querySelector('.phone').classList.contains('is-agent-expanded')
            && ${agent}.getElementById('prompt-input').value || null`, 5000);
        await shot('2b-new-frame');
        check('New frame opens the agent with a prompt to finish', drafted === 'Please make a new design: ', drafted);
        await js(`(() => { const doc = ${agent}; doc.getElementById('prompt-input').value = ''; document.querySelector('.phone-backdrop').click(); })()`);
        await wait(`!document.querySelector('.phone').classList.contains('is-agent-expanded') || null`, 5000);

        await js(`[...${menu}.querySelectorAll('.ks-phone-list button')].find((one) => one.textContent.includes('cute')).click()`);
        const drawn = await wait(`${view}?.querySelector('canvas')?.width > 100 && ${view}.querySelector('#compact-menu-btn')?.textContent.trim() || null`, 240000);
        await sleep(1500);
        await shot('3-frame');
        const chrome = await js(`({ sidebar: ${shown('#view-sidebar', view)}, menuHidden: !${shown('.phone-menu')},
            back: ${shown('.phone-back')}, menuButton: ${shown('.phone-menu-button')} })`);
        check('the frame fills the screen with its menu at the top left, and no sidebar', Boolean(drawn) && !chrome.sidebar
            && chrome.menuHidden && !chrome.back && chrome.menuButton, `${drawn} ${JSON.stringify(chrome)}`);

        const debuggerApi = window.webContents.debugger;
        debuggerApi.attach('1.3');
        const screenSize = (width, height) => debuggerApi.sendCommand('Emulation.setDeviceMetricsOverride',
            { width, height, deviceScaleFactor: 1, mobile: true });
        await screenSize(390, 844);
        await debuggerApi.sendCommand('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
        const orbitDistance = `${view}.querySelector('kigumi-app').cameraController.orbitDist`;
        const beforePinch = await js(orbitDistance);
        await debuggerApi.sendCommand('Input.synthesizePinchGesture', {
            x: 170, y: 310, scaleFactor: 1.5, gestureSourceType: 'touch',
        });
        check('pinching the model zooms the camera at normal page scale', await wait(
            `window.visualViewport.scale === 1 && ${orbitDistance} < ${beforePinch} || null`, 5000) === true);
        await debuggerApi.sendCommand('Emulation.setPageScaleFactor', { pageScaleFactor: 2 });
        check('a magnified page takes gestures over the model', await wait(
            `window.visualViewport.scale > 1 && ${view}.defaultView.getComputedStyle(${view}.querySelector('#c')).pointerEvents === 'none' || null`, 5000) === true);
        // Back to normal size (a synthesized pinch out is too slow and inexact to rely on in CI).
        await debuggerApi.sendCommand('Emulation.setPageScaleFactor', { pageScaleFactor: 1 });
        check('the model takes gestures again at normal page scale', await wait(
            `window.visualViewport.scale === 1 && ${view}.defaultView.getComputedStyle(${view}.querySelector('#c')).pointerEvents !== 'none' || null`, 5000) === true);

        await js(`${view}.querySelector('#compact-menu-btn').click()`);
        const items = await wait(`[...(${view}?.querySelectorAll('#compact-menu .compact-menu-item') || [])].map((one) => one.dataset.item).join() || null`, 5000);
        await shot('4-frame-menu');
        await js(`${view}.querySelector('.compact-menu-item[data-item="options"]').click()`);
        const sheet = await wait(`${shown('#view-sidebar', view)} && ${shown('#compact-sheet-close', view)} || null`, 5000);
        await shot('5-options');
        await js(`${view}.querySelector('#compact-sheet-close').click()`);
        check("the frame's menu opens its options as a sheet, which closes", Boolean(items && items.includes('options')) && sheet === true
            && await wait(`!${shown('#view-sidebar', view)} || null`, 5000) === true, items);

        const dismissed = await js(`(async () => {
            const app = ${view}.querySelector('kigumi-app');
            app.setViewPhase('error', 'Sample build error', { error: 'Sample build error' });
            await app.updateComplete;
            app.querySelector('.error-actions [aria-label]').click();
            await app.updateComplete;
            const hidden = !app.querySelector('#loading-overlay').classList.contains('visible');
            app.setViewPhase('ready');
            return hidden;
        })()`);
        check('a viewer error can be dismissed on the phone', dismissed);
        await js(`window.kigumiShell.send({ type: 'shell:command', command: 'run', args: ['kigumi.openFrameFromSidebar'] })`);
        const toast = await wait(`document.querySelector('.phone-status:not([hidden])')?.textContent || null`, 3000);
        check('a shell error clears after a few seconds', Boolean(toast) && await wait(
            `document.querySelector('.phone-status').hidden || null`, 10000) === true);

        // Selecting a timber names it in a chip at the top; a tap on the chip frames it.
        const chip = await js(`(async () => {
            const app = ${view}.querySelector('kigumi-app');
            const key = [...app.memberMetadataByKey.keys()][0];
            app.selectionManager.selectTimber(key);
            await app.updateComplete;
            const shownChip = ${view}.querySelector('#compact-selection-chip');
            const text = shownChip && shownChip.textContent.trim();
            app.selectionManager.clearTimberSelection();
            await app.updateComplete;
            return { text, name: app.memberMetadataByKey.get(key).name, gone: !${view}.querySelector('#compact-selection-chip') };
        })()`);
        check('a selected timber is named in a chip at the top, gone once deselected', chip.text === chip.name && chip.gone, JSON.stringify(chip));

        // Two fingers dragged together pan: the center moves, the camera doesn't turn or zoom.
        const pan = await js(`(async () => {
            const app = ${view}.querySelector('kigumi-app');
            const canvas = app.renderRoot.querySelector('#c');
            const win = canvas.ownerDocument.defaultView;
            const c = app.cameraController;
            const before = { center: [c.cx, c.cy, c.cz], dist: c.orbitDist, dir: [c.cameraOffsetDir.x, c.cameraOffsetDir.y, c.cameraOffsetDir.z] };
            const rect = canvas.getBoundingClientRect();
            const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
            const fire = (type, id, px, py) => canvas.dispatchEvent(new win.PointerEvent(type,
                { pointerId: id, pointerType: 'touch', clientX: px, clientY: py, bubbles: true, cancelable: true, isPrimary: id === 11 }));
            fire('pointerdown', 11, x - 40, y);
            fire('pointerdown', 12, x + 40, y);
            for (let step = 1; step <= 10; step++) {
                fire('pointermove', 11, x - 40 + step * 8, y + step * 4);
                fire('pointermove', 12, x + 40 + step * 8, y + step * 4);
            }
            fire('pointerup', 11, x + 40, y + 40);
            fire('pointerup', 12, x + 120, y + 40);
            await new Promise((resolve) => setTimeout(resolve, 100));
            const after = { center: [c.cx, c.cy, c.cz], dist: c.orbitDist, dir: [c.cameraOffsetDir.x, c.cameraOffsetDir.y, c.cameraOffsetDir.z] };
            const moved = Math.hypot(...after.center.map((v, i) => v - before.center[i]));
            const turned = Math.hypot(...after.dir.map((v, i) => v - before.dir[i]));
            Object.assign(c, { cx: before.center[0], cy: before.center[1], cz: before.center[2], orbitDist: before.dist });
            app.updateCamera();
            return { moved, turned, zoom: after.dist / before.dist };
        })()`);
        check('two fingers dragged together pan the view', pan.moved > 0.01 && pan.turned < 1e-6 && Math.abs(pan.zoom - 1) < 0.01, JSON.stringify(pan));

        await js(`document.querySelector('.phone-menu-button').click()`);
        const opened = await wait(`document.querySelector('.phone').classList.contains('is-menu-open') || null`, 5000);
        await shot('6-project-menu');
        await js(`[...${menu}.querySelectorAll('.ks-phone-button')].find((one) => one.textContent.includes('Example Frames')).click()`);
        await js(`${menu}.querySelector('[data-key="library-frames:kumiki"]').click()`);
        check('one tap expands Kumiki and lists its example frames', await wait(
            `${menu}.querySelector('[data-key="library-frames:kumiki"]').ariaExpanded === 'true'
            && !!${menu}.querySelector('[data-key^="frame-file:library:"]') || null`, 5000) === true);
        await js(`${menu}.querySelector('.ks-phone-button.is-quiet').click()`);
        await js(`[...${menu}.querySelectorAll('.ks-phone-button')].find((one) => one.textContent.includes('Patterns')).click()`);
        // Open folders down to the first pattern, and open it.
        const pattern = await wait(`(() => {
            const doc = ${menu};
            const rows = [...doc.querySelectorAll('.ks-phone-list button')];
            const closed = rows.find((row) => row.getAttribute('aria-expanded') === 'false');
            const leaf = rows.find((row) => row.dataset.key.startsWith('pattern-item:'));
            if (leaf) {
                leaf.scrollIntoView({ block: 'center' });
                const box = leaf.getBoundingClientRect();
                const frame = doc.defaultView.frameElement.getBoundingClientRect();
                return { label: leaf.textContent.trim(), x: frame.x + box.x + box.width / 2, y: frame.y + box.y + box.height / 2 };
            }
            if (closed) closed.click();
            return null;
        })()`, 60000);
        await debuggerApi.sendCommand('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: pattern.x, y: pattern.y }] });
        await debuggerApi.sendCommand('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
        const readOnly = await wait(`${shown('.phone-back')} && !document.querySelector('.phone').classList.contains('is-menu-open') || null`, 240000);
        await sleep(1500);
        await shot('7-pattern');
        check('the project menu opens a pattern, closing itself, with Back to the frame', opened === true && Boolean(pattern) && readOnly === true, pattern.label);

        await js(`document.querySelector('.phone-menu-button').click()`);
        check('Back stays behind the open frame browser', !await js(shown('.phone-back')));
        await js(`document.querySelector('.phone-menu-button').click()`);
        await js(`document.querySelector('.phone-back').click()`);
        const backAgain = await wait(`!${shown('.phone-back')} && ${view}?.querySelector('#compact-menu-btn')?.textContent.includes('Cute') || null`, 240000);
        check('Back goes to the frame', backAgain === true, backAgain === true ? '' : JSON.stringify(await js(`(() => {
            const app = ${view}?.querySelector('kigumi-app');
            return { button: ${view}?.querySelector('#compact-menu-btn')?.textContent.trim(), data: app && app.currentFrameData,
                phase: app && app.viewState.phase, back: ${shown('.phone-back')} };
        })()`)));

        await js(`(() => { const input = ${agent}.getElementById('prompt-input');
            input.dispatchEvent(new input.ownerDocument.defaultView.PointerEvent('pointerdown', { bubbles: true })); input.focus(); })()`);
        const expanded = await wait(`document.querySelector('.phone').classList.contains('is-agent-expanded')
            && ${agent}.body.classList.contains('is-sheet-open') || null`, 5000);
        await sleep(400);
        await shot('8-agent');
        await js(`(() => {
            const doc = ${agent};
            doc.getElementById('prompt-input').value = 'Make a frame';
            ${agent}.getElementById('send-btn').click();
        })()`);
        check('a signed-out prompt keeps the draft and shows sign-in and MCP', await js(
            `${shown('#prompt-sign-in', agent)} && ${agent}.getElementById('prompt-sign-in').textContent.includes('MCP')
            && ${agent}.getElementById('prompt-input').value === 'Make a frame'`));
        await js(`document.querySelector('.phone-backdrop').click()`);
        const folded = await wait(`!document.querySelector('.phone').classList.contains('is-agent-expanded') || null`, 5000);
        check('tapping the text box opens the agent sheet, and a tap above folds it', expanded === true && folded === true);

        await js(`document.querySelector('.phone-menu-button').click()`);
        await wait(`document.querySelector('.phone').classList.contains('is-menu-open') || null`, 5000);
        await js(`document.querySelector('.phone-close-file').click()`);
        check('Close this frame goes back to the frames', await wait(`document.querySelector('.phone').classList.contains('is-home') || null`, 10000) === true);
        await shot('9-closed');

        // Turned sideways: still laid out, the frame's view as wide as the screen.
        window.setContentSize(844, 390);
        await screenSize(844, 390);
        await sleep(800);
        await shot('10-landscape');

        check('no errors in the page', errors.length === 0, errors.slice(0, 3).join(' | '));
    } catch (error) {
        check('the run finishes', false, error.stack || String(error));
    } finally {
        server.kill();
        const passed = results.filter(Boolean).length;
        console.log(`${passed} passed, ${results.length - passed} failed`);
        app.exit(results.every(Boolean) ? 0 : 1);
    }
});
