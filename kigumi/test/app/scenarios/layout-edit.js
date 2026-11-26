// Editing a drawing's layout on the sheet: the edit button starts it, a click picks out a view, then
// split, float, resize, a divider moved, a dock (with where it will land shown first), a drag let go
// of with Escape, a camera preset and a fit, undo back to the code's, and Escape ends it.
module.exports = {
    name: 'layout-edit',
    async run({ check, inShell, waitFor, capture, runAppCommand, viewDoc, DRAWING_FRAME }) {
        await runAppCommand('kigumi.openFrameFromSidebar', DRAWING_FRAME);
        const app = `${viewDoc}.querySelector("kigumi-app")`;
        const drawingId = await waitFor(() => inShell(`(() => {
            const a = ${app};
            const drawings = a && a.sceneStore ? a.sceneStore.drawings() : [];
            return drawings.length && Array.from(a.sceneManager.bundles()).length ? drawings[drawings.length - 1].id : null;
        })()`), { timeoutMs: 90000 });
        await inShell(`${app}.enterDrawing(${JSON.stringify(drawingId)})`);
        const frame = 'new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 300))))';
        await inShell(frame);
        const info = await inShell(`(() => { const a = ${app}; const s = a.sceneStore.activeScene();
            return { layout: !!s.layout, ids: a.viewports.map(v => v.id), origin: s.origin }; })()`);
        check('the drawing carries its layout', info.layout, JSON.stringify(info));
        const first = info.ids.find(id => !/preview/i.test(id)) || info.ids[0];

        await inShell(`${app}.renderRoot.querySelector('.dp-edit-layout').click()`);
        await inShell(frame);
        check('the edit button starts editing the layout', await inShell(`${app}.layoutEditing === true`));

        // Click on a view's empty corner: the view is picked out.
        await inShell(`(() => { const a = ${app};
            const host = a.renderRoot.querySelector('#viewport').getBoundingClientRect();
            const view = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            const page = a.pageScreenRect(host.width, host.height);
            const r = view.pixelRect(page, host.height);
            const x = host.left + r.x + 6, y = host.top + (host.height - r.y - r.height) + 6;
            a.handleCanvasClick({ clientX: x, clientY: y, shiftKey: false });
        })()`);
        const picked = await waitFor(() => inShell(`${app}.layoutSelection`), { timeoutMs: 10000 }).catch(() => null);
        check('a click in a view picks it out', picked === first, String(picked));
        await inShell(frame);
        await capture('01-selected');

        const press = (selector, index, dx, dy, { capturing } = {}) => inShell(`(async () => { const a = ${app};
            const el = a.renderRoot.querySelectorAll(${JSON.stringify(selector)})[${index}];
            if (!el) return 'missing';
            const b = el.getBoundingClientRect();
            const win = a.ownerDocument.defaultView;
            const x = b.left + b.width / 2, y = b.top + b.height / 2;
            el.dispatchEvent(new win.PointerEvent('pointerdown', { bubbles: true, clientX: x, clientY: y }));
            if (${dx} || ${dy}) {
                for (let step = 1; step <= 5; step += 1) {
                    win.dispatchEvent(new win.PointerEvent('pointermove', { clientX: x + ${dx} * step / 5, clientY: y + ${dy} * step / 5 }));
                }
                await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                if (${Boolean(capturing)}) return 'held';
                win.dispatchEvent(new win.PointerEvent('pointerup', { clientX: x + ${dx}, clientY: y + ${dy} }));
            }
            return 'ok';
        })()`);
        const release = () => inShell(`(() => { const win = ${app}.ownerDocument.defaultView; win.dispatchEvent(new win.PointerEvent('pointerup', {})); })()`);
        const count = () => inShell(`${app}.viewports.length`);

        const before = await count();
        await press('.vp-tool', 0, 0, 0);
        const split = await waitFor(() => inShell(`(() => { const a = ${app}; return a.viewports.length > ${before} && a.viewports.some(v => v.id === ${JSON.stringify(first + ' 2')}); })()`), { timeoutMs: 15000 }).catch(() => false);
        check('splitting a view adds a copy beside it', split);
        await inShell(frame);
        await capture('02-split');

        // Drag the copy's grip to the middle of the preview, clear of any view's edge: it floats there.
        await inShell(`${app}.selectDrawingViewport(${JSON.stringify(first + ' 2')})`);
        await inShell(frame);
        const host = await inShell(`(() => { const a = ${app}; const h = a.renderRoot.querySelector('#viewport').getBoundingClientRect();
            const view = a.viewports.find(v => /preview/i.test(v.id)) || a.viewports[a.viewports.length - 1];
            const r = view.pixelRect(a.pageScreenRect(h.width, h.height), h.height);
            const g = a.renderRoot.querySelector('.vp-grip').getBoundingClientRect();
            return { cx: h.left + r.x + r.width / 2 - (g.left + g.width / 2), cy: h.top + (h.height - r.y - r.height / 2) - (g.top + g.height / 2) }; })()`);
        await press('.vp-grip', 0, Math.round(host.cx), Math.round(host.cy));
        const floated = await waitFor(() => inShell(`(() => { const a = ${app}; const l = a.sceneStore.activeScene().layout;
            return !a._layoutDraft && l.roots.some(r => r.leaf === ${JSON.stringify(first + ' 2')}); })()`), { timeoutMs: 15000 }).catch(() => false);
        check('a view dragged off the grid floats', floated);
        await inShell(frame);
        await capture('03-floated');

        // Resize it from a corner.
        await press('.vp-handle-se', 0, 60, 40);
        await waitFor(() => inShell(`!${app}._layoutDraft`), { timeoutMs: 15000 }).catch(() => null);
        await inShell(frame);
        await capture('04-resized');

        // Move a divider.
        await press('.vp-divider-columns', 0, -60, 0);
        await waitFor(() => inShell(`!${app}._layoutDraft`), { timeoutMs: 15000 }).catch(() => null);
        await inShell(frame);
        await capture('05-divider');

        // Drag the floating view onto the left edge of the first view, and hold it there.
        const target = await inShell(`(() => { const a = ${app}; const h = a.renderRoot.querySelector('#viewport').getBoundingClientRect();
            const view = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            const r = view.pixelRect(a.pageScreenRect(h.width, h.height), h.height);
            const g = a.renderRoot.querySelector('.vp-grip').getBoundingClientRect();
            return { dx: h.left + r.x + 8 - (g.left + g.width / 2), dy: h.top + (h.height - r.y - r.height / 2) - (g.top + g.height / 2) }; })()`);
        await press('.vp-grip', 0, Math.round(target.dx), Math.round(target.dy), { capturing: true });
        await inShell(frame);
        const drop = await inShell(`(() => { const d = ${app}._layoutDraft; return d && d.drop; })()`);
        check('dragging onto a view\'s edge shows where it will land', drop && drop.target === first && drop.side === 'left', JSON.stringify(drop));
        await capture('06-drop-zone');
        await release();
        const docked = await waitFor(() => inShell(`(() => { const a = ${app}; const l = a.sceneStore.activeScene().layout;
            return !a._layoutDraft && !l.roots.some(r => r.leaf === ${JSON.stringify(first + ' 2')}); })()`), { timeoutMs: 15000 }).catch(() => false);
        check('let go there, it docks beside that view', docked);
        await inShell(frame);
        await capture('07-docked');

        // Escape lets go of a drag and leaves the layout as it was.
        await inShell(`${app}.selectDrawingViewport(${JSON.stringify(first)})`);
        await inShell(frame);
        const layoutBefore = await inShell(`JSON.stringify(${app}.sceneStore.activeScene().layout)`);
        await press('.vp-grip', 0, 80, 60, { capturing: true });
        await inShell(`(() => { const win = ${app}.ownerDocument.defaultView; win.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); })()`);
        await release();
        await inShell('new Promise(r => setTimeout(r, 500))');
        const kept = await inShell(`(() => { const a = ${app}; return !a._layoutDraft && a.layoutEditing && JSON.stringify(a.sceneStore.activeScene().layout) === ${JSON.stringify(layoutBefore)}; })()`);
        check('escape during a drag lets go of it, still editing', kept);

        // Turn the view to look down from the top, then fit it.
        await press('.vp-tool-camera', 0, 0, 0);
        await inShell(`${app}.contextMenu.choose('top')`);
        const turned = await waitFor(() => inShell(`(() => { const a = ${app}; const v = a.viewports.find(v => v.id === ${JSON.stringify(first)});
            return !a._layoutDraft && v && Math.abs(v.spec.camera.look[2] + 1) < 1e-6; })()`), { timeoutMs: 15000 }).catch(() => false);
        check('a camera preset turns the view', turned);
        await inShell(frame);
        await capture('08-top');
        await press('.vp-tool-fit', 0, 0, 0);
        await waitFor(() => inShell(`!${app}._layoutDraft`), { timeoutMs: 15000 }).catch(() => null);

        // Undo everything back to the code's layout.
        for (let i = 0; i < 20 && await inShell(`${app}.sceneStore.activeScene().layoutEdited`); i += 1) {
            await inShell(`${app}.undoMeasurementChange()`);
            await inShell('new Promise(r => setTimeout(r, 700))');
        }
        const undone = await inShell(`(() => { const a = ${app}; return { edited: a.sceneStore.activeScene().layoutEdited, ids: a.viewports.map(v => v.id) }; })()`);
        check('undo puts the code layout back', !undone.edited && undone.ids.join() === info.ids.join(), JSON.stringify(undone));
        await inShell(frame);
        await capture('09-undone');

        await inShell(`(() => { const win = ${app}.ownerDocument.defaultView; win.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); })()`);
        check('escape ends editing', await inShell(`${app}.layoutEditing === false`));
    },
};
