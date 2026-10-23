// Drawings, a beta feature: turned on from the options' beta section (a setting the open views
// reload to read); then a drawing's dotted lines, clipped per timber by the member id pass, drawn
// with every shader they need compiled. Nothing else enters a drawing, so nothing else draws them.

module.exports = {
    name: 'drawings',
    async run({ check, inShell, waitFor, capture, settings, runAppCommand, openFrame, viewDoc, showTab, FRAME, DRAWING_FRAME }) {
        await openFrame(FRAME);
        await showTab('options');
        await inShell(`${viewDoc}.getElementById('beta-drawing-toggle').click()`);
        const betaSaved = await waitFor(() => settings.get('viewer.drawingBeta') === true, { timeoutMs: 5000 }).catch(() => false);
        const betaShown = await waitFor(() => inShell(`(() => {
            const app = document.querySelector("#slot-center iframe:not([hidden])")?.contentDocument?.querySelector("kigumi-app");
            return !!(app && app.drawingBetaEnabled);
        })()`), { timeoutMs: 20000 }).catch(() => false);
        check('turning drawings on in the beta section saves it, and the open view reloads with them', betaSaved && betaShown);

        await runAppCommand('kigumi.openFrameFromSidebar', DRAWING_FRAME);
        const viewerApp = `${viewDoc}.querySelector("kigumi-app")`;
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
            const app = ${viewerApp};
            const lines = app ? Array.from(app.sceneManager.bundles()).flatMap((bundle) => bundle.drawingLines || []) : [];
            return JSON.stringify({ entered: ${JSON.stringify(entered)}, inDrawing: app && app.isInDrawing,
                active: app && app.sceneStore.activeScene().id, lines: lines.length,
                drawings: app && app.sceneStore ? app.sceneStore.drawings().length : null });
        })()`).catch((error) => String(error));
        check('a drawing draws its dotted lines, clipped per timber, with every shader compiled',
            !!drawn && drawn.broken === 0 && drawn.glError === 0,
            drawn ? `${drawn.shown} of ${drawn.lines} lines shown, ${drawn.broken} broken programs, GL error ${drawn.glError}`
                : `drawing ${drawingId}; ${state}`);
        await capture('03c-drawing-dotted-lines');
    },
};
