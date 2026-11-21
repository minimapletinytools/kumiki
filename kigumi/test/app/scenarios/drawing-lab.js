// Experiment harness, not a test: renders each drawing of the frames in KIGUMI_LAB_FRAMES
// (comma-separated, relative to the repo) to PNG in KIGUMI_LAB_OUT, through the viewer's own export.

const fs = require('fs');
const path = require('path');

module.exports = {
    name: 'drawing-lab',
    async run({ check, inShell, waitFor, runAppCommand, viewDoc, REPO, connection }) {
        const out = process.env.KIGUMI_LAB_OUT;
        const only = (process.env.KIGUMI_LAB_DRAWINGS || '').split(',').filter(Boolean);
        fs.mkdirSync(out, { recursive: true });
        connection().setSideShown('left', false);
        for (const relative of (process.env.KIGUMI_LAB_FRAMES || '').split(',').filter(Boolean)) {
            const file = path.join(REPO, relative);
            await runAppCommand('kigumi.openFrameFromSidebar', file);
            const app = `${viewDoc}.querySelector("kigumi-app")`;
            const drawings = await waitFor(() => inShell(`(() => {
                const app = ${app};
                if (!app || !app.sceneStore || !Array.from(app.sceneManager.bundles()).length) return null;
                const list = app.sceneStore.drawings().filter((one) => one.id !== 'three-d-measurements');
                return list.length ? list.map((one) => ({ id: one.id, name: one.name || one.id })) : null;
            })()`), { timeoutMs: 300000 }).catch(() => []);
            check(`${relative}: ${drawings.length} drawings`, drawings.length > 0, drawings.map((one) => one.name).join(' | '));
            for (const drawing of drawings) {
                if (only.length && !only.some((name) => drawing.name.includes(name))) continue;
                await inShell(`${app}.enterDrawing(${JSON.stringify(drawing.id)})`);
                await new Promise((resolve) => setTimeout(resolve, 2500));
                const dataUrl = await inShell(`${app}.renderDrawingPng()`).catch((error) => String(error));
                const name = `${path.basename(relative, '.py')}--${drawing.name.replace(/[^\w.-]+/g, '_')}.png`;
                const match = /^data:image\/png;base64,(.+)$/.exec(dataUrl || '');
                if (match) fs.writeFileSync(path.join(out, name), Buffer.from(match[1], 'base64'));
                check(`rendered ${name}`, Boolean(match), match ? '' : String(dataUrl).slice(0, 200));
                await inShell(`${app}.leaveDrawing()`);
            }
        }
    },
};
