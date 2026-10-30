// Drawings, a beta feature: turned on from the options' beta section (a setting the open views
// reload to read); then a drawing's dotted lines, clipped per timber by the member id pass, drawn
// with every shader they need compiled. Nothing else enters a drawing, so nothing else draws them.

const fs = require('fs');
const path = require('path');
const { nativeImage } = require('electron');

module.exports = {
    name: 'drawings',
    async run({ check, inShell, waitFor, capture, settings, runAppCommand, openFrame, viewDoc, showTab, FRAME, DRAWING_FRAME, REPO, ARTIFACTS }) {
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
        if (!drawn) return;

        // Export as PNG: the page fitted whole at about 3000 px, with its dimensions, written to the
        // frame's exports; the view the user had (zoomed and panned here) comes back as it was.
        const exportsDir = path.join(REPO, 'kigumi_exports', path.basename(DRAWING_FRAME, '.py'), 'drawings');
        fs.rmSync(exportsDir, { recursive: true, force: true });
        const before = await inShell(`(() => {
            const app = ${viewerApp};
            app.pageView = { zoom: 2, offsetX: 40, offsetY: -30 };
            app.renderViewports();
            const button = Array.from(app.querySelectorAll('#drawing-panel button.dp-action')).find((one) => one.textContent === 'export png');
            const view = JSON.stringify(app.pageView);
            const ratio = app.renderer.getPixelRatio();
            const page = app.sceneStore.activeScene().page;
            if (button) button.click();
            return { found: Boolean(button), view, ratio, page };
        })()`);
        const written = await waitFor(() => (fs.existsSync(exportsDir) && fs.readdirSync(exportsDir).find((name) => name.endsWith('.png'))) || null,
            { timeoutMs: 20000 }).catch(() => null);
        const after = await inShell(`(() => { const app = ${viewerApp}; return { view: JSON.stringify(app.pageView), ratio: app.renderer.getPixelRatio() }; })()`);
        check('the drawing panel has an "export png" button, and it writes the drawing to the frame\'s exports',
            before.found && Boolean(written), JSON.stringify({ found: before.found, written }));
        if (written) {
            const file = path.join(exportsDir, written);
            if (ARTIFACTS) fs.copyFileSync(file, path.join(ARTIFACTS, `03c-export-${written}`));
            const image = nativeImage.createFromPath(file);
            const { width, height } = image.getSize();
            const pixels = image.toBitmap();
            let marked = 0;
            for (let i = 0; i < pixels.length; i += 4 * 7) {
                if (pixels[i] < 200 || pixels[i + 1] < 200 || pixels[i + 2] < 200) marked += 1;
            }
            const pageAspect = before.page ? before.page.width / before.page.height : width / height;
            check('the exported PNG is the whole page at about 3000 px, and has something drawn on it',
                Math.max(width, height) > 2900 && Math.max(width, height) <= 3001
                    && Math.abs(width / height - pageAspect) < 0.01 && marked > 1000,
                `${width}x${height}, page aspect ${pageAspect.toFixed(3)}, ${marked} marked samples`);
            fs.rmSync(path.join(REPO, 'kigumi_exports', path.basename(DRAWING_FRAME, '.py')), { recursive: true, force: true });
        }
        check('exporting leaves the view zoomed and panned as it was, at its own pixel ratio',
            after.view === before.view && after.ratio === before.ratio, JSON.stringify({ before, after }));

        const outline = await inShell(`(() => {
            const app = ${viewerApp};
            const views = app.viewports.filter((view) => view.isOrthographic);
            const selected = () => {
                app.renderMeasurements();
                return Array.from(app.querySelectorAll('.drawing-view-outline')).map((rect) => rect.dataset.viewportId);
            };
            app.selectionManager.clearAll();
            const empty = selected();
            app.selectionManager.enterScope(views[0].id);
            app.selectionManager.setCsgFocus({ timberKey: Array.from(app.sceneManager.keys())[0],
                path: [], featureLabel: 'rptw.front' });
            const feature = selected();
            const rect = app.querySelector('.drawing-view-outline');
            const bounds = rect.getBoundingClientRect();
            const pointerEvents = getComputedStyle(rect).pointerEvents;
            app.selectionManager.setMeasurementFocus({ viewportId: views[1].id, measureKey: 'outline-test' });
            const moved = selected();
            app.selectionManager.clearAll();
            const cleared = selected();
            app.selectionManager.enterScope(views[0].id);
            app.measureDraft.hold({ reference: { timber: 'test', feature: 'front' }, geometry: { type: 'plane' } });
            const held = selected();
            app.measureDraft.leave();
            const released = selected();
            app.selectionManager.clearAll();
            selected();
            app.querySelector('.dim-group').dispatchEvent(new app.ownerDocument.defaultView.PointerEvent('pointerdown',
                { bubbles: true, shiftKey: true }));
            const clicked = selected();
            return { empty, feature, moved, cleared, held, released, clicked, focus: app.selectionManager.focus,
                first: views[0].id, second: views[1].id,
                width: bounds.width, height: bounds.height, pointerEvents };
        })()`);
        check('selection outlines only its own drawing view, and moving the selection moves the outline',
            outline.empty.length === 0 && outline.feature.join() === outline.first && outline.moved.join() === outline.second,
            JSON.stringify(outline));
        check('deselecting removes the drawing view outline', outline.cleared.length === 0);
        check('a held measurement end outlines its view until released',
            outline.held.join() === outline.first && outline.released.length === 0);
        check('the view outline has visible bounds and lets pointer input pass through',
            outline.width > 0 && outline.height > 0 && outline.pointerEvents === 'none');
        check('clicking a drawn measurement outlines its view',
            outline.focus?.kind === 'measurement' && outline.clicked.join() === outline.focus.viewportId);
        await waitFor(() => inShell(`${viewerApp}.querySelectorAll('.drawing-view-outline').length === 1`), { timeoutMs: 5000 });
        await capture('03d-drawing-selected-view');
        const modelOutlined = await inShell(`(() => {
            const app = ${viewerApp};
            app.leaveDrawing();
            app.renderMeasurements();
            return !!app.querySelector('.drawing-view-outline');
        })()`);
        check('leaving the drawing removes its view outline', !modelOutlined);
    },
};
