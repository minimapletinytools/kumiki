// Drawings, a beta feature: turned on from the options' beta section (a setting the open views
// reload to read); then a drawing's dotted lines, clipped per timber by the member id pass, drawn
// with every shader they need compiled. Nothing else enters a drawing, so nothing else draws them.

const fs = require('fs');
const path = require('path');
const { nativeImage } = require('electron');

module.exports = {
    name: 'drawings',
    async run({ check, inShell, waitFor, capture, settings, runAppCommand, openFrame, viewDoc, showTab, FRAME, DRAWING_FRAME, PARAMETER_FRAME, REPO, ARTIFACTS }) {
        await openFrame(FRAME);
        await showTab('options');
        const drawingsOn = await waitFor(() => inShell(`(() => {
            const doc = ${viewDoc};
            const sections = [...doc.querySelectorAll('#render-controls .viewer-settings-subtitle')].slice(0, 4);
            return sections.map(section => section.textContent.trim()).join(',') === 'common,controls,visual,geometry'
                && doc.getElementById('save-settings-btn').textContent.trim() === 'save options'
                && doc.getElementById('feature-parent-toggle').closest('fieldset').querySelector('legend').textContent === '3D'
                && doc.getElementById('drawing-ghosts-toggle').closest('fieldset').querySelector('legend').textContent === 'drawing'
                && !!doc.getElementById('disassembly-multiplier-slider') === Boolean(doc.getElementById('beta-assembly-toggle')?.checked)
                && !!doc.getElementById('highlight-reference-edges') && !!doc.getElementById('color-reference-faces')
                && !doc.getElementById('debug-drawing-btn') && !doc.getElementById('svg-export-pen');
        })()`), { timeoutMs: 20000 }).catch(() => false);
        check('geometry options are shared and the drawing export and debug controls are absent', drawingsOn);

        if (ARTIFACTS) {
            await inShell(`${viewDoc}.getElementById('color-reference-faces').scrollIntoView({ block: 'center' })`);
            await inShell('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
            await capture('geometry-options');
        }

        // The scale ruler: off until the options turn it on, then at the bottom right with a round length.
        const ruler = () => inShell(`(() => {
            const el = ${viewDoc}.getElementById('scale-ruler');
            if (!el || el.hidden) return null;
            const box = el.getBoundingClientRect();
            const view = ${viewDoc}.getElementById('viewport').getBoundingClientRect();
            return { label: el.querySelector('.scale-ruler-label').textContent,
                width: el.querySelector('.scale-ruler-bar').getBoundingClientRect().width,
                corner: view.right - box.right < 20 && view.bottom - box.bottom < 40 };
        })()`);
        const rulerOff = await ruler();
        await showTab('options');
        await inShell(`${viewDoc}.getElementById('scale-ruler-toggle').click()`);
        const ruler3d = await waitFor(() => ruler(), { timeoutMs: 5000 }).catch(() => null);
        check('the scale ruler is off until the options turn it on; then it is at the 3D view\'s bottom right, a round length',
            rulerOff === null && ruler3d && ruler3d.corner && /^\d+ (mm|m)$/.test(ruler3d.label) && ruler3d.width > 20 && ruler3d.width <= 121,
            JSON.stringify({ rulerOff, ruler3d }));
        await capture('03a-scale-ruler-3d');

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

        // The agent's drawings tool: list them, go back to 3D, and open one again by its name.
        const toModel = await runAppCommand('kigumi.automationDrawings', { filePath: DRAWING_FRAME, open: '3d' }).catch((error) => ({ error: String(error) }));
        const inModel = await inShell(`${viewerApp}.isInDrawing`);
        const shared = await inShell(`(() => {
            const app = ${viewerApp};
            const checkBox = (id, checked) => {
                const el = app.querySelector('#' + id);
                el.checked = checked;
                el.dispatchEvent(new Event('change', { bubbles: true }));
            };
            checkBox('highlight-reference-edges', false);
            const off = app._referenceSources().length === 0;
            checkBox('highlight-reference-edges', true);
            checkBox('color-reference-faces', true);
            const colored = () => Array.from(app.sceneManager.bundles()).some(b => b.mesh.material.vertexColors &&
                b.mesh.geometry.getAttribute('color')?.array.some(value => value < 0.99));
            const model = !app.isInDrawing && off && app._referenceSources().length > 0 && colored();
            const saved = app.collectViewerSettingsPayload();
            checkBox('color-reference-faces', false);
            const cleared = !colored() && app._referenceSources().length > 0;
            app.applyPersistedViewerSettings(saved);
            return model && cleared && colored();
        })()`);
        check('shared reference options independently highlight edges and tint the model faces and survive restore', shared);
        const named = toModel && Array.isArray(toModel.drawings) ? toModel.drawings.find((one) => one.id === drawingId) : null;
        const reopened = named ? await runAppCommand('kigumi.automationDrawings', { filePath: DRAWING_FRAME, open: named.name }).catch((error) => ({ error: String(error) })) : null;
        const reentered = await inShell(`${viewerApp}.isInDrawing && ${viewerApp}.sceneStore.activeScene().id`);
        check('the agent\'s drawings command lists the frame\'s drawings, goes back to 3D, and opens one by its name',
            toModel && toModel.open === '3d' && inModel === false && named && reopened && reopened.open === named.name && reentered === drawingId,
            JSON.stringify({ toModel, inModel, reopened, reentered }));

        // This drawing is in another frame's view, whose options are its own.
        await inShell(`${viewerApp}.setScaleRulerEnabled(true)`);
        const rulerDrawing = await waitFor(() => ruler(), { timeoutMs: 5000 }).catch(() => null);
        check('in a drawing, the scale ruler is at the bottom right too', rulerDrawing && rulerDrawing.corner && rulerDrawing.width > 20,
            JSON.stringify(rulerDrawing));
        await capture('03d-scale-ruler-drawing');
        await inShell(`${viewerApp}.setScaleRulerEnabled(false)`);

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
        const dimensionCount = await inShell(`(() => {
            const app = ${viewerApp};
            const count = app.querySelectorAll('#measurement-overlay .dim-label').length;
            app.setDrawingOption('colorReferenceFaces', true);
            app.setEdgeLineThicknessPx(2.5);
            const button = Array.from(app.querySelectorAll('#drawing-panel button')).find(b => b.textContent === 'export svg');
            button.click();
            return count;
        })()`);
        const svgFile = await waitFor(() => (fs.existsSync(exportsDir) && fs.readdirSync(exportsDir)
            .find(name => name.endsWith('.svg'))) || null, { timeoutMs: 90000 }).catch(() => null);
        const exported = svgFile ? fs.readFileSync(path.join(exportsDir, svgFile), 'utf8') : '';
        check('SVG export contains vector edges, live dimension labels, and an embedded preview',
            exported.includes('stroke-width="2.5"') && exported.includes('class="member-fills"') && exported.includes('class="edges"') && exported.includes('data:image/png;base64,') &&
            exported.includes('fill="#f4d6c4"') && exported.includes('fill="#cfdfec"') &&
            dimensionCount > 0 && (exported.match(/class="dim-label"/g) || []).length === dimensionCount,
            JSON.stringify({ svgFile, dimensionCount, bytes: exported.length }));
        if (svgFile && ARTIFACTS) fs.copyFileSync(path.join(exportsDir, svgFile), path.join(ARTIFACTS, svgFile));
        fs.rmSync(exportsDir, { recursive: true, force: true });
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

        // A trackpad scroll that orbits has no release, so a locked view springs back once it stops.
        const tiltStart = await inShell(`(() => {
            const app = ${viewerApp};
            const view = app.viewports.find((one) => one.spec.locked && one.declaredOffsetDir);
            if (!view) return { error: 'no locked view' };
            app.activeViewportId = view.id;
            const page = app.sceneStore.activeScene().page;
            app.sceneStore.activeScene().page = null;  // on a sheet a scroll pans the page instead
            app._tiltPage = page;
            app.trackpadScrollOrbits = true;
            const element = app.querySelector('#viewport');
            for (let step = 0; step < 5; step++) {
                element.dispatchEvent(new WheelEvent('wheel', { deltaX: 20, deltaY: 10, bubbles: true, cancelable: true }));
            }
            return { tilted: !view.cameraController.cameraOffsetDir.equals(view.declaredOffsetDir) };
        })()`);
        const sprungBack = await waitFor(() => inShell(`(() => {
            const app = ${viewerApp};
            const view = app.activeViewport;
            return view.cameraController.cameraOffsetDir.distanceTo(view.declaredOffsetDir) < 1e-9 || null;
        })()`), { timeoutMs: 3000 }).catch(() => false);
        await inShell(`(() => { const app = ${viewerApp}; app.sceneStore.activeScene().page = app._tiltPage;
            delete app._tiltPage; app.trackpadScrollOrbits = false; })()`);
        check('a drawing view tilted by a trackpad scroll springs back to its angle once the scroll stops',
            tiltStart.tilted && sprungBack === true, JSON.stringify({ ...tiltStart, sprungBack }));
        await capture('03d-drawing-selected-view');
        const viewportPicked = await inShell(`(async () => {
            const app = ${viewerApp};
            const panel = app.querySelector('#drawing-panel');
            const header = panel.querySelector('.dp-header');
            const closed = panel.querySelectorAll('.dp-viewport').length === 0;
            [...panel.querySelectorAll('.dp-section-header')].find((one) => one.textContent.includes('viewports')).click();
            const rows = [...panel.querySelectorAll('.dp-viewport')];
            const last = rows[rows.length - 1];
            const id = last.querySelector('.dp-viewport-label').textContent;
            last.click();
            await app.updateComplete;
            const outline = app.querySelector('.drawing-view-outline');
            return { header: header.textContent, closed, id, outlined: outline && outline.getAttribute('data-viewport-id'),
                marked: [...panel.querySelectorAll('.dp-viewport.dp-focused .dp-viewport-label')].map((one) => one.textContent) };
        })()`);
        check('the measurements panel starts closed, and clicking a view in it selects that view',
            viewportPicked.header.includes('measurements') && viewportPicked.closed
                && viewportPicked.outlined === viewportPicked.id && viewportPicked.marked.join() === viewportPicked.id,
            JSON.stringify(viewportPicked));
        // Undo and redo in a drawing, from the keyboard: a deleted measurement comes back, though the
        // host has already claimed the key (VS Code marks ctrl-Z handled on its way to the view).
        const drawingsFile = path.join(path.dirname(DRAWING_FRAME), '.kigumi', 'drawings', `${path.basename(DRAWING_FRAME, '.py')}.json`);
        const savedDrawings = fs.existsSync(drawingsFile) ? fs.readFileSync(drawingsFile) : null;
        try {
            const measureState = (where) => inShell(`(() => {
                const app = ${viewerApp};
                const found = app.focusedMeasurement(${JSON.stringify(where?.viewportId)}, ${JSON.stringify(where?.measureKey)});
                return found ? found.measure.origin || 'code' : 'missing';
            })()`);
            const target = await inShell(`(() => {
                const app = ${viewerApp};
                for (const view of app.viewports) {
                    const row = app._measurementRows(view).measurements.find((one) => one.origin !== 'deleted');
                    if (row) return { viewportId: view.id, measureKey: row.key };
                }
                return null;
            })()`);
            const press = (key, shift = false) => inShell(`(() => {
                const doc = ${viewDoc};
                const claim = (event) => event.preventDefault();
                doc.addEventListener('keydown', claim, true);
                const mac = navigator.platform.startsWith('Mac');
                doc.body.dispatchEvent(new doc.defaultView.KeyboardEvent('keydown', { key: ${JSON.stringify(key)}, shiftKey: ${shift},
                    metaKey: mac, ctrlKey: !mac, bubbles: true, cancelable: true }));
                doc.removeEventListener('keydown', claim, true);
            })()`);
            const until = (state) => waitFor(() => measureState(target).then((now) => (now === state ? now : null)), { timeoutMs: 20000 })
                .catch(() => null);
            await inShell(`${viewerApp}.deleteMeasurement(${JSON.stringify(target?.viewportId)}, ${JSON.stringify(target?.measureKey)})`);
            const deleted = await until('deleted');
            await press('z');
            const undone = await until('code');
            await press('z', true);
            const redone = await until('deleted');
            await press('z');
            const back = await until('code');
            check('in a drawing, the undo key puts a deleted measurement back and redo deletes it again, though the host claimed the key',
                Boolean(target) && deleted && undone && redone && back, JSON.stringify({ target, deleted, undone, redone, back }));
        } finally {
            if (savedDrawings) fs.writeFileSync(drawingsFile, savedDrawings);
            else fs.rmSync(drawingsFile, { force: true });
        }

        const modelOutlined = await inShell(`(async () => {
            const app = ${viewerApp};
            const button = app.querySelector('#back-to-3d-btn');
            if (!button) return { button: false };
            button.click();
            await app.updateComplete;
            app.renderMeasurements();
            return { button: true, inDrawing: app.isInDrawing, gone: !app.querySelector('#back-to-3d-btn'),
                outlined: !!app.querySelector('.drawing-view-outline') };
        })()`);
        check('the Back to 3D button over the drawing leaves it, and goes with it',
            modelOutlined.button && !modelOutlined.inDrawing && modelOutlined.gone, JSON.stringify(modelOutlined));
        check('leaving the drawing removes its view outline', !modelOutlined.outlined);

        // A refresh measures the drawings again: the sawhorse's generated dimensions move with leg_distance.
        await openFrame(PARAMETER_FRAME);
        const ends = () => inShell(`(() => {
            const app = ${viewerApp};
            const drawings = app && app.sceneStore ? app.sceneStore.drawings() : [];
            const at = drawings.flatMap((drawing) => (drawing.viewports || []).flatMap((viewport) => viewport.measurements || []))
                .map((measure) => [measure.a && measure.a.at, measure.b && measure.b.at]);
            return at.length ? JSON.stringify(at) : null;
        })()`);
        const measuredBefore = await waitFor(ends, { timeoutMs: 90000 }).catch(() => null);
        const section = await inShell(`(${viewerApp}.kiwariSections || [])[0]?.id ?? null`).catch(() => null);
        await inShell(`(() => { const app = ${viewerApp}; app.setKiwariDraft(${JSON.stringify(section)}, 'leg_distance', '20in'); app.requestRefresh(); })()`);
        const measuredAfter = await waitFor(() => ends().then((now) => (now && now !== measuredBefore ? now : null)),
            { timeoutMs: 90000 }).catch(() => null);
        check('after a refresh, a drawing\'s measurements are of the frame just built',
            Boolean(measuredBefore) && Boolean(measuredAfter), measuredBefore ? `${JSON.parse(measuredBefore).length} measurements` : 'none found');
        await inShell(`(() => { const app = ${viewerApp}; app.setKiwariDraft(${JSON.stringify(section)}, 'leg_distance', '22in'); app.requestRefresh(); })()`);
        await waitFor(() => ends().then((now) => (now && now === measuredBefore ? now : null)), { timeoutMs: 90000 })
            .catch(() => null);
    },
};
