/** Check the HTTP app in Chromium while the web host is running. */
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');
const KIGUMI = path.resolve(__dirname, '../..');
const FRAME = path.join(KIGUMI, 'test-fixtures/minimal_frame.py');
const ARTIFACTS = path.join(KIGUMI, '.artifacts/web');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
app.whenReady().then(async () => {
    const window = new BrowserWindow({ width: 1440, height: 1000, show: false, webPreferences: { backgroundThrottling: false } });
    const violations = [];
    window.webContents.on('console-message', (_event, ...args) => {
        if (args.some((arg) => String(arg).includes('violates the following Content Security Policy'))) violations.push(args);
    });
    const js = (code) => window.webContents.executeJavaScript(code);
    async function wait(code) {
        for (let i = 0; i < 120; i++) {
            const result = await js(code);
            if (result) return result;
            await sleep(500);
        }
        throw new Error('Timed out: ' + code);
    }
    try {
        await window.loadURL('http://127.0.0.1:7346');
        window.showInactive();
        await wait('document.querySelector("#slot-left iframe")?.contentDocument?.querySelectorAll(".ks-row").length');
        console.log('Explorer rendered');
        await js(`window.kigumiShell.send({ type: 'shell:command', command: 'run', args: ['kigumi.openFrameFromSidebar', ${JSON.stringify(FRAME)}] })`);
        const doc = 'document.querySelector("#slot-center iframe")?.contentDocument';
        const view = `${doc}?.querySelector('kigumi-app')`;
        const frame = await wait(`${view}?.currentFrameData?.name`);
        const members = await wait(`${doc}?.querySelectorAll('.lp-row-timber').length`);
        const canvas = await wait(`${doc}?.querySelector('canvas')?.width`);
        console.log(JSON.stringify({ frame, members, canvas }));
        if (frame !== 'Runner Test Frame' || members !== 2 || canvas < 100) throw new Error('Unexpected fixture rendering');
        fs.mkdirSync(ARTIFACTS, { recursive: true });
        fs.writeFileSync(path.join(ARTIFACTS, 'browser.png'), (await window.webContents.capturePage()).toPNG());
        await window.reload();
        await sleep(1000);
        console.log('Reload frame:', await wait(`${view}?.currentFrameData?.name`));
        if (violations.length) throw new Error(`CSP violations: ${JSON.stringify(violations)}`);
        console.log('WEB SMOKE PASSED');
        app.exit(0);
    } catch (error) {
        console.error(error);
        console.log(await js('document.body.innerText'));
        app.exit(1);
    }
});
